#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""入场对照：开盘 / Gap硬砍 / Gap软减仓（出场固定 T+2 收盘）

选股：严格量价金叉 + VM2.5 TopN + 资金硬门控

入场臂:
  A_open       : T+1 开盘买（近涨停跳过），仓位权重 1.0
  B_gap_hard   : ≤1.5% 开盘；1.5–3% 限价昨收×1.01；≥3% 或近涨停跳过
  C_gap_soft   : ≤1.5% 开盘 w=1；1.5–3% 限价昨收×1.01 w=0.7；
                 3–5% 限价昨收×1.02，w 线性 0.5→0；≥5% 或近涨停跳过
                 ret 按权重计贡献（相对计划满仓）

出场: 买入日下一根 K 收盘

用法:
  python3 -u backtest_entry_gap.py --start 2026-04-01 --end 2026-07-17 --top-n 2
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

ROOT = Path("/home/ubuntu/alphapilot")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent

from backtest_exit_peel import (  # noqa: E402
    limit_pct,
    max_drawdown,
    pick_candidates_vm25,
    _bare,
)

GAP_OPEN_OK = 0.015
GAP_SOFT_LO = 0.03
GAP_HARD_SKIP = 0.05
LIMIT_PREMIUM = 0.01
LIMIT_PREMIUM_SOFT = 0.02
MID_WEIGHT = 0.70  # 1.5%–3%


def settle_t2_from_buy(
    g, bi: int, buy: float, cost_rt: float, entry_mode: str, weight: float = 1.0
):
    """买入日 bi → bi+1 收盘卖。ret = weight * (gross - cost)。"""
    si = bi + 1
    if si >= len(g) or buy <= 0:
        return None
    sell = float(g.loc[si, "close"])
    if sell <= 0:
        return None
    w = float(max(0.0, min(1.0, weight)))
    if w <= 1e-12:
        return {"skip": "zero_weight"}
    gross = sell / buy - 1.0
    full = gross - cost_rt
    return {
        "skip": None,
        "buy_date": str(g.loc[bi, "date"])[:10],
        "sell_date": str(g.loc[si, "date"])[:10],
        "buy": buy,
        "sell": sell,
        "gross_ret": gross,
        "full_ret": full,
        "ret": full * w,
        "weight": w,
        "entry_mode": entry_mode,
    }


def entry_open(g, signal_ai: int, sym: str, cost_rt: float, limit_frac: float):
    if signal_ai + 2 >= len(g):
        return None
    bi = signal_ai + 1
    prev = float(g.loc[signal_ai, "close"])
    op = float(g.loc[bi, "open"])
    if prev <= 0 or op <= 0:
        return {"skip": "bad_price"}
    gap = op / prev - 1.0
    if gap >= limit_pct(sym) * limit_frac:
        return {"skip": "open_limit", "buy_date": str(g.loc[bi, "date"])[:10], "open_gap": gap}
    st = settle_t2_from_buy(g, bi, op, cost_rt, "open", 1.0)
    if st and not st.get("skip"):
        st["open_gap"] = gap
    return st


def _try_limit_fill(g, bi, prev, op, lo, premium, cost_rt, mode, weight, gap):
    limit_px = round(prev * (1.0 + premium), 2)
    if lo <= limit_px + 1e-9:
        fill = op if op <= limit_px else limit_px
        st = settle_t2_from_buy(g, bi, fill, cost_rt, mode, weight)
        if st and not st.get("skip"):
            st["open_gap"] = gap
            st["limit"] = limit_px
        return st
    return {
        "skip": "limit_miss",
        "buy_date": str(g.loc[bi, "date"])[:10],
        "open_gap": gap,
        "limit": limit_px,
        "day_low": lo,
    }


