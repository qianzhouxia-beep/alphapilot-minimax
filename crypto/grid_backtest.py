"""Grid batching strategy — small batch entries/exits for cumulative gains.

Batches enter at staggered prices. Each batch tracks its symbol.
Exit checks only apply when current bar matches the batch's symbol.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd

from . import config as C
from .features import list_factors

TAKER_FEE = 0.0005


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


@dataclass
class GridTrade:
    symbol: str
    batch_id: int
    entry_time: pd.Timestamp
    entry_price: float
    direction: str
    batch_size: float
    exit_time: pd.Timestamp | None = None
    exit_price: float | None = None
    pnl_pct: float | None = None
    pnl_usdt: float | None = None
    exit_reason: str = ""
    fee_usdt: float = 0.0


@dataclass
class GridResult:
    trades: list[GridTrade]
    equity_curve: list[float]
    total_return: float
    sharpe: float
    max_drawdown: float
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    n_trades: int
    n_wins: int
    n_losses: int
    avg_hold_hours: float
    total_fees: float


def grid_backtest(
    df: pd.DataFrame,
    initial_capital: float = 1000.0,
    max_positions_per_sym: int = 3,
    per_signal_risk: float = 0.015,
    min_score: float = 0.55,
    batches: int = 3,
    take_profit_levels: list[float] | None = None,
    stop_loss_levels: list[float] | None = None,
    batch_spread: float = 0.005,
    factors: list[str] | None = None,
    taker_fee: float = TAKER_FEE,
    entry_timeframe: str = "1h",
    use_atr_sizing: bool = False,
    atr_risk_pct: float = 0.002,
    atr_max_batch_pct: float = 0.25,
    cooldown_bars: int = 6,
) -> GridResult:
    """Run grid-style backtest with symmetric per-symbol position tracking.

    When use_atr_sizing=True, batch_size = capital × atr_risk_pct / (atr_pct × batches)
    so that higher volatility → smaller batches (Turtle-inspired risk normalization).
    """
    if take_profit_levels is None:
        take_profit_levels = [0.01, 0.02, 0.03]  # 1%, 2%, 3% (was 0.5%, 1%, 2%)
    if stop_loss_levels is None:
        stop_loss_levels = [-0.015, -0.025, -0.04]  # -1.5%, -2.5%, -4% (was -1%, -2%, -4%)
    if factors is None:
        raise ValueError("Need factors")
    if "symbol" not in df.columns:
        raise ValueError("DataFrame must have a 'symbol' column")

    import xgboost as xgb

    def _load_m(target):
        path = C.MODEL_DIR / f"model_{target}.ubj"
        if not path.exists():
            return None
        m = xgb.Booster()
        m.load_model(str(path))
        return m

    model_l = _load_m("long")
    model_s = _load_m("short")
    if model_l is None and model_s is None:
        raise FileNotFoundError("No models found")

    df = df.sort_values("timestamp").reset_index(drop=True)
    df = df.dropna(subset=factors)

    X = df[factors].values
    dmat = xgb.DMatrix(X)
    df["prob_long"] = model_l.predict(dmat) if model_l else np.zeros(len(df))
    df["prob_short"] = model_s.predict(dmat) if model_s else np.zeros(len(df))

    tf_mode = df["timeframe"].mode().iloc[0] if "timeframe" in df.columns else "4h"
    annual_scale = {"1h": np.sqrt(365 * 24), "4h": np.sqrt(365 * 6), "1d": np.sqrt(365)}.get(tf_mode, np.sqrt(365 * 6))

    capital = initial_capital
    positions: list[dict] = []
    trades: list[GridTrade] = []
    equity = [capital]
    next_batch_id = 0
    last_signal_by_sym: dict = {}
    last_price_by_sym: dict = {}

    for i in range(len(df)):
        row = df.iloc[i]
        sym = row["symbol"]
        ts, price = row["timestamp"], row["close"]
        prob_l, prob_s = row["prob_long"], row["prob_short"]
        last_price_by_sym[sym] = price

        # --- Exit loop — only same-symbol batches ---
        for batch in list(positions):
            if batch["symbol"] != sym:
                continue
            direction = batch["direction"]
            unrealized = (price / batch["entry_price"] - 1) * (1 if direction == "long" else -1)
            level = batch["level"]
            tp = take_profit_levels[min(level, len(take_profit_levels) - 1)]
            sl = stop_loss_levels[min(level, len(stop_loss_levels) - 1)]

            if unrealized >= tp:
                _close_batch(batch, price, trades, ts, taker_fee)
                positions.remove(batch)
                continue
            if unrealized <= sl:
                batch["exit_reason"] = "stop_loss"
                _close_batch(batch, price, trades, ts, taker_fee)
                positions.remove(batch)
                continue
            if (i - batch["entry_idx"]) >= 96:
                _close_batch(batch, price, trades, ts, taker_fee)
                positions.remove(batch)
                continue

        # Recalc capital
        capital = initial_capital + sum(t.pnl_usdt for t in trades if t.pnl_usdt is not None)
        if capital <= 0:
            _append_grid_equity(equity, capital, positions, last_price_by_sym)
            continue

        # --- Entry — limit per symbol ---
        active_sym = sum(1 for p in positions if p["symbol"] == sym)
        if active_sym >= max_positions_per_sym * batches:
            _append_grid_equity(equity, capital, positions, last_price_by_sym)
            continue

        best_signal, best_dir = 0.0, None
        if prob_l > min_score and prob_l > best_signal:
            best_signal, best_dir = prob_l, "long"
        if prob_s > min_score and prob_s > best_signal:
            best_signal, best_dir = prob_s, "short"

        last_bar = last_signal_by_sym.get(sym, -cooldown_bars)
        if best_dir is None or i - last_bar < cooldown_bars:
            _append_grid_equity(equity, capital, positions, last_price_by_sym)
            continue

        # Only enter on entry_timeframe bars
        if entry_timeframe and row.get("timeframe") != entry_timeframe:
            _append_grid_equity(equity, capital, positions, last_price_by_sym)
            continue

        last_signal_by_sym[sym] = i
        # ATR-based dynamic batch sizing
        if use_atr_sizing:
            atr_p = row.get("atr_pct", np.nan)
            if pd.isna(atr_p) or atr_p <= 1e-6:
                atr_p = 0.02  # fallback
            raw_batch = capital * atr_risk_pct / (atr_p * batches)
            max_batch = capital * atr_max_batch_pct
            batch_size = min(raw_batch, max_batch)
        else:
            batch_size = capital * per_signal_risk / batches

        for level in range(batches):
            if active_sym + level >= max_positions_per_sym * batches:
                break
            px = price * (1 - level * batch_spread) if best_dir == "long" else price * (1 + level * batch_spread)
            entry_fee = batch_size * taker_fee
            positions.append({
                "symbol": sym, "direction": best_dir, "entry_price": px,
                "entry_idx": i, "batch_size": batch_size, "level": level,
                "batch_id": next_batch_id, "entry_time": ts,
                "exit_reason": "", "entry_fee": entry_fee,
            })
            next_batch_id += 1

        _append_grid_equity(equity, capital, positions, last_price_by_sym)

    # Close remaining
    for sym_close in df["symbol"].unique():
        sym_df = df[df["symbol"] == sym_close]
        last = sym_df.iloc[-1]
        for batch in list(positions):
            if batch["symbol"] == sym_close:
                batch["exit_reason"] = "end_of_data"
                _close_batch(batch, last["close"], trades, last["timestamp"], taker_fee)

    capital = initial_capital + sum(t.pnl_usdt for t in trades if t.pnl_usdt is not None)
    equity.append(max(capital, 0))

    # ─── Metrics ───
    eq = np.array(equity, dtype=float)
    eq = np.maximum(eq, 1e-10)
    rets = np.diff(eq) / eq[:-1]
    total_return = (eq[-1] - initial_capital) / initial_capital
    sharpe = float(np.mean(rets) / (np.std(rets, ddof=1) + 1e-10)) * annual_scale if len(rets) > 0 else 0
    dd = eq / np.maximum.accumulate(eq) - 1
    max_dd = float(np.min(dd)) if len(dd) > 0 else 0

    wins = [t for t in trades if t.pnl_usdt is not None and t.pnl_usdt > 0]
    losses = [t for t in trades if t.pnl_usdt is not None and t.pnl_usdt <= 0]
    win_rate = len(wins) / len(trades) if trades else 0
    avg_w = float(np.mean([t.pnl_pct for t in wins])) if wins else 0
    avg_l = float(np.mean([t.pnl_pct for t in losses])) if losses else 0
    gw = sum(t.pnl_usdt for t in wins) if wins else 0
    gl = sum(abs(t.pnl_usdt) for t in losses) if losses else 0
    pf = abs(gw / (gl + 1e-10)) if losses else float("inf")
    avg_hold = float(np.mean([(t.exit_time - t.entry_time).total_seconds() / 3600 for t in trades if t.exit_time is not None])) if trades else 0

    return GridResult(
        trades=trades, equity_curve=eq.tolist(),
        total_return=round(total_return * 100, 2), sharpe=round(sharpe, 4),
        max_drawdown=round(max_dd * 100, 2), win_rate=round(win_rate * 100, 2),
        avg_win=round(avg_w * 100, 4), avg_loss=round(avg_l * 100, 4),
        profit_factor=round(pf, 4), n_trades=len(trades),
        n_wins=len(wins), n_losses=len(losses),
        avg_hold_hours=round(avg_hold, 1),
        total_fees=round(sum(t.fee_usdt for t in trades), 2),
    )


def _append_grid_equity(equity: list, capital: float, positions: list, last_prices: dict):
    """Portfolio equity = capital + UPnL using each symbol's latest price."""
    upnl = 0.0
    for p in positions:
        px = last_prices.get(p["symbol"])
        if px is None:
            continue
        upnl += p["batch_size"] * (px / p["entry_price"] - 1) * (1 if p["direction"] == "long" else -1)
    equity.append(max(capital + upnl, 0))


