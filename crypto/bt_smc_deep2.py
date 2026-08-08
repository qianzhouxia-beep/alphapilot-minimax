# -*- coding: utf-8 -*-
"""Fine-grained: counter-trend trades stratified by signal strength.

Question: among counter-trend entries, does signal confidence separate
good from bad? If strong-signal counter-trend entries still win, a blanket
trend gate is wasteful. We need a *selective* rule.
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
    print("=== counter-trend quality by signal strength ===", flush=True)
    df = load_history()
    df = compute_all_features(df)
    ml, ms, factors = load_models()
    fill_nan(df, factors)
    df = df.dropna(subset=[f for f in factors if f in df.columns])
    trends = precompute_trends(df)

    df2 = df[df["timeframe"] == "2h"].sort_values(["symbol", "timestamp"])
    symbols = sorted(df2["symbol"].unique())
    all_bars = df2.groupby("symbol")
    ts_list = sorted(df2["timestamp"].unique())

    sim = Sim("deep2")
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
            sim.enter(sym, px, float(pl[i]), float(ps[i]), atr, ts, "nogate", "chop",
                      cls=cls, sig=best_sig)
        if (bi + 1) % 500 == 0:
            print(f"  bar {bi+1}/{len(ts_list)} {time.time()-t0:.0f}s", flush=True)

    # stratify counter-trend by signal strength
    bands = [(0.45, 0.50, "45-50"), (0.50, 0.55, "50-55"), (0.55, 0.60, "55-60"),
             (0.60, 0.65, "60-65"), (0.65, 0.70, "65-70"), (0.70, 1.01, "70+")]
    print("\n=== counter-trend by signal band ===")
    print(f"{'band':>8s} {'n':>5s} {'win%':>7s} {'avgPnl%':>9s} {'totalPnl$':>10s}")
    for lo, hi, name in bands:
        agg = {"n": 0, "wins": 0, "pnl": 0.0, "pct": 0.0}
        for t in sim.trades:
            if t.get("cls") != "counter":
                continue
            s = t.get("sig", 0) or 0
            if lo <= s < hi:
                agg["n"] += 1
                if t["pnl_usdt"] > 0:
                    agg["wins"] += 1
                agg["pnl"] += t["pnl_usdt"]
                agg["pct"] += t["pnl_pct"]
        if agg["n"] == 0:
            print(f"{name:>8s}    0")
            continue
        print(f"{name:>8s} {agg['n']:5d} {100*agg['wins']/agg['n']:6.1f}% "
              f"{100*agg['pct']/agg['n']:8.3f}% {agg['pnl']:10.2f}")

    # with-trend by band (for comparison)
    print("\n=== with-trend by signal band ===")
    print(f"{'band':>8s} {'n':>5s} {'win%':>7s} {'avgPnl%':>9s} {'totalPnl$':>10s}")
    for lo, hi, name in bands:
        agg = {"n": 0, "wins": 0, "pnl": 0.0, "pct": 0.0}
        for t in sim.trades:
            if t.get("cls") != "with":
                continue
            s = t.get("sig", 0) or 0
            if lo <= s < hi:
                agg["n"] += 1
                if t["pnl_usdt"] > 0:
                    agg["wins"] += 1
                agg["pnl"] += t["pnl_usdt"]
                agg["pct"] += t["pnl_pct"]
        if agg["n"] == 0:
            print(f"{name:>8s}    0")
            continue
        print(f"{name:>8s} {agg['n']:5d} {100*agg['wins']/agg['n']:6.1f}% "
              f"{100*agg['pct']/agg['n']:8.3f}% {agg['pnl']:10.2f}")

    # the two leak pairs: NEAR long counter, ADA short counter — by band
    print("\n=== the 2 leak pairs by band ===")
    for key in ["NEAR/USDT:USDT long", "ADA/USDT:USDT short"]:
        print(f"\n{key}:")
        for lo, hi, name in bands:
            agg = {"n": 0, "wins": 0, "pnl": 0.0}
            for t in sim.trades:
                if t.get("cls") != "counter" or f"{t['symbol']} {t['dir']}" != key:
                    continue
                s = t.get("sig", 0) or 0
                if lo <= s < hi:
                    agg["n"] += 1
                    if t["pnl_usdt"] > 0:
                        agg["wins"] += 1
                    agg["pnl"] += t["pnl_usdt"]
            if agg["n"] == 0:
                print(f"  {name:>8s}    0")
                continue
            print(f"  {name:>8s} {agg['n']:5d} {100*agg['wins']/agg['n']:6.1f}% {agg['pnl']:10.2f}")

    out = ROOT / "output" / "crypto" / "smc_deep2.json"
    trades_out = [{"sym": t["symbol"], "dir": t["dir"], "cls": t.get("cls"),
                   "sig": t.get("sig"), "pnl_usdt": t["pnl_usdt"], "pnl_pct": t["pnl_pct"],
                   "exit": t["exit"]} for t in sim.trades]
    out.write_text(json.dumps(trades_out, ensure_ascii=False), encoding="utf-8")
    print("\nsaved", out)


if __name__ == "__main__":
    main()
