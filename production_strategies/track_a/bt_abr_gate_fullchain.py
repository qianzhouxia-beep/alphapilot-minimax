#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backtest: add active-buy-ratio (ABR) gate to Track A P2 dynamic confirmation.

Pool  : real production Top10 archive (data/score_top10_day, 2026-07-20..07-31)
K-line: D:/alphapilot/data/kline5m_full (5m OHLCV)
Ticks : D:/alphapilot/data/tick_abr/{sym}_{date}.json (mootdx historical,
        buyorsell 0=buy / 1=sell, aggregated per 5m bucket, as-of buckets)

Arms:
  P2_base       : existing P2 dyn-confirm (trend + volume + no-chase)
  P2_cum_050    : P2_base + cumulative ABR >= 0.50 at trigger
  P2_cum_052    : P2_base + cumulative ABR >= 0.52
  P2_cum_055    : P2_base + cumulative ABR >= 0.55
  P2_win3_050   : P2_base + last-3-bucket ABR >= 0.50
  P2_win3_055   : P2_base + last-3-bucket ABR >= 0.55

Settle: T-day close and T+1 open (same as bt_dyn_confirm_long).
"""
import glob
import json
import os
import sys
import time

sys.path.insert(0, r"C:\Users\elvisq\Projects\alphapilot")
sys.path.insert(0, r"C:\Users\elvisq\Projects\alphapilot\bt_research")

import bt_dyn_confirm_long as bt

ROOT = r"C:\Users\elvisq\Projects\alphapilot"
TOP10_DIR = os.path.join(ROOT, "data", "score_top10_day")
TICK_DIR = r"D:\alphapilot\data\tick_abr"

# --- config (same as production template / bt_dyn_confirm_long) ---
CONF_VOL_RATIO = 1.3
CONF_MAX_GAP = 0.08   # production v2.12 uses 0.08 (bt_long used 0.05; use prod)
CONF_START_MIN = 9 * 60 + 35
CONF_END_MIN = 14 * 60 + 57

# --- arms ---
ARMS = ["P2_base", "P2_cum_050", "P2_cum_052", "P2_cum_055",
        "P2_win3_050", "P2_win3_055"]


def load_tick_abr(sym, day):
    p = os.path.join(TICK_DIR, f"{sym}_{day.replace('-', '')}.json")
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def cum_abr_at(tick, tmin, win=0):
    """Cumulative active-buy ratio over buckets with tmin <= given tmin.
    win=0 -> all buckets so far; win=N -> last N buckets only.
    Returns float or None if insufficient data."""
    if not tick:
        return None
    buckets = []
    for b5, a in tick.items():
        b = int(b5)
        if b <= tmin:
            buckets.append((b, a))
    buckets.sort()
    if win > 0:
        buckets = buckets[-win:]
    buy = sum(a.get("buy", 0.0) for _, a in buckets)
    sell = sum(a.get("sell", 0.0) for _, a in buckets)
    tot = buy + sell
    if tot <= 0:
        return None
    return buy / tot


def simulate_p2(d, prev_close, tick):
    """Return {arm: {trigger, px, tmin, abr_at_trigger}}."""
    if len(d) < 6 or prev_close is None or prev_close <= 0:
        return None
    n = len(d)
    open_px = float(d["open"].iloc[0])
    p935 = float(d["close"].iloc[0])
    amt_cum = d["amount"].cumsum()
    vol_cum = d["vol"].cumsum().replace(0, None).ffill()
    vwap = (amt_cum / vol_cum).values
    vol_ma5 = d["vol"].rolling(5, min_periods=1).mean().values

    # per bar, find trigger for base condition
    trigger = None  # (i, tmin, px, cum_abr, win3_abr)
    for i in range(1, n):
        t = int(d["tmin"].iloc[i])
        if t > CONF_END_MIN:
            break
        c = float(d["close"].iloc[i])
        vw = float(vwap[i]) if vwap[i] is not None else 0.0
        if vw <= 0:
            continue
        if not (c > p935 and c > vw):
            continue
        vol_ok = False
        for j in range(max(0, i - 1), i + 1):
            bar_vol = float(d["vol"].iloc[j])
            bar_vma = float(vol_ma5[j])
            bar_ret = float(d["close"].iloc[j] - d["open"].iloc[j])
            if bar_vma > 0 and bar_vol > bar_vma * CONF_VOL_RATIO and bar_ret > 0:
                vol_ok = True
                break
        if not vol_ok:
            continue
        if c > prev_close * (1 + CONF_MAX_GAP):
            continue
        cum = cum_abr_at(tick, t)
        win3 = cum_abr_at(tick, t, win=3)
        trigger = {"i": i, "tmin": t, "px": c, "cum": cum, "win3": win3}
        break

    if trigger is None:
        return {arm: {"trigger": False, "px": None, "tmin": None, "abr": None}
                for arm in ARMS}

    res = {}
    base = {"trigger": True, "px": trigger["px"], "tmin": trigger["tmin"],
            "abr": trigger["cum"]}
    res["P2_base"] = dict(base)
    for tag, val in [("P2_cum_050", 0.50), ("P2_cum_052", 0.52),
                     ("P2_cum_055", 0.55)]:
        if trigger["cum"] is not None and trigger["cum"] >= val:
            res[tag] = dict(base, abr=trigger["cum"])
        else:
            res[tag] = {"trigger": False, "px": None, "tmin": None,
                        "abr": trigger["cum"]}
    for tag, val in [("P2_win3_050", 0.50), ("P2_win3_055", 0.55)]:
        if trigger["win3"] is not None and trigger["win3"] >= val:
            res[tag] = dict(base, abr=trigger["win3"])
        else:
            res[tag] = {"trigger": False, "px": None, "tmin": None,
                        "abr": trigger["win3"]}
    return res


def main():
    files = sorted(glob.glob(os.path.join(TOP10_DIR, "*_open.json")))
    arms = {k: [] for k in ARMS}
    n_no_tick = 0
    n_no_prev = 0
    t0 = time.time()

    for af in files:
        day = os.path.basename(af).split("_")[0]
        if not ("2026-07-20" <= day <= "2026-07-31"):
            continue
        data = json.load(open(af, encoding="utf-8"))
        for it in (data.get("items") or []):
            sym = str(it.get("symbol", "")).zfill(6)
            k5m = bt.load_k5m(sym)
            if k5m is None:
                continue
            prev_close = bt.prev_close_of(k5m, day)
            if prev_close is None:
                n_no_prev += 1
                continue
            d = bt.day_df(k5m, day)
            if len(d) < 6:
                continue
            tick = load_tick_abr(sym, day)
            if tick is None:
                n_no_tick += 1
                continue
            sim = simulate_p2(d, prev_close, tick)
            if sim is None:
                continue
            next_open = bt.next_open_of(k5m, day)
            for arm, info in sim.items():
                rec = {
                    "date": day, "symbol": sym, "name": it.get("name", ""),
                    "score": it.get("score"), "rank": it.get("rank"),
                    "open_px": float(d["open"].iloc[0]),
                    "p935": float(d["close"].iloc[0]),
                    "gap_pct": (float(d["open"].iloc[0]) / prev_close - 1) * 100,
                    **info,
                }
                if info["trigger"]:
                    rec["ret_day_close"] = (float(d["close"].iloc[-1]) /
                                            info["px"] - 1) * 100
                    rec["ret_next_open"] = ((next_open / info["px"] - 1) * 100
                                            if next_open else None)
                else:
                    rec["ret_day_close"] = None
                    rec["ret_next_open"] = None
                arms[arm].append(rec)

    print(f"\n样本: 无昨收={n_no_prev} 无tick={n_no_tick}")

    def summarize(rows):
        trig = [r for r in rows if r["trigger"]]
        nont = [r for r in rows if not r["trigger"]]
        out = {
            "n_signals": len(rows),
            "n_trigger": len(trig),
            "trigger_rate": round(len(trig) / max(1, len(rows)) * 100, 1),
        }
        if trig:
            ret_day = [r["ret_day_close"] for r in trig
                       if r["ret_day_close"] is not None]
            ret_next = [r["ret_next_open"] for r in trig
                        if r["ret_next_open"] is not None]
            out.update({
                "ret_day_mean": round(float(sum(ret_day) / len(ret_day)), 3)
                if ret_day else None,
                "ret_day_win": round(100 * sum(1 for x in ret_day if x > 0) /
                                     len(ret_day), 1) if ret_day else None,
                "ret_next_mean": round(float(sum(ret_next) / len(ret_next)), 3)
                if ret_next else None,
                "ret_next_win": round(100 * sum(1 for x in ret_next if x > 0) /
                                      len(ret_next), 1) if ret_next else None,
            })
        return out

    kpis = {arm: summarize(arms[arm]) for arm in ARMS}

    print("\n======== Track A + ABR gate backtest ========")
    print(f"{'arm':<12}{'触发率':>8}{'T收均':>9}{'T收胜':>8}"
          f"{'T1开均':>9}{'T1胜':>8}{'样本':>6}")
    for arm, k in kpis.items():
        print(f"{arm:<12}{str(k.get('trigger_rate', '-')) + '%':>8}"
              f"{str(k.get('ret_day_mean', '-')) + '%':>9}"
              f"{str(k.get('ret_day_win', '-')) + '%':>8}"
              f"{str(k.get('ret_next_mean', '-')) + '%':>9}"
              f"{str(k.get('ret_next_win', '-')) + '%':>8}"
              f"{k['n_signals']:>6}")

    out_path = os.path.join(ROOT, "output", "bt_abr_gate_fullchain.json")
    json.dump({
        "protocol": {
            "pool": "real production Top10 (score_top10_day 2026-07-20..07-31)",
            "base_P2": "trend(c>P935,c>VWAP)+vol_ratio>1.3+no_chase8%",
            "arms": ARMS,
            "settle": "T day close / T+1 open",
            "note": "ABR from mootdx historical ticks (buyorsell), as-of",
        },
        "kpi": kpis,
        "trades": {arm: arms[arm] for arm in ARMS},
    }, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n已存: {out_path}")


if __name__ == "__main__":
    main()
