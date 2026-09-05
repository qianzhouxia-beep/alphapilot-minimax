#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sell-side backtest: active-sell-ratio (ASR) early-exit for Track A.

Trades : P2_base triggered trades from bt_abr_gate_fullchain output
         (real Top10 07-20..08-14, 114 candidates)
K-line : D:/alphapilot/data/kline5m_full + kline5m_full_backfill (Aug)
Ticks  : D:/alphapilot/data/tick_abr/{sym}_{date}.json (as-of buckets)

Baseline sell (same as bt_wyckoff_sell): peel + hard_stop + T+2 + limit-down.
ABR-early variants add: on a hold day, if the day's (or recent 3 buckets')
active-SELL share >= threshold, sell at next day open.

Compare: baseline vs ABR-early variants on mean/median/winrate/maxDD/hold.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\elvisq\Projects\alphapilot")
sys.path.insert(0, r"C:\Users\elvisq\Projects\alphapilot\bt_research")

import pandas as pd

import bt_sell_weak_signal as S

ROOT = Path(r"C:\Users\elvisq\Projects\alphapilot")
BACKFILL_DIR = r"D:\alphapilot\data\kline5m_full_backfill"
TICK_DIR = r"D:\alphapilot\data\tick_abr"

# thresholds to test: daily cum sell share, and last-3-bucket sell share
DAILY_ASR_LEVELS = [0.55, 0.60]
WIN3_ASR_LEVELS = [0.55, 0.60]


def _load_k5m(sym: str) -> pd.DataFrame:
    df = S.load_k5m(sym)
    if df is not None and not df.empty:
        return df
    p = os.path.join(BACKFILL_DIR, f"{sym}.parquet")
    if not os.path.exists(p):
        return pd.DataFrame()
    try:
        df = pd.read_parquet(p)
        df = df.sort_values("datetime").reset_index(drop=True)
        if not pd.api.types.is_datetime64_any_dtype(df["datetime"]):
            df["datetime"] = pd.to_datetime(df["datetime"])
        df["date"] = df["datetime"].astype(str).str[:10]
        df["time"] = df["datetime"].dt.strftime("%H:%M")
        if "vol" not in df.columns and "volume" in df.columns:
            df["vol"] = df["volume"]
        return df
    except Exception:
        return pd.DataFrame()


def _load_tick(sym: str, day: str):
    p = os.path.join(TICK_DIR, f"{sym}_{day.replace('-', '')}.json")
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def day_sell_share(tick, tmin_hi=15 * 60, win=0):
    """Active-sell share over buckets (win=0: whole day up to tmin_hi;
    win=N: last N buckets). Returns float or None."""
    if not tick:
        return None
    buckets = []
    for b5, a in tick.items():
        b = int(b5)
        if b <= tmin_hi:
            buckets.append((b, a))
    buckets.sort()
    if win > 0:
        buckets = buckets[-win:]
    buy = sum(a.get("buy", 0.0) for _, a in buckets)
    sell = sum(a.get("sell", 0.0) for _, a in buckets)
    tot = buy + sell
    if tot <= 0:
        return None
    return sell / tot


