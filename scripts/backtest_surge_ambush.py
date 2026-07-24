#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三臂回测：Baseline / AmbushWatch / AmbushApply。

协议: T 信号 → T+1 开买(近涨停跳过) → T+2 收卖 → 成本 15bp。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/ubuntu/alphapilot")
os.chdir(str(ROOT))
import sys
sys.path.insert(0, str(ROOT))

from vm25_scorer import VM25Scorer, _bare, _load_json
from backtest_v3_pipeline import volume_gc_asof, fund_gate_ok
from backtest_v3_tradable_gated import (
    day_chg,
    limit_pct,
    max_drawdown,
    near_limit,
    settle_tradable,
)
from soft_universe_gate import apply_universe_gate
from consec_inflow import load_fund_hist, consec_for_symbol
from surge_ambush_score import score_ambush


def _ma(series: pd.Series, n: int) -> float:
    if len(series) < n:
        return float("nan")
    return float(series.tail(n).mean())


def is_downtrend_channel(g: pd.DataFrame, ai: int) -> bool:
    if ai < 60:
        return False
    sub = g.iloc[: ai + 1]
    c = sub["close"].astype(float)
    c0 = float(c.iloc[-1])
    ma5, ma20, ma60 = _ma(c, 5), _ma(c, 20), _ma(c, 60)
    if any(math.isnan(x) for x in (ma5, ma20, ma60)):
        return False
    bear = (ma5 < ma20) and (ma20 < ma60) and (c0 < ma60)
    return bool(bear and c0 < ma20)


def build_wide_pool(
    groups: dict,
    date: str,
    score_cap: int,
    limit_frac: float,
    fund_hist: dict,
) -> list[dict]:
    """宽池：非近涨停 + 资金硬底过 + 非下跌通道 + 有未来结算日。"""
    cheap = []
    for sym, g in groups.items():
        idxs = g.index[g["date"] <= date]
        if len(idxs) == 0:
            continue
        ai = int(idxs[-1])
        if str(g.loc[ai, "date"]) != date:
            continue
        if ai + 2 >= len(g):
            continue
        lim = limit_pct(sym)
        chg = day_chg(g, ai)
        if chg is not None and near_limit(chg, lim, limit_frac):
            continue
        fh = fund_hist.get(sym, {})
        if not fund_gate_ok(fh, date, 5):
            continue
        if is_downtrend_channel(g, ai):
            continue
        cheap.append({"symbol": sym, "ai": ai})
    return cheap[:score_cap]


def recall_surge(groups: dict, date: str, surge_thr: float) -> set[str]:
    surge = set()
    for sym, g in groups.items():
        idxs = g.index[g["date"] == date]
        if len(idxs) == 0:
            continue
        ai = int(idxs[-1])
        if ai + 1 >= len(g):
            continue
        c0 = float(g.loc[ai, "close"])
        c1 = float(g.loc[ai + 1, "close"])
        if c0 > 0 and (c1 / c0 - 1.0) >= surge_thr:
            surge.add(sym)
    return surge


def recall_metric(ranked: list[dict], surge: set[str]) -> dict | None:
    if not surge:
        return None
    pool = {x["symbol"] for x in ranked}
    hit = len(pool & surge)
    return {"surge_n": len(surge), "pool_hit": hit, "recall": hit / len(surge)}


def push_trades(
    arms: dict,
    arm_key: str,
    ranked: list[dict],
    date: str,
    cost_rt: float,
    thr: float,
    groups: dict,
):
    picks = ranked[:2]
    for p in picks:
        if p["symbol"] not in groups:
            continue
        g = groups[p["symbol"]]
        st = settle_tradable(g, p["ai"], cost_rt)
        base = {
            "date": date,
            "symbol": p["symbol"],
            "arm": p.get("arm"),
            "score": p.get("score"),
            "surge_ambush_tier": p.get("surge_ambush_tier"),
            "surge_ambush_score": p.get("surge_ambush_score"),
        }
        if st is None:
            arms[arm_key].append({**base, "skipped": True, "skip_reason": "no_bar"})
            continue
        if st.get("skip"):
            arms[arm_key].append({**base, "skipped": True, "skip_reason": st["skip"]})
            continue
        ret = float(st["ret"])
        arms[arm_key].append(
            {
                **base,
                "skipped": False,
                "ret": ret,
                "buy": st["buy"],
                "sell": st["sell"],
                "buy_date": st["buy_date"],
                "sell_date": st["sell_date"],
                "win": ret > 0,
                "hit_3pct": ret >= thr,
                "hit_5pct": ret >= 0.05,
            }
        )


