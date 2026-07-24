#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""K 执行层对照回测（选股固定 A0：VM2.5+严格金叉+资金硬门）。

入场统一 GapSoft C（可调 gap_ok）；出场对照:

  A0_gapsoft_t2     : 买入日后一交易日收盘卖（现网 T+2 骨架）
  K_timestop        : 可卖日若买入日峰值浮盈 <1% 且开盘仍≤成本 → 开盘划痕；
                      否则仍收盘卖（近似执行器时间止损·划痕）
  K_entry_tight     : GapSoft 但 gap_ok=1%（更少追开盘，更多限价等）+ T+2 收盘
  K_both            : entry_tight + timestop

用法:
  python3 -u backtest_k_execution.py --start 2026-04-01 --end 2026-07-17 --top-n 2
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

from backtest_entry_gap import (  # noqa: E402
    GAP_HARD_SKIP,
    GAP_OPEN_OK,
    GAP_SOFT_LO,
    LIMIT_PREMIUM,
    LIMIT_PREMIUM_SOFT,
    MID_WEIGHT,
    entry_gap_soft,
    soft_weight_3_to_5,
    summarize,
)
from backtest_exit_peel import limit_pct, pick_candidates_vm25, _bare  # noqa: E402


def settle_t2_close(g, bi: int, buy: float, cost_rt: float, weight: float, entry_mode: str):
    si = bi + 1
    if si >= len(g) or buy <= 0:
        return None
    sell = float(g.loc[si, "close"])
    if sell <= 0:
        return None
    w = float(max(0.0, min(1.0, weight)))
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
        "exit_mode": "t2_close",
    }


def settle_k_timestop(
    g,
    bi: int,
    buy: float,
    cost_rt: float,
    weight: float,
    entry_mode: str,
    min_peak: float = 0.01,
    max_pnl: float = 0.0,
):
    """买入日 bi；下一交易日 si 可卖。

    划痕条件（对齐 k_execution.time_stop_triggered 的日频近似）:
      - 买入日最高价相对成本峰值 < min_peak
      - 可卖日开盘价 / 成本 - 1 <= max_pnl
      → 以开盘价卖出（模拟早盘划痕，不等 14:45 T+2）
    否则仍 si 收盘卖。
    """
    si = bi + 1
    if si >= len(g) or buy <= 0:
        return None
    hi_buy = float(g.loc[bi, "high"])
    op_si = float(g.loc[si, "open"])
    cl_si = float(g.loc[si, "close"])
    if hi_buy <= 0 or op_si <= 0 or cl_si <= 0:
        return None

    peak_gain = hi_buy / buy - 1.0
    open_pnl = op_si / buy - 1.0
    scratch = peak_gain < min_peak and open_pnl <= max_pnl
    sell = op_si if scratch else cl_si
    exit_mode = "k_scratch_open" if scratch else "t2_close"

    w = float(max(0.0, min(1.0, weight)))
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
        "exit_mode": exit_mode,
        "peak_gain_buy_day": round(peak_gain, 4),
        "scratched": scratch,
    }


def _try_limit(g, bi, prev, op, lo, premium, cost_rt, mode, weight, gap, settler):
    limit_px = round(prev * (1.0 + premium), 2)
    if lo <= limit_px + 1e-9:
        fill = op if op <= limit_px else limit_px
        st = settler(g, bi, fill, cost_rt, weight, mode)
        if st and not st.get("skip"):
            st["open_gap"] = gap
            st["limit"] = limit_px
        return st
    return {
        "skip": "limit_miss",
        "buy_date": str(g.loc[bi, "date"])[:10],
        "open_gap": gap,
        "limit": limit_px,
    }