def simulate(trade, asr_level, win):
    """Simulate one trade. win: 0=daily-cum, >0=last-N-buckets.
    asr_level: active-sell share threshold for early exit."""
    sym = str(trade["symbol"])[-6:]
    date = trade["date"]
    px = float(trade["px"])
    df = _load_k5m(sym)
    if df.empty:
        return None
    dates = sorted(set(df["date"]))
    if date not in dates:
        return None
    bi = dates.index(date)
    if bi + 1 >= len(dates):
        return None

    hs, ta, pb = S.adaptive_params(df, date)
    cost = px
    peak = cost
    shares = 1000
    peel_count = 0
    trail_armed = False
    awaiting_new_high = False
    peel_peak_snapshot = 0.0
    t2_extended = False
    exit_pending = False

    hold_hist = []

    for d in range(1, 6):
        if bi + d >= len(dates):
            break
        cur_date = dates[bi + d]
        day_df = df[df["date"] == cur_date]
        if day_df.empty:
            continue
        o = float(day_df["open"].iloc[0])
        c = float(day_df["close"].iloc[-1])
        h = float(day_df["high"].max())
        l = float(day_df["low"].min())
        v = float(day_df["volume"].sum()) if "volume" in day_df else float(day_df["vol"].sum())
        ret = (c / cost - 1) * 100

        if exit_pending:
            return "asr_early", (o / cost - 1) * 100, d, (peak / cost - 1) * 100

        if h > peak:
            peak = h
        peak_prev = max(x["h"] for x in hold_hist) if hold_hist else cost

        prev_c = (float(df[df["date"] == dates[bi + d - 1]]["close"].iloc[-1])
                  if bi + d - 1 >= 0 else 0)
        daily = (c / prev_c - 1) * 100 if prev_c > 0 else 0.0
        if daily <= S.LIMIT_DOWN_PCT:
            return "limit_down", ret, d, (peak / cost - 1) * 100

        # ASR early-exit detection (intraday, as-of): if a bucket's or the
        # day's active-sell share crosses threshold -> sell next open.
        if asr_level is not None:
            tick = _load_tick(sym, cur_date)
            asr = day_sell_share(tick, win=win) if tick else None
            if asr is not None and asr >= asr_level:
                exit_pending = True
                hold_hist.append({"h": h, "l": l, "c": c, "o": o, "v": v})
                continue

        # peel pullback take-profit
        if ret >= ta * 100:
            trail_armed = True
        elif ret < 0:
            trail_armed = False
            awaiting_new_high = False

        if trail_armed and not awaiting_new_high:
            pbk = (peak - l) / peak * 100 if peak > 0 else 0.0
            if pbk >= pb * 100:
                n = peel_count
                if n >= S.PEEL_MAX_STEPS or shares < 200:
                    hold_hist.append({"h": h, "l": l, "c": c, "o": o, "v": v})
                    return "peel_clear", (c / cost - 1) * 100, d, (peak / cost - 1) * 100
                peel_count = n + 1
                awaiting_new_high = True
                peel_peak_snapshot = peak
                hold_hist.append({"h": h, "l": l, "c": c, "o": o, "v": v})
                continue

        if awaiting_new_high and peak > peel_peak_snapshot + 1e-9:
            awaiting_new_high = False

        if ret <= hs * 100:
            return "hard_stop", ret, d, (peak / cost - 1) * 100

        if d >= 3:
            if t2_extended:
                return "t2_force_after_extend", ret, d, (peak / cost - 1) * 100
            if c >= cost * S.T2_EXTEND_MIN_PRICE_RATIO:
                t2_extended = True
            else:
                return "t2_force", ret, d, (peak / cost - 1) * 100

        hold_hist.append({"h": h, "l": l, "c": c, "o": o, "v": v})

    return "hold_eod", ret, 5, (peak / cost - 1) * 100


def run(trades, asr_level=None, win=0):
    rows = []
    for t in trades:
        r = simulate(t, asr_level, win) if asr_level is not None else simulate_base(t)
        if r:
            rows.append(r)
    return pd.DataFrame(rows, columns=["reason", "ret", "hold", "peak_ret"])


def simulate_base(trade):
    """Baseline = simulate with ASR never triggered (level None)."""
    return simulate(trade, asr_level=None, win=0)


def main():
    bt = json.load(open(
        r"C:\Users\elvisq\Projects\alphapilot\output\bt_abr_gate_fullchain.json",
        encoding="utf-8"))
    trades = [t for t in bt["trades"]["P2_base"]
              if t.get("trigger") and t.get("px")]
    print(f"P2_base 触发样本: {len(trades)}")

    modes = [("基线(无ASR早退)", None)]
    for lvl in DAILY_ASR_LEVELS:
        modes.append((f"ASR日累计>={lvl}", (lvl, 0)))
    for lvl in WIN3_ASR_LEVELS:
        modes.append((f"ASR近3桶>={lvl}", (lvl, 3)))

    print(f"\n{'策略':<22} {'平均':>8} {'中位':>8} {'盈利%':>7} "
          f"{'最大亏':>8} {'持有':>6} {'早走n':>6} {'早走中位':>9}")
    results = {}
    for name, spec in modes:
        if spec is None:
            df = run(trades, None, 0)
        else:
            lvl, win = spec
            df = run(trades, lvl, win)
        results[name] = df
        we = df[df["reason"] == "asr_early"]
        we_med = we["ret"].median() if len(we) else float("nan")
        print(f"{name:<22} {df['ret'].mean():>+8.2f} {df['ret'].median():>+8.2f} "
              f"{(df['ret'] > 0).mean() * 100:>7.1f} {df['ret'].min():>+8.1f} "
              f"{df['hold'].mean():>6.1f} {len(we):>6} {we_med:>+9.2f}")

    out = ROOT / "output/bt_abr_sell_early.csv"
    for name, df in results.items():
        d = df.copy()
        d["strategy"] = name
        if name == list(results)[0]:
            d.to_csv(out, index=False, encoding="utf-8-sig", mode="w")
        else:
            d.to_csv(out, index=False, encoding="utf-8-sig", mode="a", header=False)
    print(f"\n明细已存: {out}")


if __name__ == "__main__":
    main()