def entry_gap_hard(
    g,
    signal_ai: int,
    sym: str,
    cost_rt: float,
    limit_frac: float,
    gap_ok: float = GAP_OPEN_OK,
    gap_skip: float = GAP_SOFT_LO,
    limit_premium: float = LIMIT_PREMIUM,
):
    """原 GapAware：≥3% 硬砍。"""
    if signal_ai + 2 >= len(g):
        return None
    bi = signal_ai + 1
    prev = float(g.loc[signal_ai, "close"])
    op = float(g.loc[bi, "open"])
    lo = float(g.loc[bi, "low"])
    if prev <= 0 or op <= 0 or lo <= 0:
        return {"skip": "bad_price"}
    gap = op / prev - 1.0
    lim = limit_pct(sym)
    if gap >= lim * limit_frac or gap >= gap_skip:
        return {
            "skip": "gap_chase",
            "buy_date": str(g.loc[bi, "date"])[:10],
            "open_gap": gap,
        }
    if gap <= gap_ok:
        st = settle_t2_from_buy(g, bi, op, cost_rt, "open_ok", 1.0)
        if st and not st.get("skip"):
            st["open_gap"] = gap
        return st
    return _try_limit_fill(
        g, bi, prev, op, lo, limit_premium, cost_rt, "limit_pullback", 1.0, gap
    )


def soft_weight_3_to_5(gap: float) -> float:
    """gap∈[3%,5%) → 权重线性 0.50 → 0；gap=3%→0.5，gap→5%→0。"""
    if gap < GAP_SOFT_LO:
        return 1.0
    if gap >= GAP_HARD_SKIP:
        return 0.0
    return 0.5 * (GAP_HARD_SKIP - gap) / (GAP_HARD_SKIP - GAP_SOFT_LO)


def entry_gap_soft(
    g,
    signal_ai: int,
    sym: str,
    cost_rt: float,
    limit_frac: float,
    gap_ok: float = GAP_OPEN_OK,
):
    """3%–5% 按比重减仓 + 限价；≥5% 跳过。"""
    if signal_ai + 2 >= len(g):
        return None
    bi = signal_ai + 1
    prev = float(g.loc[signal_ai, "close"])
    op = float(g.loc[bi, "open"])
    lo = float(g.loc[bi, "low"])
    if prev <= 0 or op <= 0 or lo <= 0:
        return {"skip": "bad_price"}
    gap = op / prev - 1.0
    lim = limit_pct(sym)
    if gap >= lim * limit_frac or gap >= GAP_HARD_SKIP:
        return {
            "skip": "gap_chase",
            "buy_date": str(g.loc[bi, "date"])[:10],
            "open_gap": gap,
        }
    if gap <= gap_ok:
        st = settle_t2_from_buy(g, bi, op, cost_rt, "open_ok", 1.0)
        if st and not st.get("skip"):
            st["open_gap"] = gap
        return st
    if gap < GAP_SOFT_LO:
        return _try_limit_fill(
            g, bi, prev, op, lo, LIMIT_PREMIUM, cost_rt, "limit_mid", MID_WEIGHT, gap
        )
    # 3%–5%：减仓 + 限价昨收×1.02
    w = soft_weight_3_to_5(gap)
    if w <= 1e-12:
        return {
            "skip": "gap_chase",
            "buy_date": str(g.loc[bi, "date"])[:10],
            "open_gap": gap,
        }
    return _try_limit_fill(
        g, bi, prev, op, lo, LIMIT_PREMIUM_SOFT, cost_rt, "limit_soft_3_5", w, gap
    )