def _close_batch(batch: dict, exit_price: float, trades: list, ts: pd.Timestamp, fee_rate: float):
    direction = batch["direction"]
    pnl_pct = (exit_price / batch["entry_price"] - 1) * (1 if direction == "long" else -1)
    pnl_usdt = batch["batch_size"] * pnl_pct
    exit_fee = batch["batch_size"] * fee_rate
    total_fee = batch.get("entry_fee", batch["batch_size"] * fee_rate) + exit_fee
    trades.append(GridTrade(
        symbol=batch.get("symbol", ""),
        batch_id=batch["batch_id"],
        entry_time=batch["entry_time"],
        entry_price=batch["entry_price"],
        direction=direction,
        batch_size=batch["batch_size"],
        exit_time=ts,
        exit_price=exit_price,
        pnl_pct=round(pnl_pct, 6),
        pnl_usdt=round(pnl_usdt - total_fee, 4),
        exit_reason=batch.get("exit_reason", ""),
        fee_usdt=round(total_fee, 4),
    ))


def run_grid_pipeline(force_fetch: bool = False) -> GridResult:
    from .data import build_dataset
    from .features import compute_features, list_factors

    df = build_dataset(limit=2000, force_refresh=force_fetch)
    df = compute_features(df, forward=2, threshold=0.01)
    factors = list_factors()

    t = df.dropna(subset=["label_long", "label_short"]).copy().sort_values("timestamp")
    for col in factors:
        t[col] = t.groupby(["symbol", "timeframe"])[col].transform(lambda s: s.fillna(s.median()))
    dead = [c for c in factors if t[c].isna().any()]
    if dead:
        t = t.drop(columns=dead)
        factors = [c for c in factors if c not in dead]

    t_4h = t[t["timeframe"] == "4h"].copy()
    log(f"Grid backtest on 4h: {len(t_4h)} rows, {len(factors)} factors")
    return grid_backtest(t_4h, factors=factors)


