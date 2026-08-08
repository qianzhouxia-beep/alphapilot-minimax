# -*- coding: utf-8 -*-
"""Deep-dive: label every trade as with/against/chop trend, compare quality.

Core question: are counter-trend entries the real leak?
If yes, their win rate / avg pnl will be clearly worse than with-trend.
"""
import json, sys, time
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bt_smc_gate import (
    load_history, compute_all_features, load_models, fill_nan,
    precompute_trends, Sim, INITIAL, THR_L, THR_S,
)
import xgboost as xgb


def main():
    print("=== deep dive: with-trend vs counter-trend ===", flush=True)
    df = load_history()
    df = compute_all_features(df)
    ml, ms, factors = load_models()
    fill_nan(df, factors)
    df = df.dropna(subset=[f for f in factors if f in df.columns])
    print(f"precomputing trends...", flush=True)
    trends = precompute_trends(df)

    df2 = df[df["timeframe"] == "2h"].sort_values(["symbol", "timestamp"])
    symbols = sorted(df2["symbol"].unique())
    all_bars = df2.groupby("symbol")
    ts_list = sorted(df2["timestamp"].unique())

    sim = Sim("deep")
    last_px = {}
    t0 = time.time()
    for bi, ts in enumerate(ts_list):
        rows_now, idxs = [], []
        for sym in symbols:
            sub = all_bars.get_group(sym)
            sub = sub[sub["timestamp"] == ts]
            if sub.empty:
                continue
            rows_now.append(sub.iloc[0])
            idxs.append(sym)
        if not rows_now:
            continue
        latest = pd.DataFrame(rows_now)
        need = [c for c in factors if c in latest.columns]
        dmat = xgb.DMatrix(latest[need].values)
        pl = ml.predict(dmat)
        ps = ms.predict(dmat) if ms is not None else np.zeros(len(rows_now))
        for i, sym in enumerate(idxs):
            px = float(latest.iloc[i]["close"])
            last_px[sym] = px
            sim.close_positions(sym, px, ts)
        for i, sym in enumerate(idxs):
            px = float(latest.iloc[i]["close"])
            atr = float(latest.iloc[i].get("atr_pct", 0)) if "atr_pct" in latest.columns else None
            trend = trends.get(sym, {}).get(ts, "chop")
            best_dir, best_sig = None, 0.0
            if pl[i] > THR_L:
                best_dir, best_sig = "long", float(pl[i])
            if ps[i] > THR_S and ps[i] > best_sig:
                best_dir, best_sig = "short", float(ps[i])
            cls = "chop"
            if best_dir is not None:
                if trend == "up":
                    cls = "with" if best_dir == "long" else "counter"
                elif trend == "down":
                    cls = "with" if best_dir == "short" else "counter"
            sim.enter(sym, px, float(pl[i]), float(ps[i]), atr, ts, "nogate", "chop", cls=cls)
        if (bi + 1) % 500 == 0:
            print(f"  bar {bi+1}/{len(ts_list)} {time.time()-t0:.0f}s", flush=True)

    # summarize by cls
    agg = defaultdict(lambda: {"n": 0, "wins": 0, "pnl": 0.0, "pnl_pct_sum": 0.0})
    for t in sim.trades:
        c = t.get("cls", "unknown")
        agg[c]["n"] += 1
        if t["pnl_usdt"] > 0:
            agg[c]["wins"] += 1
        agg[c]["pnl"] += t["pnl_usdt"]
        agg[c]["pnl_pct_sum"] += t["pnl_pct"]
    print("\n=== trade quality by trend class (nogate protocol) ===")
    print(f"{'class':10s} {'n':>6s} {'win%':>7s} {'avgPnl%':>9s} {'avgPnl$':>9s} {'totalPnl$':>10s}")
    for c in ["with", "counter", "chop"]:
        a = agg.get(c)
        if not a or a["n"] == 0:
            print(f"{c:10s}  0")
            continue
        print(f"{c:10s} {a['n']:6d} {100*a['wins']/a['n']:6.1f}% "
              f"{100*a['pnl_pct_sum']/a['n']:8.3f}% {a['pnl']/a['n']:9.3f} {a['pnl']:10.2f}")

    # counter-trend breakdown by symbol×dir
    print("\n=== counter-trend trades by symbol×dir (the suspected leak) ===")
    cagg = defaultdict(lambda: {"n": 0, "wins": 0, "pnl": 0.0})
    for t in sim.trades:
        if t.get("cls") != "counter":
            continue
        key = f"{t['symbol']} {t['dir']}"
        cagg[key]["n"] += 1
        if t["pnl_usdt"] > 0:
            cagg[key]["wins"] += 1
        cagg[key]["pnl"] += t["pnl_usdt"]
    print(f"{'sym dir':28s} {'n':>5s} {'win%':>7s} {'totalPnl$':>10s}")
    for k in sorted(cagg, key=lambda x: cagg[x]["pnl"])[:20]:
        a = cagg[k]
        print(f"{k:28s} {a['n']:5d} {100*a['wins']/a['n']:6.1f}% {a['pnl']:10.2f}")

    # with-trend breakdown by symbol×dir
    print("\n=== with-trend trades by symbol×dir ===")
    wagg = defaultdict(lambda: {"n": 0, "wins": 0, "pnl": 0.0})
    for t in sim.trades:
        if t.get("cls") != "with":
            continue
        key = f"{t['symbol']} {t['dir']}"
        wagg[key]["n"] += 1
        if t["pnl_usdt"] > 0:
            wagg[key]["wins"] += 1
        wagg[key]["pnl"] += t["pnl_usdt"]
    print(f"{'sym dir':28s} {'n':>5s} {'win%':>7s} {'totalPnl$':>10s}")
    for k in sorted(wagg, key=lambda x: -wagg[x]["pnl"])[:20]:
        a = wagg[k]
        print(f"{k:28s} {a['n']:5d} {100*a['wins']/a['n']:6.1f}% {a['pnl']:10.2f}")


if __name__ == "__main__":
    main()
