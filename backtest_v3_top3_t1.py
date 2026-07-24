#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用户口径：候选池(~20-80) -> 综合评分 Top3 -> T+1（次日收益，成功=涨>=3%）。

不再全市场打分。流程：
  1) 先形成候选池（严格金叉 或 放宽金叉）
  2) 仅对候选打 VM2.5 分
  3) hard: 资金硬门控后再取 Top3
     soft: 资金流软加到分数上，取 Top3（不删票）
"""
from __future__ import annotations
import argparse, json, os, time
from collections import defaultdict
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path("/home/ubuntu/alphapilot")
os.chdir(ROOT)
from vm25_scorer import VM25Scorer, _bare
from backtest_v3_pipeline import volume_gc_asof, fund_gate_ok


def relaxed_gc(kl, ai):
    """放宽：价>MA25 且 量MA5>量MA60（不要求刚上穿）"""
    if ai < 60:
        return False
    sub = kl.iloc[: ai + 1]
    c = sub["close"].astype(float).values
    vcol = "volume" if "volume" in sub.columns else "amount"
    v = sub[vcol].astype(float).values
    ma25 = pd.Series(c).rolling(25).mean().values[-1]
    vm5 = pd.Series(v).rolling(5).mean().values[-1]
    vm60 = pd.Series(v).rolling(60).mean().values[-1]
    return bool(c[-1] > ma25 and vm5 > vm60)


def fund_soft_bonus(fund_hist, date, lookback=5):
    if not fund_hist:
        return 0.0
    dates = [d for d in sorted(fund_hist.keys()) if d <= date]
    if not dates:
        return 0.0
    use = dates[-lookback:]
    s = float(sum(float(fund_hist[d]) for d in use))
    return float(0.05 * np.tanh(s / 5e8))


def summarize(trades, name, thr):
    if not trades:
        return {"arm": name, "n_trades": 0}
    rets = np.array([t["ret"] for t in trades], float)
    by = defaultdict(list)
    for t in trades:
        by[t["date"]].append(t["ret"])
    day = np.array([np.mean(v) for v in by.values()], float)
    return {
        "arm": name,
        "n_trades": int(len(trades)),
        "n_days": int(len(by)),
        "win_rate": float((rets > 0).mean()),
        "hit_3pct_rate": float((rets >= thr).mean()),
        "avg_return": float(rets.mean()),
        "median_return": float(np.median(rets)),
        "day_win_rate": float((day > 0).mean()),
        "day_avg_return": float(day.mean()),
    }


def settle_1d(g, ai):
    if ai + 1 >= len(g):
        return None
    buy = float(g.loc[ai, "close"])
    sell = float(g.loc[ai + 1, "close"])
    ret = sell / buy - 1
    if abs(ret) > 0.25:
        return None
    return ret, str(g.loc[ai + 1, "date"]), buy


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-06-01")
    ap.add_argument("--end", default="2026-07-10")
    ap.add_argument("--top-n", type=int, default=3)
    ap.add_argument("--threshold", type=float, default=0.03)
    ap.add_argument("--prefer", default="opt")
    args = ap.parse_args()

    print("=== Top3 T+1（候选池->Top3）===")
    print(f"{args.start}~{args.end} top_n={args.top_n} thr={args.threshold}")
    scorer = VM25Scorer(prefer=args.prefer)
    assert scorer.load()

    kpath = ROOT / "data/kline_cache/kline_all.parquet"
    if not kpath.exists():
        kpath = ROOT / "kline_all.parquet"
    kdf = pd.read_parquet(kpath)
    kdf["date"] = kdf["date"].astype(str).str[:10]
    kdf["symbol"] = kdf["symbol"].astype(str).map(_bare)
    groups = {s: g.sort_values("date").reset_index(drop=True) for s, g in kdf.groupby("symbol")}
    sample = next(iter(groups.values()))
    dates = sorted(d for d in sample["date"].unique() if args.start <= d <= args.end)
    print(f"stocks={len(groups)} days={len(dates)}")

    arms = {
        "hard_strictGC_fund_top3": [],
        "soft_strictGC_fundboost_top3": [],
        "soft_relaxedGC_fundboost_top3": [],
    }
    t0 = time.time()

    for di, date in enumerate(dates):
        strict_pool, relaxed_pool = [], []
        for sym, g in groups.items():
            idxs = g.index[g["date"] <= date]
            if len(idxs) == 0:
                continue
            ai = int(idxs[-1])
            if str(g.loc[ai, "date"]) != date:
                continue
            settled = settle_1d(g, ai)
            if settled is None:
                continue
            ret, sell_date, buy = settled
            is_strict = volume_gc_asof(g, ai)
            is_relax = relaxed_gc(g, ai)
            if not is_strict and not is_relax:
                continue
            sub = g.iloc[: ai + 1].copy()
            try:
                r = scorer.score(sub, sym)
            except Exception:
                continue
            if "error" in r:
                continue
            base = float(r["score"])
            fh = scorer.fund_flow.get(sym, {})
            bonus = fund_soft_bonus(fh, date)
            row = {
                "symbol": sym, "ret": ret, "sell_date": sell_date, "buy": buy,
                "score": base, "score_soft": base + bonus,
                "fund_ok": fund_gate_ok(fh, date, 5),
            }
            if is_strict:
                strict_pool.append(row)
            if is_relax:
                relaxed_pool.append(row)

        def push(cands, key, arm, hard_fund=False):
            pool = cands
            if hard_fund:
                pool = [x for x in cands if x["fund_ok"]]
            picks = sorted(pool, key=lambda x: -x[key])[: args.top_n]
            for p in picks:
                arms[arm].append({
                    "date": date, "symbol": p["symbol"], "ret": p["ret"],
                    "score": p["score"], "score_used": p[key],
                    "win": p["ret"] > 0, "hit_3pct": p["ret"] >= args.threshold,
                    "sell_date": p["sell_date"],
                })
            return len(pool), len(picks)

        p1, n1 = push(strict_pool, "score", "hard_strictGC_fund_top3", hard_fund=True)
        p2, n2 = push(strict_pool, "score_soft", "soft_strictGC_fundboost_top3", hard_fund=False)
        p3, n3 = push(relaxed_pool, "score_soft", "soft_relaxedGC_fundboost_top3", hard_fund=False)
        print(
            f"  {date}: strict={len(strict_pool)} relaxed={len(relaxed_pool)} "
            f"hard_pool={p1}->{n1} softS={p2}->{n2} softR={p3}->{n3}",
            flush=True,
        )
        if (di + 1) % 5 == 0:
            print(f"  ... {int(time.time()-t0)}s", flush=True)

    kpis = [summarize(arms[k], k, args.threshold) for k in arms]
    out = {
        "config": {
            "start": args.start, "end": args.end, "top_n": args.top_n,
            "hold": 1, "threshold": args.threshold,
            "intent": "Candidate pool then Top3 T+1; success if next-day >=3%",
        },
        "kpi": kpis,
        "trades": {k: arms[k] for k in arms},
    }
    path = ROOT / "output/v3_top3_t1_backtest.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n======== Top3 T+1 结果 ========")
    for k in kpis:
        if k.get("n_trades", 0) == 0:
            print(f"{k['arm']}: 无成交")
            continue
        print(
            f"{k['arm']}: n={k['n_trades']} days={k['n_days']} "
            f"win={k['win_rate']*100:.1f}% hit3%={k['hit_3pct_rate']*100:.1f}% "
            f"avg={k['avg_return']*100:.2f}% day_win={k['day_win_rate']*100:.1f}%"
        )
    print("saved", path)


if __name__ == "__main__":
    main()