def summarize(trades: list[dict], name: str, thr: float, cal_days: list[str]) -> dict:
    filled = [t for t in trades if not t.get("skipped")]
    skipped = [t for t in trades if t.get("skipped")]
    by = defaultdict(list)
    for t in filled:
        by[t["date"]].append(float(t["ret"]))
    day_rets = []
    for d in cal_days:
        if d in by:
            day_rets.append(float(np.mean(by[d])))
        else:
            day_rets.append(0.0)
    day_arr = np.array(day_rets, dtype=float)
    rets = np.array([t["ret"] for t in filled], dtype=float) if filled else np.array([])
    return {
        "arm": name,
        "n_trades": len(filled),
        "n_skipped": len(skipped),
        "n_signal_days": len([d for d in cal_days if d in by]),
        "win_rate": float((rets > 0).mean()) if len(rets) else None,
        "hit_3pct": float((rets >= thr).mean()) if len(rets) else None,
        "hit_5pct": float((rets >= 0.05).mean()) if len(rets) else None,
        "avg_ret": float(rets.mean()) if len(rets) else None,
        "median_ret": float(np.median(rets)) if len(rets) else None,
        "day_avg_ret": float(day_arr.mean()) if len(day_arr) else None,
        "day_win_rate": float((day_arr > 0).mean()) if len(day_arr) else None,
        "max_dd": max_drawdown(day_arr) if len(day_arr) else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Surge Ambush 三臂回测")
    ap.add_argument("--start", default="2026-01-16")
    ap.add_argument("--end", default="2026-07-15")
    ap.add_argument("--score-cap", type=int, default=120)
    ap.add_argument("--limit-frac", type=float, default=0.97)
    ap.add_argument("--cost-rt", type=float, default=0.0015)
    ap.add_argument("--threshold", type=float, default=0.03)
    ap.add_argument("--surge-thr", type=float, default=0.05)
    ap.add_argument("--mult-strong", type=float, default=1.15)
    ap.add_argument("--mult-mid", type=float, default=1.05)
    ap.add_argument("--mult-base", type=float, default=0.85)
    ap.add_argument("--max-stocks", type=int, default=0)
    args = ap.parse_args()

    print("=== Surge Ambush 三臂回测 ===", flush=True)
    print(
        f"window {args.start}~{args.end} cap={args.score_cap} "
        f"base={args.mult_base} strong={args.mult_strong} mid={args.mult_mid}",
        flush=True,
    )

    scorer = VM25Scorer()
    if not scorer.load():
        raise SystemExit("VM25Scorer load failed")

    # ── Load klines ──
    kpath = ROOT / "data" / "kline_cache" / "kline_all.parquet"
    if not kpath.exists():
        kpath = ROOT / "kline_all.parquet"
    kdf = pd.read_parquet(kpath)
    kdf["date"] = kdf["date"].astype(str).str[:10]
    kdf["symbol"] = kdf["symbol"].astype(str).map(_bare)

    symbols = sorted(kdf["symbol"].unique())
    if args.max_stocks:
        symbols = symbols[: args.max_stocks]

    groups = {
        sym: g.sort_values("date").reset_index(drop=True)
        for sym, g in kdf[kdf["symbol"].isin(symbols)].groupby("symbol")
    }

    cal_sym = "600519" if "600519" in groups else next(iter(groups))
    dates = sorted(
        d for d in groups[cal_sym]["date"].unique() if args.start <= d <= args.end
    )
    print(f"stocks={len(groups)} days={len(dates)}", flush=True)

    fund_hist = load_fund_hist()

    arms: dict[str, list] = {"Baseline": [], "AmbushWatch": [], "AmbushApply": []}
    day_meta = []
    t0 = time.time()

    for di, date in enumerate(dates):
        cheap = build_wide_pool(
            groups, date, args.score_cap, args.limit_frac, fund_hist
        )
        if not cheap:
            day_meta.append(
                {
                    "date": date,
                    "cheap_n": 0,
                    "scored_n": 0,
                    "n_b": 0,
                    "n_w": 0,
                    "n_a": 0,
                }
            )
            continue

        # ── Score ──
        scored = []
        for x in cheap:
            sym, ai = x["symbol"], x["ai"]
            g = groups[sym]
            sub = g.iloc[: ai + 1].copy()
            try:
                r = scorer.score(sub, sym)
            except Exception:
                continue
            if "error" in r:
                continue
            scored.append(
                {"symbol": sym, "ai": ai, "score_raw": float(r["score"])}
            )
            if len(scored) % 40 == 0:
                print(f"    score {len(scored)}/{len(cheap)}", flush=True)

        if not scored:
            day_meta.append(
                {
                    "date": date,
                    "cheap_n": len(cheap),
                    "scored_n": 0,
                    "n_b": 0,
                    "n_w": 0,
                    "n_a": 0,
                }
            )
            continue

        # ── Universe gate ──
        gc_set = set()
        for r in scored:
            g = groups[r["symbol"]]
            if volume_gc_asof(g, r["ai"]):
                gc_set.add(r["symbol"])

        items = [
            {
                "symbol": r["symbol"],
                "score": r["score_raw"],
                "gc": r["symbol"] in gc_set,
            }
            for r in scored
        ]
        log_fn = print if di == 0 else lambda *a, **kw: None
        items_out, _ = apply_universe_gate(
            items,
            gc_bare=gc_set,
            gc_set=set(),
            bypass_bare=set(),
            log=log_fn,
        )
        arm_map = {x["symbol"]: x.get("arm", "B") for x in items_out}

        baseline_pool = []
        watch_pool = []
        apply_pool = []

        for r in scored:
            sym = r["symbol"]
            arm = arm_map.get(sym, "B")
            base = r["score_raw"]

            if arm != "B":
                row = {"symbol": sym, "arm": arm, "score": base, "ai": r["ai"]}
                baseline_pool.append(row)
                watch_pool.append(row)
                apply_pool.append(row)
                continue

            consec = consec_for_symbol(sym, fund_hist, asof=date)
            s = score_ambush(
                {"symbol": sym},
                consec=consec,
                wind_row=None,
                prefer=set(),
                zt_sectors=set(),
                zt_codes=set(),
                labels=[],
            )

            bl_row = {"symbol": sym, "arm": "B", "score": base * args.mult_base, "ai": r["ai"]}
            baseline_pool.append(bl_row)

            w_row = {"symbol": sym, "arm": "B", "score": base * args.mult_base, "ai": r["ai"]}
            w_row.update(s)
            watch_pool.append(w_row)

            a_row = {"symbol": sym, "arm": "B", "ai": r["ai"]}
            a_row.update(s)
            if s["surge_ambush_tier"] == "strong":
                a_row["score"] = base * args.mult_base * args.mult_strong
            elif s["surge_ambush_tier"] == "mid":
                a_row["score"] = base * args.mult_base * args.mult_mid
            else:
                a_row["score"] = base * args.mult_base
            apply_pool.append(a_row)

        def sorter(pool):
            return sorted(pool, key=lambda x: -float(x.get("score") or 0))

        push_trades(
            arms, "Baseline", sorter(baseline_pool),
            date, args.cost_rt, args.threshold, groups,
        )
        push_trades(
            arms, "AmbushWatch", sorter(watch_pool),
            date, args.cost_rt, args.threshold, groups,
        )
        push_trades(
            arms, "AmbushApply", sorter(apply_pool),
            date, args.cost_rt, args.threshold, groups,
        )

        surge = recall_surge(groups, date, args.surge_thr)
        day_meta.append(
            {
                "date": date,
                "cheap_n": len(cheap),
                "scored_n": len(scored),
                "n_b": len(baseline_pool),
                "n_w": len(watch_pool),
                "n_a": len(apply_pool),
                "surge_n": len(surge),
                "recall_bl": recall_metric(sorter(baseline_pool), surge),
                "recall_w": recall_metric(sorter(watch_pool), surge),
                "recall_a": recall_metric(sorter(apply_pool), surge),
            }
        )
        print(
            f"  {date}: cheap={len(cheap)} scored={len(scored)} "
            f"nB={len(baseline_pool)} nW={len(watch_pool)} nA={len(apply_pool)} "
            f"surge={len(surge)} ({di+1}/{len(dates)})",
            flush=True,
        )

    # ── Summaries ──
    summaries = {
        k: summarize(v, k, args.threshold, dates) for k, v in arms.items()
    }

    def arm_b_pct(trades: list) -> float | None:
        filled = [t for t in trades if not t.get("skipped")]
        if not filled:
            return None
        return sum(1 for t in filled if t.get("arm") == "B") / len(filled)

    for k in arms:
        summaries[k]["top2_armB_pct"] = arm_b_pct(arms[k])

    tier_hist = {"strong": 0, "mid": 0, "plain": 0}
    for t in arms["AmbushWatch"]:
        tier = t.get("surge_ambush_tier") or "plain"
        if tier not in tier_hist:
            tier_hist[tier] = 0
        tier_hist[tier] += 1

    report = {
        "config": vars(args),
        "summaries": summaries,
        "ambush_tier_dist": tier_hist,
        "day_meta": day_meta,
    }

    elapsed = time.time() - t0
    print(f"\n=== 完成 {elapsed:.0f}s ===", flush=True)
    for k, v in report["summaries"].items():
        print(f"\n  {k}:")
        for kk, vv in v.items():
            if kk != "arm":
                print(f"    {kk}: {vv}")
    print(f"\n  tier_dist: {tier_hist}", flush=True)

    out_path = ROOT / "output" / "backtest_surge_ambush.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"saved {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())