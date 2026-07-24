#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""K 位置闸门 A/B 对照回测（可交易协议）。

臂:
  A0_baseline     严格金叉 + 资金硬门 + VM2.5 TopN
  K1_hard_gate    同上，但 TopN 前经 K 位置/形态硬过滤
  K2_gate_rerank  硬过滤后按 k_adjusted_score 取 TopN

协议: T 信号 → T+1 开盘买 → T+2 收盘卖 → 成本 15bp。

加速:
  - 仅扫描资金流历史覆盖标的
  - 日内 GC+资金通过后再并行 VM2.5 打分
"""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

from vm25_scorer import VM25Scorer, _bare
from backtest_v3_pipeline import fund_gate_ok
from k_system_factors import evaluate_symbol


def limit_pct(symbol: str) -> float:
    s = _bare(symbol)
    if s.startswith(("300", "301", "688")):
        return 0.20
    if s.startswith(("8", "4")):
        return 0.30
    return 0.10


def day_chg(g: pd.DataFrame, ai: int) -> float | None:
    if ai < 1:
        return None
    prev = float(g.loc[ai - 1, "close"])
    cur = float(g.loc[ai, "close"])
    if prev <= 0:
        return None
    return cur / prev - 1


def near_limit(chg: float | None, lim: float, frac: float = 0.97) -> bool:
    if chg is None:
        return False
    return chg >= lim * frac


def precompute_strict_gc(g: pd.DataFrame) -> np.ndarray:
    """向量化严格量价金叉（与 volume_gc_asof 对齐）。"""
    n = len(g)
    out = np.zeros(n, dtype=bool)
    if n < 61:
        return out
    c = g["close"].astype(float)
    vcol = "volume" if "volume" in g.columns else "amount"
    v = g[vcol].astype(float)
    ma25 = c.rolling(25, min_periods=25).mean()
    vm5 = v.rolling(5, min_periods=5).mean()
    vm60 = v.rolling(60, min_periods=60).mean()
    cross = (vm5 > vm60) & (vm5.shift(1) <= vm60.shift(1))
    out[:] = ((c > ma25) & cross).fillna(False).to_numpy()
    return out


def settle_tradable(g: pd.DataFrame, signal_ai: int, cost_rt: float):
    bi = signal_ai + 1
    si = signal_ai + 2
    if si >= len(g):
        return None
    lim = limit_pct(str(g.loc[signal_ai, "symbol"]) if "symbol" in g.columns else "")
    buy_open = float(g.loc[bi, "open"])
    prev_close = float(g.loc[signal_ai, "close"])
    if prev_close <= 0 or buy_open <= 0:
        return None
    open_gap = buy_open / prev_close - 1
    if open_gap >= lim * 0.97:
        return {"skip": "open_limit", "buy_date": str(g.loc[bi, "date"])}
    sell_close = float(g.loc[si, "close"])
    gross = sell_close / buy_open - 1
    net = gross - cost_rt
    return {
        "skip": None,
        "buy_date": str(g.loc[bi, "date"]),
        "sell_date": str(g.loc[si, "date"]),
        "buy": buy_open,
        "sell": sell_close,
        "gross_ret": gross,
        "ret": net,
        "open_gap": open_gap,
    }


def max_drawdown(day_rets: np.ndarray) -> float:
    if len(day_rets) == 0:
        return 0.0
    eq = np.cumprod(1.0 + day_rets)
    peak = np.maximum.accumulate(eq)
    dd = eq / peak - 1.0
    return float(dd.min())


def summarize(trades: list, name: str, thr: float) -> dict:
    filled = [t for t in trades if not t.get("skipped")]
    skipped = [t for t in trades if t.get("skipped")]
    if not filled:
        return {
            "arm": name,
            "n_signals": len(trades),
            "n_filled": 0,
            "n_skipped": len(skipped),
            "fill_rate": 0.0,
        }
    rets = np.array([t["ret"] for t in filled], float)
    by = defaultdict(list)
    for t in filled:
        by[t["date"]].append(t["ret"])
    days = sorted(by)
    day = np.array([np.mean(by[d]) for d in days], float)
    return {
        "arm": name,
        "n_signals": len(trades),
        "n_filled": len(filled),
        "n_skipped": len(skipped),
        "fill_rate": float(len(filled) / max(len(trades), 1)),
        "n_days": len(days),
        "win_rate": float((rets > 0).mean()),
        "hit_3pct_rate": float((rets >= thr).mean()),
        "avg_return": float(rets.mean()),
        "median_return": float(np.median(rets)),
        "day_win_rate": float((day > 0).mean()),
        "day_avg_return": float(day.mean()),
        "max_drawdown": max_drawdown(day),
        "total_return": float(np.prod(1.0 + day) - 1.0),
        "skip_reasons": {
            k: int(sum(1 for t in skipped if t.get("skip_reason") == k))
            for k in sorted({t.get("skip_reason") for t in skipped if t.get("skip_reason")})
        },
    }


def pick_and_settle(cands: list, top_n: int, groups: dict, cost_rt: float, thr_skip: float = 0.25):
    trades = []
    cands = sorted(cands, key=lambda x: x["rank_score"], reverse=True)[:top_n]
    for c in cands:
        g = groups[c["sym"]]
        ai = c["ai"]
        st = settle_tradable(g, ai, cost_rt)
        if st is None:
            continue
        if st.get("skip"):
            trades.append(
                {
                    "date": c["date"],
                    "symbol": c["sym"],
                    "skipped": True,
                    "skip_reason": st["skip"],
                    "score": c["score"],
                    "k": c.get("k"),
                }
            )
            continue
        if abs(float(st["ret"])) > thr_skip:
            trades.append(
                {
                    "date": c["date"],
                    "symbol": c["sym"],
                    "skipped": True,
                    "skip_reason": "outlier_ret",
                    "score": c["score"],
                }
            )
            continue
        trades.append(
            {
                "date": c["date"],
                "symbol": c["sym"],
                "skipped": False,
                "ret": float(st["ret"]),
                "gross_ret": float(st["gross_ret"]),
                "score": c["score"],
                "rank_score": c["rank_score"],
                "k": c.get("k"),
                "buy_date": st["buy_date"],
                "sell_date": st["sell_date"],
            }
        )
    return trades


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-04-01")
    ap.add_argument("--end", default="2026-07-17")
    ap.add_argument("--top-n", type=int, default=2)
    ap.add_argument("--threshold", type=float, default=0.03)
    ap.add_argument("--cost-rt", type=float, default=0.0015)
    ap.add_argument("--prefer", default="opt")
    ap.add_argument("--limit-frac", type=float, default=0.97)
    ap.add_argument("--require-pattern", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    os.environ["K_REQUIRE_PATTERN"] = "1" if args.require_pattern else "0"

    print("=== K Location Gate A/B Backtest ===", flush=True)
    print(
        f"{args.start}~{args.end} top_n={args.top_n} thr={args.threshold} "
        f"cost={args.cost_rt} require_pattern={args.require_pattern} workers={args.workers}",
        flush=True,
    )

    scorer = VM25Scorer(prefer=args.prefer)
    assert scorer.load()

    kpath = ROOT / "data/kline_cache/kline_all.parquet"
    if not kpath.exists():
        kpath = ROOT / "kline_all.parquet"
    kdf = pd.read_parquet(kpath)
    kdf["date"] = kdf["date"].astype(str).str[:10]
    kdf["symbol"] = kdf["symbol"].astype(str).map(_bare)
    kdf = kdf[~kdf["symbol"].str.startswith(("8", "4"))]
    groups = {s: g.sort_values("date").reset_index(drop=True) for s, g in kdf.groupby("symbol")}

    fund_syms = {_bare(s) for s in (scorer.fund_flow or {})}
    if fund_syms:
        groups = {s: g for s, g in groups.items() if s in fund_syms}
    print(f"universe_after_fund_map={len(groups)}", flush=True)

    print("precompute GC masks...", flush=True)
    gc_masks = {s: precompute_strict_gc(g) for s, g in groups.items()}
    date_to_ai = {
        s: {str(d): i for i, d in enumerate(g["date"].astype(str).str[:10].tolist())}
        for s, g in groups.items()
    }

    cal_sym = "600519" if "600519" in groups else next(iter(groups))
    dates = sorted(d for d in groups[cal_sym]["date"].unique() if args.start <= d <= args.end)
    print(f"stocks={len(groups)} signal_days={len(dates)} calendar={cal_sym}", flush=True)

    arms = {"A0_baseline": [], "K1_hard_gate": [], "K2_gate_rerank": []}
    t0 = time.time()
    k_pass = k_fail = 0

    def score_one(sym: str, g: pd.DataFrame, ai: int, date: str):
        sub = g.iloc[: ai + 1].copy()
        try:
            r = scorer.score(sub, sym)
        except Exception:
            return None
        if "error" in r:
            return None
        base = float(r["score"])
        k = evaluate_symbol(sym, g, asof_idx=ai, require_pattern=bool(args.require_pattern))
        return {
            "sym": sym,
            "ai": ai,
            "date": date,
            "score": base,
            "rank_score": base,
            "k": k,
            "k_adj": base * (1.0 + float(k.get("k_score_boost") or 0)),
        }

    for di, date in enumerate(dates):
        gc_hits = []
        for sym, g in groups.items():
            ai = date_to_ai[sym].get(date)
            if ai is None:
                continue
            if ai + 2 >= len(g):
                continue
            if not bool(gc_masks[sym][ai]):
                continue
            lim = limit_pct(sym)
            chg = day_chg(g, ai)
            if near_limit(chg, lim, args.limit_frac):
                continue
            fh = scorer.fund_flow.get(sym, {})
            if not fund_gate_ok(fh, date):
                continue
            gc_hits.append((sym, g, ai))

        pool = []
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
            futs = [ex.submit(score_one, sym, g, ai, date) for sym, g, ai in gc_hits]
            for fut in as_completed(futs):
                row = fut.result()
                if row:
                    pool.append(row)

        for c in pool:
            if c["k"].get("k_tradeable"):
                k_pass += 1
            else:
                k_fail += 1

        arms["A0_baseline"].extend(
            pick_and_settle(
                [{**c, "rank_score": c["score"]} for c in pool],
                args.top_n,
                groups,
                args.cost_rt,
            )
        )
        k_pool = [c for c in pool if c["k"].get("k_tradeable")]
        arms["K1_hard_gate"].extend(
            pick_and_settle(
                [{**c, "rank_score": c["score"]} for c in k_pool],
                args.top_n,
                groups,
                args.cost_rt,
            )
        )
        arms["K2_gate_rerank"].extend(
            pick_and_settle(
                [{**c, "rank_score": c["k_adj"]} for c in k_pool],
                args.top_n,
                groups,
                args.cost_rt,
            )
        )

        if (di + 1) % 5 == 0 or di == 0 or di == len(dates) - 1:
            print(
                f"  [{di+1}/{len(dates)}] {date} gc+fund={len(gc_hits)} scored={len(pool)} "
                f"k_ok={len(k_pool)} elapsed={time.time()-t0:.0f}s",
                flush=True,
            )

    summaries = [summarize(arms[k], k, args.threshold) for k in arms]
    base = next(s for s in summaries if s["arm"] == "A0_baseline")
    for s in summaries:
        if s["arm"] == "A0_baseline" or not base.get("n_filled"):
            s["delta_total_vs_A0"] = 0.0
            s["delta_avg_vs_A0"] = 0.0
            s["delta_dd_vs_A0"] = 0.0
        else:
            s["delta_total_vs_A0"] = float(s.get("total_return", 0) - base.get("total_return", 0))
            s["delta_avg_vs_A0"] = float(s.get("avg_return", 0) - base.get("avg_return", 0))
            s["delta_dd_vs_A0"] = float(s.get("max_drawdown", 0) - base.get("max_drawdown", 0))

    result = {
        "protocol": "T close signal → T+1 open buy → T+2 close sell; cost 15bp; strictGC+fund+VM2.5",
        "window": {"start": args.start, "end": args.end},
        "top_n": args.top_n,
        "require_pattern": bool(args.require_pattern),
        "k_eval_pass": k_pass,
        "k_eval_fail": k_fail,
        "summaries": summaries,
        "elapsed_sec": round(time.time() - t0, 1),
    }
    out = ROOT / "output" / "k_location_gate_backtest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== RESULTS ===", flush=True)
    for s in summaries:
        print(
            f"{s['arm']}: filled={s.get('n_filled')} win={s.get('win_rate', 0):.1%} "
            f"hit3={s.get('hit_3pct_rate', 0):.1%} avg={s.get('avg_return', 0):.2%} "
            f"day_avg={s.get('day_avg_return', 0):.3%} total={s.get('total_return', 0):.2%} "
            f"maxDD={s.get('max_drawdown', 0):.2%} dTotal={s.get('delta_total_vs_A0', 0):+.2%}",
            flush=True,
        )
    print(f"wrote {out}", flush=True)


if __name__ == "__main__":
    main()
