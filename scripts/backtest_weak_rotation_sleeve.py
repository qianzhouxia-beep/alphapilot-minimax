#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""弱市袖套回测：目标抓涨幅≥3%（不要求涨停）。信号=T-1，评估=T。"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(os.environ.get("ALPHAPILOT_ROOT", "/home/ubuntu/alphapilot"))
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from weak_rotation_sleeve import (  # noqa: E402
    STRONG_CHG_PCT,
    TOP_N,
    build_strong_universe,
    features_asof,
    industry_density,
    load_chip_map,
    load_fund_flow,
    load_industry_map,
    load_kline,
    main_net_5d,
    scan_sleeve,
)

DAYS = ["2026-07-15", "2026-07-16", "2026-07-17"]
OUT = ROOT / "output" / "weak_rotation_sleeve_backtest.json"


def prev_trade_day(dates, day):
    e = [d for d in dates if d < day]
    return e[-1] if e else None


def summarize_strong(rows, chip, fund, groups):
    if not rows:
        return {}
    feats = []
    for r in rows:
        g = groups.get(r["symbol"])
        if g is None:
            continue
        # 描述性：用信号日前一日？用户要强势股共同点 → 用当日收盘特征（标注 descriptive）
        f = features_asof(g, r["date"], chip=chip)
        if not f:
            continue
        f["main_net_5d"] = main_net_5d(fund, r["symbol"], r["date"])
        f["industry_l1"] = r.get("industry_l1")
        f["chg"] = r["chg"]
        feats.append(f)

    def pct(cond):
        return round(100 * sum(1 for x in feats if cond(x)) / len(feats), 1) if feats else None

    vr = [x["vol_ratio5"] for x in feats if x.get("vol_ratio5") is not None]
    ret5 = [x["ret5_pre"] for x in feats if x.get("ret5_pre") is not None]
    c70 = [float(x["chip_conc70"]) for x in feats if x.get("chip_conc70") is not None]
    return {
        "n": len(rows),
        "n_with_feat": len(feats),
        "pct_uptrend_ma": pct(lambda x: x.get("uptrend_ma")),
        "pct_above_ma60": pct(lambda x: x.get("above_ma60")),
        "pct_vr_mild_0_8_1_8": pct(lambda x: 0.8 <= (x.get("vol_ratio5") or 0) < 1.8),
        "pct_vr5_ge_1_5": pct(lambda x: (x.get("vol_ratio5") or 0) >= 1.5),
        "pct_main5_pos": pct(lambda x: x.get("main_net_5d") is not None and x["main_net_5d"] > 0),
        "pct_main_board": pct(lambda x: x.get("board") == "main"),
        "pct_chip_8_18": pct(
            lambda x: x.get("chip_conc70") is not None and 8 <= float(x["chip_conc70"]) <= 18
        ),
        "median_vr5": round(float(np.median(vr)), 2) if vr else None,
        "median_ret5_incl_day": round(float(np.median(ret5)), 2) if ret5 else None,
        "median_chip70": round(float(np.median(c70)), 2) if c70 else None,
        "median_chg": round(float(np.median([r["chg"] for r in rows])), 2),
        "top_industry": Counter(r.get("industry_l1") for r in rows if r.get("industry_l1")).most_common(10),
        "top_industry_density": sorted(
            industry_density(rows, load_industry_map()).items(), key=lambda x: -x[1]
        )[:10],
    }