def entry_gap_soft_custom(
    g,
    signal_ai: int,
    sym: str,
    cost_rt: float,
    limit_frac: float,
    gap_ok: float,
    settler,
):
    """与 entry_gap_soft 相同入场规则，出场由 settler 决定。"""
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
        return {"skip": "gap_chase", "buy_date": str(g.loc[bi, "date"])[:10], "open_gap": gap}
    if gap <= gap_ok:
        st = settler(g, bi, op, cost_rt, 1.0, "open_ok")
        if st and not st.get("skip"):
            st["open_gap"] = gap
        return st
    if gap < GAP_SOFT_LO:
        return _try_limit(
            g, bi, prev, op, lo, LIMIT_PREMIUM, cost_rt, "limit_mid", MID_WEIGHT, gap, settler
        )
    w = soft_weight_3_to_5(gap)
    if w <= 1e-12:
        return {"skip": "gap_chase", "buy_date": str(g.loc[bi, "date"])[:10], "open_gap": gap}
    return _try_limit(
        g, bi, prev, op, lo, LIMIT_PREMIUM_SOFT, cost_rt, "limit_soft_3_5", w, gap, settler
    )


def append_trade(arms, arm, date, sym, score, st, thr):
    base = {"date": date, "symbol": sym, "score": score}
    if st is None:
        arms[arm].append({**base, "skipped": True, "skip_reason": "no_bar"})
        return
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
        return
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
            "exit_mode": st.get("exit_mode"),
            "open_gap": st.get("open_gap"),
            "scratched": st.get("scratched"),
            "hit_3pct": float(st.get("full_ret", st["ret"])) >= thr,
        }
    )


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
    ap.add_argument("--tight-gap-ok", type=float, default=0.01)
    ap.add_argument("--min-peak", type=float, default=0.01)
    ap.add_argument("--max-pnl", type=float, default=0.0)
    ap.add_argument("--no-fund-gate", action="store_true")
    args = ap.parse_args()
    args.fund_gate = not args.no_fund_gate

    import pandas as pd
    from vm25_scorer import VM25Scorer
    from backtest_v3_pipeline import volume_gc_asof, fund_gate_ok as fund_gate_pipeline

    print("=== K Execution A/B Backtest ===", flush=True)
    print(
        f"{args.start}~{args.end} top_n={args.top_n} gap_ok={args.gap_ok} "
        f"tight={args.tight_gap_ok} min_peak={args.min_peak}",
        flush=True,
    )

    kpath = ROOT / "data/kline_cache/kline_all.parquet"
    if not kpath.exists():
        kpath = ROOT / "kline_all.parquet"
    kdf = pd.read_parquet(kpath)
    kdf["date"] = kdf["date"].astype(str).str[:10]
    kdf["symbol"] = kdf["symbol"].astype(str).map(_bare)
    kdf = kdf[~kdf["symbol"].str.startswith(("8", "4"))]
    groups = {
        s: g.sort_values("date").reset_index(drop=True) for s, g in kdf.groupby("symbol")
    }
    cal_sym = "600519" if "600519" in groups else next(iter(groups))
    dates = sorted(d for d in groups[cal_sym]["date"].unique() if args.start <= d <= args.end)

    scorer = VM25Scorer(prefer=args.prefer)
    assert scorer.load()
    print(f"days={len(dates)} symbols={len(groups)}", flush=True)

    def settler_t2(g, bi, buy, cost_rt, weight, mode):
        return settle_t2_close(g, bi, buy, cost_rt, weight, mode)

    def settler_ks(g, bi, buy, cost_rt, weight, mode):
        return settle_k_timestop(
            g, bi, buy, cost_rt, weight, mode, min_peak=args.min_peak, max_pnl=args.max_pnl
        )

    arms = {
        "A0_gapsoft_t2": [],
        "K_timestop": [],
        "K_entry_tight": [],
        "K_both": [],
    }
    t0 = time.time()
    scratch_n = 0

    for di, date in enumerate(dates):
        picks = pick_candidates_vm25(
            groups, date, args, scorer, volume_gc_asof, fund_gate_pipeline
        )
        for p in picks:
            sym, ai = p["symbol"], p["ai"]
            g = groups[sym]
            score = p.get("score")

            st_a0 = entry_gap_soft_custom(
                g, ai, sym, args.cost_rt, args.limit_frac, args.gap_ok, settler_t2
            )
            st_ks = entry_gap_soft_custom(
                g, ai, sym, args.cost_rt, args.limit_frac, args.gap_ok, settler_ks
            )
            st_et = entry_gap_soft_custom(
                g, ai, sym, args.cost_rt, args.limit_frac, args.tight_gap_ok, settler_t2
            )
            st_both = entry_gap_soft_custom(
                g, ai, sym, args.cost_rt, args.limit_frac, args.tight_gap_ok, settler_ks
            )

            append_trade(arms, "A0_gapsoft_t2", date, sym, score, st_a0, args.threshold)
            append_trade(arms, "K_timestop", date, sym, score, st_ks, args.threshold)
            append_trade(arms, "K_entry_tight", date, sym, score, st_et, args.threshold)
            append_trade(arms, "K_both", date, sym, score, st_both, args.threshold)
            if st_ks and st_ks.get("scratched"):
                scratch_n += 1

        if (di + 1) % 5 == 0 or di == 0 or di == len(dates) - 1:
            print(
                f"  [{di+1}/{len(dates)}] {date} picks={len(picks)} "
                f"elapsed={int(time.time()-t0)}s",
                flush=True,
            )

    kpis = [summarize(arms[k], k, args.threshold) for k in arms]
    # enrich exit stats
    for k, trades in arms.items():
        filled = [t for t in trades if not t.get("skipped")]
        scratches = sum(1 for t in filled if t.get("scratched"))
        for kpi in kpis:
            if kpi["arm"] == k:
                kpi["n_scratch"] = scratches
                kpi["scratch_rate"] = float(scratches / max(len(filled), 1))
                modes = {}
                for t in filled:
                    em = t.get("exit_mode") or "?"
                    modes[em] = modes.get(em, 0) + 1
                kpi["exit_modes"] = modes

    base = next(k for k in kpis if k["arm"] == "A0_gapsoft_t2")
    for k in kpis:
        if k["arm"] == "A0_gapsoft_t2" or not base.get("n_filled"):
            k["delta_avg_vs_A0"] = 0.0
            k["delta_total_vs_A0"] = 0.0
            k["delta_dd_vs_A0"] = 0.0
        else:
            k["delta_avg_vs_A0"] = float(k.get("avg_ret", 0) - base.get("avg_ret", 0))
            k["delta_total_vs_A0"] = float(k.get("total_return", 0) - base.get("total_return", 0))
            k["delta_dd_vs_A0"] = float(k.get("max_drawdown", 0) - base.get("max_drawdown", 0))

    # pick best by avg_ret then max_dd
    ranked = sorted(
        [k for k in kpis if k.get("n_filled")],
        key=lambda x: (float(x.get("avg_ret") or -9), float(x.get("max_drawdown") or -9)),
        reverse=True,
    )
    prefer = ranked[0]["arm"] if ranked else "A0_gapsoft_t2"

    out = {
        "protocol": {
            "rank": "VM2.5 + strict GC + hard fund (A0 selection)",
            "A0": "GapSoft C (gap_ok=1.5%) + T+2 close",
            "K_timestop": "same entry; scratch at next open if buy-day peak<1% and open<=cost",
            "K_entry_tight": "GapSoft gap_ok=1% + T+2 close",
            "K_both": "tight entry + timestop",
            "note": "时段过滤(开盘异动/午休)为盘中钟点规则，日频回测无法完整复现",
            "cost_rt": args.cost_rt,
            "top_n": args.top_n,
        },
        "window": {"start": args.start, "end": args.end},
        "scratch_events": scratch_n,
        "summaries": kpis,
        "recommendation": {
            "prefer": prefer,
            "reason": "highest avg_ret among arms (tie-break less negative maxDD)",
        },
        "elapsed_sec": round(time.time() - t0, 1),
    }
    path = ROOT / "output" / "k_execution_backtest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== RESULTS ===", flush=True)
    for s in kpis:
        print(
            f"{s['arm']}: filled={s.get('n_filled')} win={s.get('win_rate', 0):.1%} "
            f"hit3={s.get('hit_3pct_rate', 0):.1%} avg={s.get('avg_ret', 0):.2%} "
            f"total={s.get('total_return', 0):.1%} maxDD={s.get('max_drawdown', 0):.1%} "
            f"scratch={s.get('scratch_rate', 0):.1%} dAvg={s.get('delta_avg_vs_A0', 0):+.2%}",
            flush=True,
        )
    print(f"prefer={prefer} wrote {path}", flush=True)


if __name__ == "__main__":
    main()
