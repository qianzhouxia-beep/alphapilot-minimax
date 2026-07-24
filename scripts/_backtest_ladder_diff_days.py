#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Focused A1_cur vs A1_ladder on days where expos differ (severe, no crash)."""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/ubuntu/alphapilot")
os.chdir(ROOT)

from vm25_scorer import VM25Scorer, _bare
from backtest_v3_pipeline import volume_gc_asof, fund_gate_ok
from backtest_v3_tradable_gated import settle_tradable, near_limit, day_chg, limit_pct
from market_env_gate import (
    INDEXES,
    apply_market_env_gate,
    _flags_from_indexes,
    _trend_from_klines,
    fetch_all_index_klines,
    position_exposure,
    position_exposure_legacy,
    recommend_top_n,
    stock_board,
)


def build_flags(ih, date):
    idxs = {}
    for k in INDEXES:
        kl = [x for x in (ih.get(k) or []) if x["date"] <= date]
        st = _trend_from_klines(kl)
        st["name"] = INDEXES[k]["name"]
        idxs[k] = st
    flags = _flags_from_indexes(idxs)
    return flags, {
        "asof": date,
        "indexes": idxs,
        "flags": flags,
        "position_exposure": position_exposure(flags),
    }


def main():
    ih = fetch_all_index_klines(lmt=500)
    sh = ih.get("sh_main") or []
    dates_all = [x["date"] for x in sh if x["date"] >= "2024-01-01"]
    diff_days = []
    for d in dates_all:
        flags, _ = build_flags(ih, d)
        if not flags.get("market_severe"):
            continue
        cur = position_exposure_legacy(flags)
        lad = position_exposure(flags)
        if cur != lad:
            diff_days.append(d)
    print("diff_days", diff_days)

    scorer = VM25Scorer(prefer="opt")
    assert scorer.load()
    imap = {}
    ip = ROOT / "data/stock_industry_map.json"
    if ip.exists():
        imap = json.loads(ip.read_text(encoding="utf-8"))

    kpath = ROOT / "data/kline_cache/kline_all.parquet"
    if not kpath.exists():
        kpath = ROOT / "kline_all.parquet"
    kdf = pd.read_parquet(kpath)
    kdf["date"] = kdf["date"].astype(str).str[:10]
    kdf["symbol"] = kdf["symbol"].astype(str).map(_bare)
    kdf = kdf[~kdf["symbol"].str.startswith(("8", "4"))]
    groups = {s: g.sort_values("date").reset_index(drop=True) for s, g in kdf.groupby("symbol")}

    cost_rt = 0.0015
    thr = 0.03
    arms = {"A1_cur": [], "A1_ladder": []}
    day_ret = {"A1_cur": {}, "A1_ladder": {}}

    for date in diff_days:
        flags, env = build_flags(ih, date)
        expo_cur = position_exposure_legacy(flags)
        expo_lad = position_exposure(flags)
        pool = []
        for sym, g in groups.items():
            idxs = g.index[g["date"] <= date]
            if len(idxs) == 0:
                continue
            ai = int(idxs[-1])
            if str(g.loc[ai, "date"]) != date or ai + 2 >= len(g):
                continue
            lim = limit_pct(sym)
            chg = day_chg(g, ai)
            if near_limit(chg, lim, 0.97):
                continue
            if not volume_gc_asof(g, ai):
                continue
            sub = g.iloc[: ai + 1].copy()
            try:
                r = scorer.score(sub, sym)
            except Exception:
                continue
            if "error" in r:
                continue
            fh = scorer.fund_flow.get(sym, {})
            if not fund_gate_ok(fh, date, 5):
                continue
            ind = imap.get(sym) or {}
            pool.append(
                {
                    "symbol": sym,
                    "ai": ai,
                    "score": float(r["score"]),
                    "industry_l1": ind.get("industry_l1") if isinstance(ind, dict) else None,
                    "board": stock_board(sym),
                }
            )

        def run_arm(name, expo):
            day_ret[name][date] = 0.0
            if expo <= 0:
                return 0
            cands = apply_market_env_gate(
                list(pool), env=env, hard_filter=True, mode="hard_only", industry_map=imap
            )
            n = recommend_top_n(expo, 2)
            picks = sorted(cands, key=lambda x: -x["score"])[:n]
            rets = []
            for p in picks:
                st = settle_tradable(groups[p["symbol"]], p["ai"], cost_rt)
                if not st or st.get("skip"):
                    arms[name].append({"date": date, "symbol": p["symbol"], "skipped": True})
                    continue
                scaled = float(st["ret"]) * expo
                rets.append(scaled)
                arms[name].append(
                    {
                        "date": date,
                        "symbol": p["symbol"],
                        "skipped": False,
                        "ret": scaled,
                        "ret_raw": float(st["ret"]),
                        "exposure": expo,
                        "hit_3pct": scaled >= thr,
                    }
                )
            day_ret[name][date] = float(np.mean(rets)) if rets else 0.0
            return len(rets)

        n_c = run_arm("A1_cur", expo_cur)
        n_l = run_arm("A1_ladder", expo_lad)
        print(
            f"  {date}: pool={len(pool)} cur_expo={expo_cur} fill={n_c} "
            f"lad_expo={expo_lad} fill={n_l} day_lad={day_ret['A1_ladder'][date]*100:.2f}%"
        )

    def kpi(name):
        arr = np.array([day_ret[name][d] for d in diff_days], float)
        filled = [t for t in arms[name] if not t.get("skipped")]
        rets = np.array([t["ret"] for t in filled], float) if filled else np.array([])
        return {
            "arm": name,
            "n_diff_days": len(diff_days),
            "n_filled": len(filled),
            "day_avg": float(arr.mean()) if len(arr) else 0.0,
            "total": float(np.prod(1 + arr) - 1) if len(arr) else 0.0,
            "win": float((rets > 0).mean()) if len(rets) else None,
            "hit3": float((rets >= thr).mean()) if len(rets) else None,
        }

    k_cur, k_lad = kpi("A1_cur"), kpi("A1_ladder")
    out = {
        "diff_days": diff_days,
        "kpi": [k_cur, k_lad],
        "delta_ladder_minus_cur": {
            "total_pp": (k_lad["total"] - k_cur["total"]) * 100,
            "day_avg_pp": (k_lad["day_avg"] - k_cur["day_avg"]) * 100,
        },
        "trades": arms,
        "note": "Only days where ladder expo differs from legacy severe→0",
    }
    path = ROOT / "output/ladder_vs_cur_diff_days.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n======== diff-days only ========")
    for k in (k_cur, k_lad):
        print(
            f"{k['arm']}: days={k['n_diff_days']} fills={k['n_filled']} "
            f"day_avg={k['day_avg']*100:.3f}% total={k['total']*100:.2f}% "
            f"win={k['win']} hit3={k['hit3']}"
        )
    print(
        f"DELTA lad-cur: total {out['delta_ladder_minus_cur']['total_pp']:+.2f}pp "
        f"day_avg {out['delta_ladder_minus_cur']['day_avg_pp']:+.3f}pp"
    )
    print("saved", path)


if __name__ == "__main__":
    main()
