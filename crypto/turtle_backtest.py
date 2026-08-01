"""Turtle Trading Strategy — Adapted for Crypto.

Core Turtle Principles:
  1. ATR-based position sizing (1% risk per unit)
  2. Channel breakout entry (20-period high/low filter)
  3. Pyramid adding on favorable moves (+0.5 ATR per add)
  4. Chandelier trailing exit (3× ATR from peak)
  5. Partial take-profit at +1× ATR (shares some grid DNA)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd

from . import config as C

TAKER_FEE = 0.0005


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


@dataclass
class TurtleTrade:
    symbol: str
    batch_id: int
    entry_time: pd.Timestamp
    entry_price: float
    direction: str
    unit_size: float       # dollar amount per unit
    unit_count: int = 1    # how many units in this batch
    exit_time: pd.Timestamp | None = None
    exit_price: float | None = None
    pnl_pct: float | None = None
    pnl_usdt: float | None = None
    exit_reason: str = ""
    fee_usdt: float = 0.0


@dataclass
class TurtleResult:
    trades: list[TurtleTrade]
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


def _collision(p1: float, close: float) -> float:
    """Simplified collision — we just return the 'collision' meaning of how much price moved since entry."""
    return (close / p1 - 1)


def turtle_backtest(
    df: pd.DataFrame,
    initial_capital: float = 1000.0,
    max_total_units: int = 6,          # max units across all symbols
    max_units_per_sym: int = 3,         # max units per symbol
    min_score: float = 0.50,
    # Turtle ATR params
    atr_risk_pct: float = 0.005,        # risk 0.5% of capital per ATR-unit
    atr_stop_mult: float = 2.0,         # stop at -2× ATR from avg entry
    atr_trail_mult: float = 3.0,        # chandelier trail at -3× ATR from peak
    atr_add_mult: float = 0.5,          # add 1 unit on +0.5× ATR favorable move
    atr_tp_mult: float = 1.0,           # take 1 unit profit at +1× ATR
    # Channel breakout
    channel_lookback: int = 20,         # N-period high/low
    exit_channel_lookback: int = 10,    # opposite channel for exit (turtle exit)
    # General
    max_hold_hours: int = 48,
    factors: list[str] | None = None,
    taker_fee: float = TAKER_FEE,
    entry_timeframe: str = "2h",
    use_channel_filter: bool = True,    # whether to enforce breakout
) -> TurtleResult:
    """Run Turtle-inspired backtest."""
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

    df = df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    df = df.dropna(subset=factors)

    # Precompute model scores
    X = df[factors].values
    dmat = xgb.DMatrix(X)
    df["prob_long"] = model_l.predict(dmat) if model_l else np.zeros(len(df))
    df["prob_short"] = model_s.predict(dmat) if model_s else np.zeros(len(df))

    # Precompute per-symbol channel highs/lows and ATR
    df["channel_high"] = df.groupby("symbol")["high"].transform(
        lambda s: s.rolling(channel_lookback, min_periods=channel_lookback).max()
    )
    df["channel_low"] = df.groupby("symbol")["low"].transform(
        lambda s: s.rolling(channel_lookback, min_periods=channel_lookback).min()
    )
    df["exit_channel_high"] = df.groupby("symbol")["high"].transform(
        lambda s: s.rolling(exit_channel_lookback, min_periods=exit_channel_lookback).max()
    )
    df["exit_channel_low"] = df.groupby("symbol")["low"].transform(
        lambda s: s.rolling(exit_channel_lookback, min_periods=exit_channel_lookback).min()
    )
    # Ensure ATR is available
    if "atr_14" not in df.columns:
        # compute simple ATR on the fly
        tr = pd.concat([
            df["high"] - df["low"],
            (df["high"] - df["close"].shift(1)).abs(),
            (df["low"] - df["close"].shift(1)).abs(),
        ], axis=1).max(axis=1)
        df["atr_14"] = tr.groupby(df["symbol"]).transform(lambda s: s.rolling(14).mean())
    df["atr_pct"] = df["atr_14"] / df["close"]

    tf_mode = df["timeframe"].mode().iloc[0] if "timeframe" in df.columns else "2h"
    annual_scale = {"1h": np.sqrt(365 * 24), "2h": np.sqrt(365 * 12), "4h": np.sqrt(365 * 6), "1d": np.sqrt(365)}.get(tf_mode, np.sqrt(365 * 12))

    capital = initial_capital
    units: list[dict] = []       # each unit is like a mini-position
    trades: list[TurtleTrade] = []
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

        atr_p = row.get("atr_pct", 0.02)
        if pd.isna(atr_p) or atr_p <= 1e-6:
            atr_p = 0.02

        curr_units_sym = sum(1 for u in units if u["symbol"] == sym)

        # ─── EXITS — process same-symbol units ───
        for u in list(units):
            if u["symbol"] != sym:
                continue
            direction = u["direction"]
            # Weighted average entry
            avg_entry = u["avg_entry"]
            highest = u["highest"]
            lowest = u["lowest"]

            ret = (price / avg_entry - 1) * (1 if direction == "long" else -1)

            # Update peak/trough
            if direction == "long":
                u["highest"] = max(highest, price)
            else:
                u["lowest"] = min(lowest, price)

            peak_to_curr = (price / u["highest"] - 1) * (1 if direction == "long" else -1)
            trough_to_curr = (u["lowest"] / price - 1) * (1 if direction == "long" else -1)

            # ① Hard stop at -2× ATR from avg entry
            if ret <= -atr_stop_mult * atr_p:
                _close_turtle_unit(u, price, trades, ts, taker_fee, "hard_stop")
                units.remove(u)
                continue

            # ② Chandelier trailing exit at -3× ATR from peak
            if peak_to_curr <= -atr_trail_mult * atr_p:
                _close_turtle_unit(u, price, trades, ts, taker_fee, "chandelier_trail")
                units.remove(u)
                continue

            # ③ Opposite channel breakout exit (classic Turtle)
            channel_exit = False
            if direction == "long":
                # Price broke below exit channel low
                if curr_units_sym > 0 and price <= row.get("exit_channel_low", 0) and not pd.isna(row.get("exit_channel_low")):
                    channel_exit = True
            else:
                if curr_units_sym > 0 and price >= row.get("exit_channel_high", 0) and not pd.isna(row.get("exit_channel_high")):
                    channel_exit = True
            if channel_exit:
                _close_turtle_unit(u, price, trades, ts, taker_fee, "channel_exit")
                units.remove(u)
                continue

            # ④ Max hold
            try:
                hold_h = (ts - u["entry_time"]).total_seconds() / 3600
                if hold_h >= max_hold_hours:
                    _close_turtle_unit(u, price, trades, ts, taker_fee, "max_hold")
                    units.remove(u)
                    continue
            except Exception:
                pass

        # Recalc capital after exits
        capital = initial_capital + sum(t.pnl_usdt for t in trades if t.pnl_usdt is not None)
        if capital <= 0:
            _append_turtle_equity(equity, capital, units, last_price_by_sym)
            continue

        curr_units_sym = sum(1 for u in units if u["symbol"] == sym)
        total_units = len(units)

        # ─── PYRAMID ADD — add unit on favorable move ───
        if curr_units_sym > 0 and curr_units_sym < max_units_per_sym:
            for u in list(units):
                if u["symbol"] != sym:
                    continue
                direction = u["direction"]
                avg_entry = u["avg_entry"]
                ret = (price / avg_entry - 1) * (1 if direction == "long" else -1)
                # Add when price has moved favorably by atr_add_mult × ATR
                if ret >= atr_add_mult * atr_p:
                    # Only add once per price level — check we haven't already added at this level
                    if price / u["last_add_price"] - 1 >= atr_add_mult * atr_p * 0.8:
                        unit_size = capital * atr_risk_pct / (atr_p + 1e-10)
                        if unit_size > capital * 0.3:  # cap at 30% per unit
                            unit_size = capital * 0.3
                        units.append({
                            "symbol": sym,
                            "direction": direction,
                            "avg_entry": (u["avg_entry"] * u["n_units"] + price) / (u["n_units"] + 1),
                            "n_units": 1,
                            "entry_time": u["entry_time"],
                            "unit_size": unit_size,
                            "highest": max(u["highest"], price),
                            "lowest": min(u["lowest"], price),
                            "batch_id": next_batch_id,
                            "entry_fee": unit_size * taker_fee,
                            "last_add_price": price,
                        })
                        u["avg_entry"] = (u["avg_entry"] * u["n_units"] + price) / (u["n_units"] + 1)
                        u["n_units"] += 1
                        u["highest"] = max(u["highest"], price)
                        u["lowest"] = min(u["lowest"], price)
                        u["last_add_price"] = price
                        next_batch_id += 1
                        curr_units_sym += 1
                        total_units += 1
                        sym_s = sym.replace("/USDT:USDT", "")
                        log(f"  PYRAMID ADD {sym_s} {direction} @ ${price:.2f} "
                            f"(units={u['n_units']}, avg_entry=${u['avg_entry']:.2f})")
                    break  # one add per bar

        # ─── ENTRY — model score + channel breakout ───
        if curr_units_sym < max_units_per_sym and total_units < max_total_units:
            best_signal, best_dir = 0.0, None
            if prob_l > min_score and prob_l > best_signal:
                best_signal, best_dir = prob_l, "long"
            if prob_s > min_score and prob_s > best_signal:
                best_signal, best_dir = prob_s, "short"

            if best_dir is not None:
                # Turtle channel breakout filter
                channel_ok = True
                if use_channel_filter:
                    if best_dir == "long":
                        channel_ok = (
                            not pd.isna(row.get("channel_high")) and
                            price >= row["channel_high"] * 0.995  # slight tolerance
                        )
                    else:
                        channel_ok = (
                            not pd.isna(row.get("channel_low")) and
                            price <= row["channel_low"] * 1.005
                        )

                last_bar = last_signal_by_sym.get(sym, -999)
                bars_since_last = i - last_bar

                if channel_ok and bars_since_last >= 2:
                    # Only on entry timeframe
                    if entry_timeframe and row.get("timeframe") != entry_timeframe:
                        _append_turtle_equity(equity, capital, units, last_price_by_sym)
                        continue

                    last_signal_by_sym[sym] = i

                    # Turtle unit size: risk atr_risk_pct of capital per ATR unit
                    unit_size = capital * atr_risk_pct / (atr_p + 1e-10)
                    if unit_size > capital * 0.3:
                        unit_size = capital * 0.3

                    units.append({
                        "symbol": sym,
                        "direction": best_dir,
                        "avg_entry": price,
                        "n_units": 1,
                        "entry_time": ts,
                        "unit_size": unit_size,
                        "highest": price,
                        "lowest": price,
                        "batch_id": next_batch_id,
                        "entry_fee": unit_size * taker_fee,
                        "last_add_price": price,
                    })
                    next_batch_id += 1
                    sym_s = sym.replace("/USDT:USDT", "")
                    log(f"  ENTER {sym_s} {best_dir} 1st unit @ ${price:.2f} "
                        f"(prob={best_signal:.3f}, unit=${unit_size:.2f}, atr_pct={atr_p:.4f})")

        _append_turtle_equity(equity, capital, units, last_price_by_sym)

    # Close remaining
    last_row = df.groupby("symbol").last().reset_index()
    for _, lr in last_row.iterrows():
        sym_close = lr["symbol"]
        for u in list(units):
            if u["symbol"] == sym_close:
                _close_turtle_unit(u, lr["close"], trades, lr["timestamp"], taker_fee, "end_of_data")

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
    avg_hold = float(np.mean([
        (t.exit_time - t.entry_time).total_seconds() / 3600
        for t in trades if t.exit_time is not None
    ])) if trades else 0

    return TurtleResult(
        trades=trades, equity_curve=eq.tolist(),
        total_return=round(total_return * 100, 2), sharpe=round(sharpe, 4),
        max_drawdown=round(max_dd * 100, 2), win_rate=round(win_rate * 100, 2),
        avg_win=round(avg_w * 100, 4), avg_loss=round(avg_l * 100, 4),
        profit_factor=round(pf, 4), n_trades=len(trades),
        n_wins=len(wins), n_losses=len(losses),
        avg_hold_hours=round(avg_hold, 1),
        total_fees=round(sum(t.fee_usdt for t in trades), 2),
    )


def _append_turtle_equity(equity: list, capital: float, units: list, last_prices: dict):
    upnl = 0.0
    for u in units:
        px = last_prices.get(u["symbol"])
        if px is None:
            continue
        ret = (px / u["avg_entry"] - 1) * (1 if u["direction"] == "long" else -1)
        upnl += u["unit_size"] * ret
    equity.append(max(capital + upnl, 0))


def _close_turtle_unit(u: dict, exit_price: float, trades: list, ts: pd.Timestamp,
                       fee_rate: float, reason: str):
    direction = u["direction"]
    pnl_pct = (exit_price / u["avg_entry"] - 1) * (1 if direction == "long" else -1)
    pnl_usdt = u["unit_size"] * pnl_pct
    exit_fee = u["unit_size"] * fee_rate
    entry_fee = u.get("entry_fee", 0)
    total_fee = entry_fee + exit_fee
    trades.append(TurtleTrade(
        symbol=u.get("symbol", ""),
        batch_id=u["batch_id"],
        entry_time=u["entry_time"],
        entry_price=u["avg_entry"],
        direction=direction,
        unit_size=u["unit_size"],
        unit_count=u.get("n_units", 1),
        exit_time=ts,
        exit_price=exit_price,
        pnl_pct=round(pnl_pct, 6),
        pnl_usdt=round(pnl_usdt - total_fee, 4),
        exit_reason=reason,
        fee_usdt=round(total_fee, 4),
    ))


def print_turtle_result(r: TurtleResult):
    print(f"\n{'='*55}")
    print(f"Turtle Strategy Backtest")
    print(f"{'='*55}")
    print(f"  Total trades:   {r.n_trades}")
    print(f"  Wins:           {r.n_wins}")
    print(f"  Losses:         {r.n_losses}")
    print(f"  Win Rate:       {r.win_rate:.1f}%")
    print(f"  Total Return:   {r.total_return:+.2f}%")
    print(f"  Sharpe:         {r.sharpe:.3f}")
    print(f"  Max DD:         {r.max_drawdown:.2f}%")
    print(f"  Avg Win:        {r.avg_win:+.4f}%")
    print(f"  Avg Loss:       {r.avg_loss:+.4f}%")
    print(f"  Profit Factor:  {r.profit_factor:.3f}")
    print(f"  Avg Hold:       {r.avg_hold_hours:.1f}h")
    print(f"  Total Fees:     ${r.total_fees:.2f}")
    print(f"  Start:          $1,000.00")
    print(f"  End:            ${1000 * (1 + r.total_return/100):.2f}")
