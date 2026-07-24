#!/usr/bin/env python3
"""Compare A1_ladder vs A1_permission on days where expo differs."""
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
    apply_market_env_gate,
    build_env_asof,
    fetch_all_index_klines,
    position_exposure_ladder,
    recommend_top_n,
    stock_board,
)
from permission_gate import enrich_env_with_permission, position_exposure_permission


def main():
    ih = fetch_all_index_klines(lmt=500)
    sh = ih.get("sh_main") or []
    dates = [x["date"] for x in sh if "2025-01-01" <= x["date"] <= "2026-07-17"]

    kpath = ROOT / "data/kline_cache/kline_all.parquet"
    if not kpath.exists():
        kpath = ROOT / "kline_all.parquet"
    kdf = pd.read_parquet(kpath)
    kdf["date"] = kdf["date"].astype(str).str[:10]
    kdf["symbol"] = kdf["symbol"].astype(str).map(_bare)
    kdf = kdf[~kdf["symbol"].str.startswith(("8", "4"))]
    groups = {s: g.sort_values("date").reset_index(drop=True) for s, g in kdf.groupby("symbol")}

    imap = {}
    ip = ROOT / "data/stock_industry_map.json"
    if ip.exists():
        imap = json.loads(ip.read_text(encoding="utf-8"))

    diff = []
    for d in dates:
        env = enrich_env_with_permission(build_env_asof(ih, d), asof=d, kdf=kdf)
        f = env["flags"]
        p = env["permission"]
        el = position_exposure_ladder(f)
        ep = position_exposure_permission(f, p)
        if abs(el - ep) > 1e-9:
            diff.append((d, el, ep, p.get("up3_count"), p.get("n_sustained_in"), f.get("market_crash_day")))
    print("diff_days", len(diff))
    for row in diff:
        print(" ", row)

    scorer = VM25Scorer(prefer="opt")
    assert scorer.load()
    cost_rt, thr = 0.0015, 0.03
    day_ret = {"ladder": {}, "perm": {}}
    fills = {"ladder": [], "perm": []}

    for d, el, ep, up3, sus, crash in diff:
        env = enrich_env_with_permission(build_env_asof(ih, d), asof=d, kdf=kdf)
        pool = []
        for sym, g in groups.items():
            idxs = g.index[g["date"] <= d]
            if len(idxs) == 0:
                continue
            ai = int(idxs[-1])
            if str(g.loc[ai, "date"]) != d or ai + 2 >= len(g):
                continue
            lim = limit_pct(sym)
            chg = day_chg(g, ai)
            if near_limit(chg, lim, 0.97) or not volume_gc_asof(g, ai):
                continue
            sub = g.iloc[: ai + 1].copy()
            try:
                r = scorer.score(sub, sym)
            except Exception:
                continue
            if "error" in r:
                continue
            if not fund_gate_ok(scorer.fund_flow.get(sym, {}), d, 5):
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

        def run(name, expo):
            day_ret[name][d] = 0.0
            if expo <= 0:
                return 0
            env["position_exposure"] = expo
            cands = apply_market_env_gate(
                list(pool), env=env, hard_filter=True, mode="hard_only", industry_map=imap
            )
            picks = sorted(cands, key=lambda x: -x["score"])[: recommend_top_n(expo, 2)]
            rets = []
            for p in picks:
                st = settle_tradable(groups[p["symbol"]], p["ai"], cost_rt)
                if not st or st.get("skip"):
                    continue
                scaled = float(st["ret"]) * expo
                rets.append(scaled)
                fills[name].append({"date": d, "symbol": p["symbol"], "ret": scaled, "expo": expo})
            day_ret[name][d] = float(np.mean(rets)) if rets else 0.0
            return len(rets)

        nl = run("ladder", el)
        np_ = run("perm", ep)
        print(
            f"  {d}: pool={len(pool)} lad_e={el} fill={nl} day={day_ret['ladder'][d]*100:.2f}% | "
            f"perm_e={ep} fill={np_} day={day_ret['perm'][d]*100:.2f}% up3={up3} sus={sus} crash={crash}"
        )

    def kpi(name):
        arr = np.array([day_ret[name][d] for d, *_ in diff], float)
        rets = np.array([t["ret"] for t in fills[name]], float)
        return {
            "arm": name,
            "n_days": len(diff),
            "n_filled": len(fills[name]),
            "empty_days": int(sum(1 for d, *_ in diff if abs(day_ret[name][d]) < 1e-12 and not fills[name])),
            "day_avg": float(arr.mean()) if len(arr) else 0.0,
            "total": float(np.prod(1 + arr) - 1) if len(arr) else 0.0,
            "win": float((rets > 0).mean()) if len(rets) else None,
        }

    # empty_days fix: count days with expo<=0 or no fill
    def empty_count(name, expos):
        n = 0
        for (d, el, ep, *_), e in zip(diff, expos):
            expo = el if name == "ladder" else ep
            if expo <= 0 or abs(day_ret[name][d]) < 1e-15 and not any(t["date"] == d for t in fills[name]):
                # if expo>0 but no fill, still "empty opportunity"
                if expo <= 0:
                    n += 1
        return n

    kl, kp = kpi("ladder"), kpi("perm")
    kl["empty_expo0"] = sum(1 for _, el, *_ in diff if el <= 0)
    kp["empty_expo0"] = sum(1 for _, _, ep, *_ in diff if ep <= 0)
    out = {
        "diff_days": [
            {"date": d, "expo_ladder": el, "expo_perm": ep, "up3": u, "sustained": s, "crash": c}
            for d, el, ep, u, s, c in diff
        ],
        "kpi": [kl, kp],
        "delta_perm_minus_ladder": {
            "total_pp": (kp["total"] - kl["total"]) * 100,
            "day_avg_pp": (kp["day_avg"] - kl["day_avg"]) * 100,
            "empty_expo0_ladder": kl["empty_expo0"],
            "empty_expo0_perm": kp["empty_expo0"],
        },
        "fills": fills,
    }
    path = ROOT / "output/permission_vs_ladder_diff_days.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n======== perm vs ladder (diff days) ========")
    for k in (kl, kp):
        print(
            f"{k['arm']}: days={k['n_days']} fills={k['n_filled']} empty0={k['empty_expo0']} "
            f"day_avg={k['day_avg']*100:.3f}% total={k['total']*100:.2f}% win={k['win']}"
        )
    print(
        f"DELTA perm-lad: total {out['delta_perm_minus_ladder']['total_pp']:+.2f}pp "
        f"day_avg {out['delta_perm_minus_ladder']['day_avg_pp']:+.3f}pp "
        f"empty0 {kl['empty_expo0']}→{kp['empty_expo0']}"
    )
    print("saved", path)


if __name__ == "__main__":
    main()