def print_grid_result(r: GridResult):
    print(f"\n{'='*55}")
    print(f"Grid Batching Strategy Backtest")
    print(f"{'='*55}")
    print(f"  Total batches: {r.n_trades}")
    print(f"  Win batches:   {r.n_wins}")
    print(f"  Loss batches:  {r.n_losses}")
    print(f"  Win Rate:      {r.win_rate:.1f}%")
    print(f"  Total Return:  {r.total_return:+.2f}%")
    print(f"  Sharpe:        {r.sharpe:.3f}")
    print(f"  Max DD:        {r.max_drawdown:.2f}%")
    print(f"  Avg Win:       {r.avg_win:+.4f}%")
    print(f"  Avg Loss:      {r.avg_loss:+.4f}%")
    print(f"  Profit Factor: {r.profit_factor:.3f}")
    print(f"  Avg Hold:      {r.avg_hold_hours:.1f}h")
    print(f"  Total Fees:    ${r.total_fees:.2f}")
    print(f"  Start:         $1,000.00")
    print(f"  End:           ${1000 * (1 + r.total_return/100):.2f}")


if __name__ == "__main__":
    import logging, os
    os.environ["HTTP_PROXY"] = "http://127.0.0.1:7890"
    os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7890"
    logging.basicConfig(level=logging.INFO)
    r = run_grid_pipeline()
    print_grid_result(r)
