"""Backtesting engine — Binance perpetual paper backtest with peel/trailing exit."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from . import config as C
from .features import compute_features, list_factors

_models: dict = {}

TAKER_FEE = 0.0005


def _load_model(target: str = "long"):
    key = f"{target}_model"
    if key not in _models:
        import xgboost as xgb
        path = C.MODEL_PATH.with_name(C.MODEL_PATH.stem + f"_{target}" + C.MODEL_PATH.suffix)
        if not path.exists():
            path = C.MODEL_PATH
        if not path.exists():
            raise FileNotFoundError(f"Model not found: {path}")
        _models[key] = xgb.Booster()
        _models[key].load_model(str(path))
    return _models[key]


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


@dataclass
class Trade:
    symbol: str
    entry_time: pd.Timestamp
    entry_price: float
    direction: str
    size: float
    exit_time: pd.Timestamp | None = None
    exit_price: float | None = None
    pnl_pct: float | None = None
    pnl_usdt: float | None = None
    exit_reason: str = ""
    fee_usdt: float = 0.0


@dataclass
class BacktestResult:
    trades: list[Trade]
    equity_curve: list[float]
    total_return: float
    sharpe: float
    max_drawdown: float
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    n_trades: int
    total_fees: float


def backtest(
    df: pd.DataFrame,
    initial_capital: float = 1000.0,
    max_positions_per_symbol: int = 1,
    per_trade_risk: float = 0.02,
    min_score: float = 0.55,
    long_model: bool = True,
    short_model: bool = False,
    factors: list[str] | None = None,
    taker_fee: float = TAKER_FEE,
    entry_timeframe: str = "1h",
) -> BacktestResult:
    if "label_long" not in df.columns:
        raise ValueError("Run compute_features with forward/threshold first")
    if "symbol" not in df.columns:
        raise ValueError("DataFrame must have a 'symbol' column")

    if factors is None:
        factors = list_factors()
    df = df.sort_values("timestamp").reset_index(drop=True)
    df = df.dropna(subset=factors).copy()

    if long_model:
        model_l = _load_model("long")
    if short_model:
        model_s = _load_model("short")

    import xgboost as xgb

    X = df[factors].values
    dmat = xgb.DMatrix(X)
    df["prob_long"] = model_l.predict(dmat) if long_model else np.zeros(len(df))
    df["prob_short"] = model_s.predict(dmat) if short_model else np.zeros(len(df))

    # Sharpe annualization
    if "timeframe" in df.columns:
        tf_mode = df["timeframe"].mode().iloc[0]
        annual_scale = {"1h": np.sqrt(365 * 24), "4h": np.sqrt(365 * 6), "1d": np.sqrt(365)}.get(tf_mode, np.sqrt(365 * 6))
    else:
        annual_scale = np.sqrt(365 * 6)

    # Track latest price per symbol for UPnL
    last_px: dict[str, float] = {}

    capital = initial_capital
    positions: list[dict] = []
    trades: list[Trade] = []
    equity = [capital]

    for i in range(len(df)):
        row = df.iloc[i]
        sym = row["symbol"]
        ts = row["timestamp"]
        price = row["close"]
        prob_l = row["prob_long"]
        prob_s = row["prob_short"]
        last_px[sym] = price

        # 1. Exits — same symbol
        for pos in list(positions):
            if pos["symbol"] != sym:
                continue

            bars_held = i - pos["entry_idx"]
            if bars_held >= C.EXIT.max_hold_bars:
                _close_trade(pos, price, trades, ts, taker_fee)
                positions.remove(pos)
                continue

            unrealized = (price / pos["entry_price"] - 1) * (1 if pos["direction"] == "long" else -1)
            pos["peak"] = max(pos["peak"], unrealized)
            pos["trail_high"] = max(pos.get("trail_high", 0), unrealized)

            if pos["trail_high"] >= C.EXIT.trail_arm:
                pullback = pos["trail_high"] - unrealized
                if pullback >= C.EXIT.peel_pullback:
                    pos["exit_reason"] = "peel"
                    _close_trade(pos, price, trades, ts, taker_fee)
                    positions.remove(pos)
                    continue
            if unrealized <= C.EXIT.hard_stop:
                pos["exit_reason"] = "hard_stop"
                _close_trade(pos, price, trades, ts, taker_fee)
                positions.remove(pos)
                continue
            if unrealized >= C.EXIT.take_profit:
                pos["exit_reason"] = "take_profit"
                _close_trade(pos, price, trades, ts, taker_fee)
                positions.remove(pos)
                continue

        capital = _current_capital(initial_capital, trades)
        if capital <= 0:
            equity.append(0)
            continue

        # 2. Entries — per-symbol limit + entry timeframe filter
        active_sym = sum(1 for p in positions if p["symbol"] == sym)
        if active_sym >= max_positions_per_symbol:
            _append_equity(equity, capital, positions, last_px)
            continue
        if entry_timeframe and row.get("timeframe") != entry_timeframe:
            _append_equity(equity, capital, positions, last_px)
            continue

        best_signal, best_dir = 0.0, None
        if long_model and prob_l > min_score and prob_l > best_signal:
            best_signal, best_dir = prob_l, "long"
        if short_model and prob_s > min_score and prob_s > best_signal:
            best_signal, best_dir = prob_s, "short"

        if best_dir is None:
            _append_equity(equity, capital, positions, last_px)
            continue

        trade_size = capital * per_trade_risk
        positions.append({
            "symbol": sym, "direction": best_dir, "entry_price": price,
            "entry_idx": i, "entry_size": trade_size, "peak": 0.0,
            "trail_high": 0.0, "entry_time": ts,
            "entry_fee": trade_size * taker_fee,
        })
        _append_equity(equity, capital, positions, last_px)

    # Close remaining
    last_rows = df.groupby("symbol").last().reset_index()
    for sym_close in last_rows.itertuples():
        for pos in list(positions):
            if pos["symbol"] == sym_close.symbol:
                pos["exit_reason"] = "end_of_data"
                _close_trade(pos, sym_close.close, trades, sym_close.timestamp, taker_fee)

    capital = _current_capital(initial_capital, trades)
    equity.append(max(capital, 0))

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

    return BacktestResult(
        trades=trades, equity_curve=eq.tolist(),
        total_return=round(total_return * 100, 2), sharpe=round(sharpe, 4),
        max_drawdown=round(max_dd * 100, 2), win_rate=round(win_rate * 100, 2),
        avg_win=round(avg_w * 100, 4), avg_loss=round(avg_l * 100, 4),
        profit_factor=round(pf, 4), n_trades=len(trades),
        total_fees=round(sum(t.fee_usdt for t in trades), 2),
    )


def _append_equity(equity: list, capital: float, positions: list, last_px: dict):
    """Append portfolio equity using per-symbol latest prices."""
    upnl = 0.0
    for p in positions:
        px = last_px.get(p["symbol"])
        if px is None:
            continue
        upnl += p["entry_size"] * (px / p["entry_price"] - 1) * (1 if p["direction"] == "long" else -1)
    equity.append(max(capital + upnl, 0))


def _close_trade(pos: dict, exit_price: float, trades: list, ts: pd.Timestamp, fee_rate: float):
    direction = pos["direction"]
    pnl_pct = (exit_price / pos["entry_price"] - 1) * (1 if direction == "long" else -1)
    pnl_usdt = pos["entry_size"] * pnl_pct
    exit_fee = pos["entry_size"] * fee_rate
    total_fee = pos.get("entry_fee", pos["entry_size"] * fee_rate) + exit_fee
    net_pnl = pnl_usdt - total_fee
    trades.append(Trade(
        symbol=pos.get("symbol", ""), entry_time=pos["entry_time"],
        entry_price=pos["entry_price"], direction=direction, size=pos["entry_size"],
        exit_time=ts, exit_price=exit_price, pnl_pct=round(pnl_pct, 6),
        pnl_usdt=round(net_pnl, 4), exit_reason=pos.get("exit_reason", ""),
        fee_usdt=round(total_fee, 4),
    ))


def _current_capital(initial: float, trades: list[Trade]) -> float:
    return initial + sum(t.pnl_usdt for t in trades if t.pnl_usdt is not None)


def run_backtest_pipeline(force_fetch: bool = False) -> BacktestResult:
    from .data import build_dataset
    df = build_dataset(force_refresh=force_fetch)
    df = compute_features(df, forward=2, threshold=0.01)
    result = backtest(df)
    return result


def print_result(r: BacktestResult):
    print(f"\n{'='*50}")
    print(f"Backtest Results")
    print(f"{'='*50}")
    print(f"  Trades:       {r.n_trades}")
    print(f"  Total Return: {r.total_return:+.2f}%")
    print(f"  Sharpe:       {r.sharpe:.3f}")
    print(f"  Max DD:       {r.max_drawdown:.2f}%")
    print(f"  Win Rate:     {r.win_rate:.1f}%")
    print(f"  Avg Win:      {r.avg_win:+.4f}%")
    print(f"  Avg Loss:     {r.avg_loss:+.4f}%")
    print(f"  Profit Factor:{r.profit_factor:.3f}")
    print(f"  Total Fees:   ${r.total_fees:.2f}")
    print(f"  Start:        $1,000.00")
    print(f"  End:          ${1000 * (1 + r.total_return/100):.2f}")


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    result = run_backtest_pipeline()
    print_result(result)