def summarize(trades, name, thr):
    filled = [t for t in trades if not t.get("skipped")]
    skipped = [t for t in trades if t.get("skipped")]
    skip_reasons = {
        k: int(sum(1 for t in skipped if t.get("skip_reason") == k))
        for k in sorted({t.get("skip_reason") for t in skipped if t.get("skip_reason")})
    }
    if not filled:
        return {
            "arm": name,
            "n_signals": len(trades),
            "n_filled": 0,
            "n_skipped": len(skipped),
            "fill_rate": 0.0,
            "note": "no fills",
            "skip_reasons": skip_reasons,
        }
    rets = np.array([float(t["ret"]) for t in filled], dtype=float)
    fulls = np.array(
        [float(t.get("full_ret", t["ret"])) for t in filled], dtype=float
    )
    weights = np.array([float(t.get("weight") or 1.0) for t in filled], dtype=float)
    by = defaultdict(list)
    for t in filled:
        by[t["date"]].append(float(t["ret"]))
    days = sorted(by)
    day = np.array([float(np.mean(by[d])) for d in days], dtype=float)
    modes = defaultdict(int)
    for t in filled:
        modes[t.get("entry_mode") or "?"] += 1
    return {
        "arm": name,
        "n_signals": len(trades),
        "n_filled": len(filled),
        "n_skipped": len(skipped),
        "fill_rate": float(len(filled) / max(len(trades), 1)),
        "n_days": len(days),
        "avg_weight": float(np.mean(weights)),
        "hit_3pct_rate": float(np.mean(fulls >= thr)),
        "win_rate": float(np.mean(rets > 0)),
        "avg_ret": float(np.mean(rets)),
        "avg_full_ret": float(np.mean(fulls)),
        "median_ret": float(np.median(rets)),
        "day_win_rate": float(np.mean(day > 0)),
        "day_avg_ret": float(np.mean(day)),
        "max_drawdown": max_drawdown(day),
        "total_return": float(np.prod(1.0 + day) - 1.0),
        "entry_modes": dict(modes),
        "skip_reasons": skip_reasons,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-04-01")
    ap.add_argument("--end", default="2026-07-17")
    ap.add_argument("--top-n", type=int, default=2)
    ap.add_argument("--threshold", type=float, default=0.03)
    ap.add_argument("--cost-rt", type=float, default=0.0015)
    ap.add_argument("--prefer", default="opt")
    ap.add_argument("--limit-frac", type=float, default=0.97)
    ap.add_argument("--gap-ok", type=float, default=GAP_OPEN_OK)
    ap.add_argument("--no-fund-gate", action="store_true")
    args = ap.parse_args()
    args.fund_gate = not args.no_fund_gate

    os.chdir(ROOT)
    from vm25_scorer import VM25Scorer
    from backtest_v3_pipeline import volume_gc_asof, fund_gate_ok as fund_gate_pipeline

    kpath = ROOT / "data/kline_cache/kline_all.parquet"
    if not kpath.exists():
        kpath = ROOT / "kline_all.parquet"
    print("load kline", kpath, flush=True)
    kdf = pd.read_parquet(kpath)
    kdf["date"] = kdf["date"].astype(str).str[:10]
    kdf["symbol"] = kdf["symbol"].astype(str).map(_bare)
    kdf = kdf[~kdf["symbol"].str.startswith(("8", "4"))]
    kdf = kdf.sort_values(["symbol", "date"]).reset_index(drop=True)
    groups = {
        sym: g.sort_values("date").reset_index(drop=True)
        for sym, g in kdf.groupby("symbol", sort=False)
    }
    cal_sym = "600519" if "600519" in groups else next(iter(groups))
    dates = sorted(d for d in groups[cal_sym]["date"].unique() if args.start <= d <= args.end)

    scorer = VM25Scorer(prefer=args.prefer)
    assert scorer.load(), "VM2.5 load failed"
    print(
        f"days={len(dates)} symbols={len(groups)} top_n={args.top_n} fund_gate={args.fund_gate}",
        flush=True,
    )

    arms = {"A_open": [], "B_gap_hard": [], "C_gap_soft": []}
    t0 = time.time()
    for di, date in enumerate(dates):
        picks = pick_candidates_vm25(
            groups, date, args, scorer, volume_gc_asof, fund_gate_pipeline
        )
        for p in picks:
            sym, ai = p["symbol"], p["ai"]
            g = groups[sym]
            settled = {
                "A_open": entry_open(g, ai, sym, args.cost_rt, args.limit_frac),
                "B_gap_hard": entry_gap_hard(
                    g, ai, sym, args.cost_rt, args.limit_frac, gap_ok=args.gap_ok
                ),
                "C_gap_soft": entry_gap_soft(
                    g, ai, sym, args.cost_rt, args.limit_frac, gap_ok=args.gap_ok
                ),
            }
            for arm, st in settled.items():
                base = {"date": date, "symbol": sym, "score": p.get("score")}
                if st is None:
                    arms[arm].append({**base, "skipped": True, "skip_reason": "no_bar"})
                    continue
                if st.get("skip"):
                    arms[arm].append(
                        {
                            **base,
                            "skipped": True,
                            "skip_reason": st["skip"],
                            "buy_date": st.get("buy_date"),
                            "open_gap": st.get("open_gap"),
                        }
                    )
                    continue
                arms[arm].append(
                    {
                        **base,
                        "skipped": False,
                        "ret": st["ret"],
                        "full_ret": st.get("full_ret", st["ret"]),
                        "gross_ret": st["gross_ret"],
                        "weight": st.get("weight", 1.0),
                        "buy": st["buy"],
                        "sell": st["sell"],
                        "buy_date": st["buy_date"],
                        "sell_date": st["sell_date"],
                        "entry_mode": st.get("entry_mode"),
                        "open_gap": st.get("open_gap"),
                        "hit_3pct": float(st.get("full_ret", st["ret"])) >= args.threshold,
                    }
                )
        if (di + 1) % 5 == 0 or di == 0:
            print(f"  {date} picks={len(picks)} elapsed={int(time.time()-t0)}s", flush=True)

    kpis = [summarize(arms[k], k, args.threshold) for k in arms]
    a = next(k for k in kpis if k["arm"] == "A_open")
    c = next(k for k in kpis if k["arm"] == "C_gap_soft")
    go_live = False
    reason = []
    if c.get("n_filled", 0) > 0 and a.get("n_filled", 0) > 0:
        fr = float(c.get("fill_rate") or 0)
        if fr < 0.70:
            reason.append(f"C fill_rate {fr:.1%} < 70%")
        else:
            avg_ok = float(c["avg_ret"]) >= float(a["avg_ret"]) - 1e-6
            dd_better = float(c["max_drawdown"]) > float(a["max_drawdown"]) - 1e-6
            if avg_ok or dd_better:
                go_live = True
                reason.append(
                    "C vs A: avg_ret {:.4f}/{:.4f}; max_dd {:.4f}/{:.4f}".format(
                        c["avg_ret"], a["avg_ret"], c["max_drawdown"], a["max_drawdown"]
                    )
                )
            else:
                reason.append("C avg_ret and max_dd both worse than Open")
    else:
        reason.append("insufficient fills")

    out = {
        "protocol": {
            "rank": "VM2.5 + strict GC + hard fund gate",
            "exit": "T+2 close (buy_day+1 close)",
            "A": "T+1 open skip near-limit, weight=1",
            "B": "gap hard: skip gap>=3% or near-limit; mid limit prev*1.01",
            "C": (
                "gap soft: <=1.5% open w=1; 1.5-3% limit prev*1.01 w=0.7; "
                "3-5% limit prev*1.02 w=linear 0.5→0; >=5% skip; ret=weight*full_ret"
            ),
            "cost_rt": args.cost_rt,
            "top_n": args.top_n,
            "note": "avg_ret 为仓位加权贡献；avg_full_ret / hit_3pct 按满仓价差",
        },
        "window": {"start": args.start, "end": args.end},
        "kpi": kpis,
        "go_live_recommendation": {
            "prefer_arm": "C_gap_soft" if go_live else "A_open",
            "go_live_soft": go_live,
            "reason": "; ".join(reason),
        },
    }
    out_path = ROOT / "output/entry_gap_vm25_backtest.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("======== Entry Gap Backtest (A/B/C) ========", flush=True)
    print(json.dumps(out["protocol"], ensure_ascii=False), flush=True)
    for k in kpis:
        print(json.dumps(k, ensure_ascii=False), flush=True)
    print("GO_LIVE_SOFT", go_live, reason, flush=True)
    print("saved", out_path, flush=True)


if __name__ == "__main__":
    main()
