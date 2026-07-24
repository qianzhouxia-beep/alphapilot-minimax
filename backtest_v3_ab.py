#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V3 管线 A/B 回测：标签对齐 hold=1 + 三组对照。

组:
  A) GC_only     : 量价金叉池内随机抽 TopK（固定 seed）
  B) GC_VM25     : 金叉 + 资金门控 + VM2.5 TopK（当前管线）
  C) GC_nofund   : 金叉 + VM2.5 TopK（去掉资金门控）

持有期默认 1 日，与 train_v25 FORWARD_DAYS=1 / THRESHOLD=0.03 对齐。
"""
from __future__ import annotations

import argparse
import json
import os
import random
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/ubuntu/alphapilot")
os.chdir(ROOT)

from vm25_scorer import VM25Scorer, _bare
from backtest_v3_pipeline import volume_gc_asof, fund_gate_ok


def summarize(trades, name, hold, threshold):
    if not trades:
        return {
            "arm": name, "n_trades": 0, "n_days": 0,
            "win_rate": None, "precision_3pct": None,
            "avg_return": None, "median_return": None,
            "day_win_rate": None, "day_avg_return": None,
        }
    rets = np.array([t["ret"] for t in trades], dtype=float)
    by_day = defaultdict(list)
    for t in trades:
        by_day[t["date"]].append(t["ret"])
    day_rets = np.array([np.mean(v) for v in by_day.values()], dtype=float)
    return {
        "arm": name,
        "hold": hold,
        "threshold": threshold,
        "n_trades": len(trades),
        "n_days": len(by_day),
        "win_rate": float((rets > 0).mean()),
        "precision_3pct": float((rets >= threshold).mean()),
        "avg_return": float(rets.mean()),
        "median_return": float(np.median(rets)),
        "day_win_rate": float((day_rets > 0).mean()),
        "day_avg_return": float(day_rets.mean()),
    }


def settle(g, ai, hold):
    hi = ai + hold
    if hi >= len(g):
        return None
    buy = float(g.loc[ai, "close"])
    sell = float(g.loc[hi, "close"])
    ret = sell / buy - 1
    if abs(ret) > 0.25:
        return None
    return ret, str(g.loc[hi, "date"]), buy


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-06-01")
    ap.add_argument("--end", default="2026-07-10")  # leave room for hold=1 settle
    ap.add_argument("--hold", type=int, default=1)
    ap.add_argument("--top-k", type=int, default=20)
    ap.add_argument("--threshold", type=float, default=0.03)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--prefer", default="opt")
    args = ap.parse_args()

    print("=== V3 A/B 回测（hold 对齐标签）===")
    print(f"窗口 {args.start}~{args.end} hold={args.hold} top_k={args.top_k} thr={args.threshold}")

    scorer = VM25Scorer(prefer=args.prefer)
    if not scorer.load():
        raise SystemExit(2)

    kpath = ROOT / "data" / "kline_cache" / "kline_all.parquet"
    if not kpath.exists():
        kpath = ROOT / "kline_all.parquet"
    kdf = pd.read_parquet(kpath)
    kdf["date"] = kdf["date"].astype(str).str[:10]
    kdf["symbol"] = kdf["symbol"].astype(str).map(_bare)

    groups = {
        sym: g.sort_values("date").reset_index(drop=True)
        for sym, g in kdf.groupby("symbol")
    }
    sample = next(iter(groups.values()))
    trade_dates = sorted(d for d in sample["date"].unique() if args.start <= d <= args.end)
    print(f"股票 {len(groups)} | 交易日 {len(trade_dates)}")

    arms = {"GC_only": [], "GC_VM25": [], "GC_nofund": []}
    t0 = time.time()
    rng = random.Random(args.seed)

    for di, date in enumerate(trade_dates):
        gc_pool = []
        scored = []
        for sym, g in groups.items():
            idxs = g.index[g["date"] <= date]
            if len(idxs) == 0:
                continue
            ai = int(idxs[-1])
            if str(g.loc[ai, "date"]) != date:
                continue
            if not volume_gc_asof(g, ai):
                continue
            settled = settle(g, ai, args.hold)
            if settled is None:
                continue
            ret, sell_date, buy = settled
            gc_pool.append({"symbol": sym, "ai": ai, "ret": ret, "sell_date": sell_date, "buy": buy})

            # score for ML arms
            sub = g.iloc[: ai + 1].copy()
            try:
                r = scorer.score(sub, sym)
            except Exception:
                continue
            if "error" in r:
                continue
            scored.append({
                "symbol": sym, "ai": ai, "ret": ret, "sell_date": sell_date,
                "buy": buy, "score": float(r["score"]),
                "fund_ok": fund_gate_ok(scorer.fund_flow.get(sym, {}), date, 5),
            })

        if not gc_pool:
            print(f"  {date}: GC=0")
            continue

        # A) random from GC
        picks_a = list(gc_pool)
        rng.shuffle(picks_a)
        picks_a = picks_a[: args.top_k]
        for p in picks_a:
            arms["GC_only"].append({
                "date": date, "symbol": p["symbol"], "ret": p["ret"],
                "win": p["ret"] > 0, "hit_3pct": p["ret"] >= args.threshold,
                "sell_date": p["sell_date"], "arm": "GC_only",
            })

        # B) GC + fund gate + VM25
        pool_b = [x for x in scored if x["fund_ok"]]
        pool_b.sort(key=lambda x: -x["score"])
        for p in pool_b[: args.top_k]:
            arms["GC_VM25"].append({
                "date": date, "symbol": p["symbol"], "ret": p["ret"],
                "score": p["score"],
                "win": p["ret"] > 0, "hit_3pct": p["ret"] >= args.threshold,
                "sell_date": p["sell_date"], "arm": "GC_VM25",
            })

        # C) GC + VM25 no fund gate
        pool_c = sorted(scored, key=lambda x: -x["score"])
        for p in pool_c[: args.top_k]:
            arms["GC_nofund"].append({
                "date": date, "symbol": p["symbol"], "ret": p["ret"],
                "score": p["score"],
                "win": p["ret"] > 0, "hit_3pct": p["ret"] >= args.threshold,
                "sell_date": p["sell_date"], "arm": "GC_nofund",
            })

        print(
            f"  {date}: GC={len(gc_pool)} scored={len(scored)} fund_ok={sum(1 for x in scored if x['fund_ok'])} "
            f"| A={len(picks_a)} B={min(args.top_k,len(pool_b))} C={min(args.top_k,len(pool_c))}",
            flush=True,
        )
        if (di + 1) % 5 == 0:
            print(f"  ... elapsed {int(time.time()-t0)}s", flush=True)

    kpis = [summarize(arms[k], k, args.hold, args.threshold) for k in ("GC_only", "GC_VM25", "GC_nofund")]

    # decile check on GC_nofund scored universe per-day aggregated is heavy; do global on B trades scores if present
    ml_trades = arms["GC_nofund"]
    decile = []
    if ml_trades and all("score" in t for t in ml_trades):
        arr = np.array([[t["score"], t["ret"]] for t in ml_trades], dtype=float)
        order = np.argsort(arr[:, 0])
        n = len(order)
        for q in range(10):
            seg = order[q * n // 10:(q + 1) * n // 10]
            sub = arr[seg]
            decile.append({
                "q": q + 1,
                "n": int(len(seg)),
                "avg_score": float(sub[:, 0].mean()),
                "avg_ret": float(sub[:, 1].mean()),
                "win_rate": float((sub[:, 1] > 0).mean()),
            })

    out = {
        "config": {
            "start": args.start, "end": args.end, "hold": args.hold,
            "top_k": args.top_k, "threshold": args.threshold, "seed": args.seed,
            "label_align": "hold==FORWARD_DAYS(1), precision uses THRESHOLD(0.03)",
        },
        "kpi": kpis,
        "decile_GC_nofund": decile,
        "verdict": None,
    }

    # simple verdict
    m = {k["arm"]: k for k in kpis}
    b, a = m.get("GC_VM25", {}), m.get("GC_only", {})
    if b.get("n_trades") and a.get("n_trades"):
        better = (b["avg_return"] or -9) > (a["avg_return"] or -9) and (b["win_rate"] or 0) > (a["win_rate"] or 0)
        out["verdict"] = (
            "VM2.5 相对纯金叉有增量" if better else
            "VM2.5 未显著优于纯金叉（优先改标签/门控，而非继续堆模型）"
        )

    path = ROOT / "output" / "v3_ab_backtest.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n======== A/B 结果 ========")
    for k in kpis:
        if not k["n_trades"]:
            print(f"{k['arm']}: 无成交")
            continue
        print(
            f"{k['arm']}: n={k['n_trades']} win={k['win_rate']*100:.1f}% "
            f"prec@3%={k['precision_3pct']*100:.1f}% avg={k['avg_return']*100:.2f}% "
            f"day_win={k['day_win_rate']*100:.1f}%"
        )
    if out["verdict"]:
        print("判定:", out["verdict"])
    print("保存:", path)


if __name__ == "__main__":
    main()