def run_mode(label, dates, strong, kdf, **scan_kw):
    day_reports = []
    all_rets, all_hits, all_n = [], 0, 0
    for day in DAYS:
        sig = prev_trade_day(dates, day)
        if not sig:
            continue
        result = scan_sleeve(
            asof_signal=sig,
            trade_day=day,
            kdf=kdf,
            strong_by_day={k: v for k, v in strong.items() if k <= sig},
            top_n=TOP_N,
            **scan_kw,
        )
        picked = result["picked"]
        pool = result.get("pool_preview") or picked
        hit = [p for p in picked if p.get("hit_strong")]
        rets = [p["trade_ret"] for p in picked if p.get("trade_ret") is not None]
        pool_rets = [p["trade_ret"] for p in pool if p.get("trade_ret") is not None]
        avg = round(float(np.mean(rets)), 2) if rets else None
        pool_avg = round(float(np.mean(pool_rets)), 2) if pool_rets else None
        prec = round(100 * len(hit) / len(picked), 1) if picked else None
        for r in rets:
            all_rets.append(r)
            all_n += 1
        all_hits += len(hit)
        # 命中名单：TopN 中真正 ≥3% 的票
        caught = [
            {"symbol": p["symbol"], "name": p.get("name"), "ret": p.get("trade_ret"), "ind": p.get("industry_l1")}
            for p in picked
            if p.get("hit_strong")
        ]
        day_reports.append(
            {
                "trade_day": day,
                "signal_asof": sig,
                "n_strong_ge3": len(strong.get(day) or []),
                "breadth": result.get("breadth"),
                "hot_industries": result.get("hot_industries"),
                "defensive_mode": result.get("defensive_mode"),
                "skip_reason": result.get("skip_reason"),
                "sleeve_n_passed": result.get("n_passed"),
                "sleeve_topn": [
                    {
                        "symbol": p["symbol"],
                        "name": p.get("name"),
                        "score": p.get("score"),
                        "industry_l1": p.get("industry_l1"),
                        "trade_ret": p.get("trade_ret"),
                        "hit_strong": p.get("hit_strong"),
                        "vol_ratio5": round(p["vol_ratio5"], 2) if p.get("vol_ratio5") else None,
                        "ret5_pre": round(p["ret5_pre"], 2) if p.get("ret5_pre") is not None else None,
                        "uptrend_ma": p.get("uptrend_ma"),
                        "chip_conc70": p.get("chip_conc70"),
                    }
                    for p in picked
                ],
                "caught_ge3": caught,
                "precision_ge3_pct": prec,
                "avg_trade_ret": avg,
                "pool30_avg_ret": pool_avg,
                "pool30_hit_ge3": sum(1 for p in pool if p.get("hit_strong")),
                "n_hit_ge3": len(hit),
            }
        )
        print(
            f"[{label}] {day}: strong={len(strong.get(day) or [])} "
            f"pass={result.get('n_passed')} skip={result.get('skip_reason')} "
            f"hit={len(hit)}/{len(picked)} avg={avg} hot={[x[0] for x in (result.get('hot_industries') or [])[:4]]}",
            flush=True,
        )
    summary = {
        "topn_picks": all_n,
        "topn_hit_ge3": all_hits,
        "topn_precision_ge3_pct": round(100 * all_hits / all_n, 1) if all_n else None,
        "topn_avg_ret": round(float(np.mean(all_rets)), 2) if all_rets else None,
        "topn_median_ret": round(float(np.median(all_rets)), 2) if all_rets else None,
        "days_traded": sum(1 for r in day_reports if r["sleeve_topn"]),
        "days_skipped": sum(1 for r in day_reports if r.get("skip_reason")),
    }
    return day_reports, summary


def main():
    print("loading...", flush=True)
    kdf = load_kline()
    dates = sorted(kdf["date"].unique().tolist())
    imap = load_industry_map()
    chip = load_chip_map()
    fund = load_fund_flow()
    groups = {s: g.reset_index(drop=True) for s, g in kdf.groupby("symbol")}

    look = []
    for d in DAYS:
        p = prev_trade_day(dates, d)
        if p:
            look.append(p)
        look.append(d)
    # extra prev for breadth
    p0 = prev_trade_day(dates, min(look))
    if p0:
        look = [p0] + look
    look = sorted(set(look))
    strong = build_strong_universe(kdf, imap, look, thr_pct=STRONG_CHG_PCT)
    for d in DAYS:
        print(f"strong>={STRONG_CHG_PCT}% {d}: {len(strong.get(d, []))}", flush=True)

    # 模式A：广度坍塌空仓（默认生产）
    os.environ["WEAK_TRADE_ON_COLLAPSE"] = "0"
    days_a, sum_a = run_mode("collapse_empty", dates, strong, kdf)

    # 模式B：坍塌日切防御行业仍交易
    os.environ["WEAK_TRADE_ON_COLLAPSE"] = "1"
    days_b, sum_b = run_mode("collapse_defensive", dates, strong, kdf, force_trade=True)

    pooled = []
    for d in DAYS:
        pooled.extend(strong.get(d, []))
    traits = summarize_strong(pooled, chip, fund, groups)
    traits_by_day = {d: summarize_strong(strong.get(d, []), chip, fund, groups) for d in DAYS}

    out = {
        "window": DAYS,
        "target": f"trade_day return >= {STRONG_CHG_PCT}%",
        "signal": "T-1: ret5 relative strength + mild vol_ratio + uptrend + hot industry density + main board",
        "mode_collapse_empty": {"days": days_a, "summary": sum_a},
        "mode_collapse_defensive": {"days": days_b, "summary": sum_b},
        "strong_ge3_common_traits": {
            "note": "descriptive same-day features of stocks with ret>=3% (not the signal)",
            "pooled": traits,
            "by_day": traits_by_day,
        },
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved", OUT)
    print("A collapse_empty", json.dumps(sum_a, ensure_ascii=False))
    print("B collapse_defensive", json.dumps(sum_b, ensure_ascii=False))


if __name__ == "__main__":
    main()
