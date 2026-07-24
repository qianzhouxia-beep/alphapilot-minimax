#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只比 Hard vs Pure 的 Top1 / Top2 / Top3（主人实际只买最好的 1～3 只）。

协议同可交易：T+1 开 / T+2 收 / 15bp。
"""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

from vm25_scorer import VM25Scorer, _bare
from backtest_v3_pipeline import volume_gc_asof, fund_gate_ok
from backtest_v3_tradable_gated import day_chg, limit_pct, max_drawdown, near_limit, settle_tradable
from backtest_soft_universe_v1 import (
    above_ma20,
    is_downtrend_channel,
    ma,
    ret_nd,
)


def summarize(trades: list, thr: float, calendar_days: list[str]) -> dict:
    filled = [t for t in trades if not t.get("skipped")]
    by = defaultdict(list)
    for t in filled:
        by[t["date"]].append(float(t["ret"]))
    day_rets = [float(np.mean(by[d])) if d in by else 0.0 for d in calendar_days]
    day_arr = np.array(day_rets, dtype=float)
    rets = np.array([t["ret"] for t in filled], dtype=float) if filled else np.array([])
    return {
        "n_trades": len(filled),
        "win_rate": float((rets > 0).mean()) if len(rets) else None,
        "hit_3pct": float((rets >= thr).mean()) if len(rets) else None,
        "hit_5pct": float((rets >= 0.05).mean()) if len(rets) else None,
        "avg_ret": float(rets.mean()) if len(rets) else None,
        "day_avg_ret": float(day_arr.mean()) if len(day_arr) else None,
        "max_dd": max_drawdown(day_arr) if len(day_arr) else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-06-26")
    ap.add_argument("--end", default="2026-07-20")
    ap.add_argument("--score-cap", type=int, default=120)
    ap.add_argument("--cost-rt", type=float, default=0.0015)
    ap.add_argument("--threshold", type=float, default=0.03)
    ap.add_argument("--limit-frac", type=float, default=0.97)
    ap.add_argument("--prefer", default="opt")
    args = ap.parse_args()

    print("=== Hard vs Pure | Top1/2/3 only ===", flush=True)
    scorer = VM25Scorer(prefer=args.prefer)
    if not scorer.load():
        raise SystemExit(2)

    kpath = ROOT / "data/kline_cache/kline_all.parquet"
    if not kpath.exists():
        kpath = ROOT / "kline_all.parquet"
    kdf = pd.read_parquet(kpath)
    kdf["date"] = kdf["date"].astype(str).str[:10]
    kdf["symbol"] = kdf["symbol"].astype(str).map(_bare)
    kdf = kdf[~kdf["symbol"].str.startswith(("8", "4", "bj"))]
    groups = {s: g.sort_values("date").reset_index(drop=True) for s, g in kdf.groupby("symbol")}
    cal_sym = "600519" if "600519" in groups else next(iter(groups))
    dates = sorted(d for d in groups[cal_sym]["date"].unique() if args.start <= d <= args.end)
    print(f"days={len(dates)} score_cap={args.score_cap}", flush=True)

    tops = (1, 2, 3)
    arms = {f"Hard_Top{k}": [] for k in tops}
    arms.update({f"Pure_Top{k}": [] for k in tops})
    t0 = time.time()

    for di, date in enumerate(dates):
        cheap = []
        for sym, g in groups.items():
            idxs = g.index[g["date"] <= date]
            if len(idxs) == 0:
                continue
            ai = int(idxs[-1])
            if str(g.loc[ai, "date"]) != date or ai + 2 >= len(g):
                continue
            lim = limit_pct(sym)
            chg = day_chg(g, ai)
            if near_limit(chg, lim, args.limit_frac):
                continue
            if not fund_gate_ok(scorer.fund_flow.get(sym, {}), date, 5):
                continue
            if is_downtrend_channel(g, ai):
                continue
            gc = volume_gc_asof(g, ai)
            if not (above_ma20(g, ai) or gc):
                continue
            cheap.append({"symbol": sym, "ai": ai, "gc": gc, "mom5": ret_nd(g, ai, 5), "signal_chg": chg})

        gc_list = [x for x in cheap if x["gc"]]
        non_gc = sorted([x for x in cheap if not x["gc"]], key=lambda x: -x["mom5"])
        reserve = max(20, int(args.score_cap * 0.35))
        gc_take = gc_list[: max(10, args.score_cap - reserve)]
        wide = gc_take + non_gc[: max(0, args.score_cap - len(gc_take))]

        scored = []
        for x in wide:
            sub = groups[x["symbol"]].iloc[: x["ai"] + 1].copy()
            try:
                r = scorer.score(sub, x["symbol"])
            except Exception:
                continue
            if "error" in r:
                continue
            scored.append({**x, "score_raw": float(r["score"])})

        hard_ranked = sorted([x for x in scored if x["gc"]], key=lambda x: -x["score_raw"])
        pure_ranked = sorted(scored, key=lambda x: -x["score_raw"])

        def push(ranked, arm: str, n: int):
            for p in ranked[:n]:
                st = settle_tradable(groups[p["symbol"]], p["ai"], args.cost_rt)
                base = {"date": date, "symbol": p["symbol"], "score": p["score_raw"], "gc": p["gc"]}
                if st is None:
                    arms[arm].append({**base, "skipped": True, "skip_reason": "no_bar"})
                    continue
                if st.get("skip"):
                    arms[arm].append({**base, "skipped": True, "skip_reason": st["skip"]})
                    continue
                ret = float(st["ret"])
                arms[arm].append(
                    {
                        **base,
                        "skipped": False,
                        "ret": ret,
                        "win": ret > 0,
                        "hit_3pct": ret >= args.threshold,
                        "hit_5pct": ret >= 0.05,
                    }
                )

        for k in tops:
            push(hard_ranked, f"Hard_Top{k}", k)
            push(pure_ranked, f"Pure_Top{k}", k)

        print(f"  {date}: scored={len(scored)} hard={len(hard_ranked)} ({di+1}/{len(dates)})", flush=True)

    table = {}
    for name, trades in arms.items():
        table[name] = summarize(trades, args.threshold, dates)

    # 逐档对比：Pure 相对 Hard
    cmp = {}
    for k in tops:
        h, p = table[f"Hard_Top{k}"], table[f"Pure_Top{k}"]
        cmp[f"Top{k}"] = {
            "hard": h,
            "pure": p,
            "better_avg_ret": (p.get("avg_ret") or 0) > (h.get("avg_ret") or 0),
            "better_hit5": (p.get("hit_5pct") or 0) > (h.get("hit_5pct") or 0),
            "better_win": (p.get("win_rate") or 0) > (h.get("win_rate") or 0),
            "better_dd": (p.get("max_dd") or -1) > (h.get("max_dd") or -1),  # less negative = better
            "delta_avg_ret": None
            if h.get("avg_ret") is None or p.get("avg_ret") is None
            else p["avg_ret"] - h["avg_ret"],
            "delta_max_dd": None
            if h.get("max_dd") is None or p.get("max_dd") is None
            else p["max_dd"] - h["max_dd"],
        }

    out = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "window": {"start": args.start, "end": args.end},
        "note": "Only Top1/2/3 trades; Hard=gc硬宇宙 Pure=宽池VM",
        "summaries": table,
        "compare": cmp,
        "elapsed_sec": int(time.time() - t0),
    }
    path = ROOT / "output" / "soft_universe_top123_backtest.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== Top1 / Top2 / Top3：Hard(原) vs Pure(新) ===", flush=True)
    for k in tops:
        h, p = table[f"Hard_Top{k}"], table[f"Pure_Top{k}"]
        print(
            f"Top{k} Hard: avg={h['avg_ret']} hit5={h['hit_5pct']} win={h['win_rate']} dd={h['max_dd']} n={h['n_trades']}",
            flush=True,
        )
        print(
            f"Top{k} Pure: avg={p['avg_ret']} hit5={p['hit_5pct']} win={p['win_rate']} dd={p['max_dd']} n={p['n_trades']}",
            flush=True,
        )
        d = cmp[f"Top{k}"]
        print(
            f"  → Pure更好? 收益={d['better_avg_ret']} hit5={d['better_hit5']} 胜率={d['better_win']} 回撤={d['better_dd']} "
            f"(Δavg={d['delta_avg_ret']}, Δdd={d['delta_max_dd']})",
            flush=True,
        )
    print(f"saved {path}", flush=True)


if __name__ == "__main__":
    main()
