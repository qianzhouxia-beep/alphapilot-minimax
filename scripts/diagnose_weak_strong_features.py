#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对比弱市日：次日≥3% 强势股 vs 其余股，在 T-1 特征上的差异，寻找可预测组合。"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(os.environ.get("ALPHAPILOT_ROOT", "/home/ubuntu/alphapilot"))
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from weak_rotation_sleeve import (  # noqa: E402
    features_asof,
    load_chip_map,
    load_fund_flow,
    load_industry_map,
    load_kline,
    main_net_5d,
)

DAYS = ["2026-07-15", "2026-07-16", "2026-07-17"]
OUT = ROOT / "output" / "weak_strong_feature_diag.json"


def prev_day(dates, day):
    e = [d for d in dates if d < day]
    return e[-1] if e else None


def main():
    kdf = load_kline()
    dates = sorted(kdf["date"].unique().tolist())
    imap = load_industry_map()
    chip = load_chip_map()
    fund = load_fund_flow()
    groups = {s: g.reset_index(drop=True) for s, g in kdf.groupby("symbol")}

    # 行业涨停密度：用涨停近似（chg>=9.5 main / 19 chinext）
    def day_ret(g, day):
        idxs = g.index[g["date"] == day]
        if len(idxs) == 0:
            return None
        ai = int(idxs[0])
        if ai < 1:
            return None
        prev = float(g.loc[ai - 1, "close"])
        c = float(g.loc[ai, "close"])
        if prev <= 0:
            return None
        return (c / prev - 1) * 100

    reports = []
    for day in DAYS:
        sig = prev_day(dates, day)
        winners, losers, all_f = [], [], []
        ind_strong = Counter()
        ind_total = Counter()

        for sym, g in groups.items():
            ret = day_ret(g, day)
            if ret is None:
                continue
            ind = (imap.get(sym) or {}).get("industry_l1") or "NA"
            ind_total[ind] += 1
            feat = features_asof(g, sig, chip=chip)
            if not feat:
                continue
            feat["main5"] = main_net_5d(fund, sym, sig)
            feat["trade_ret"] = ret
            feat["industry_l1"] = ind
            feat["name"] = (imap.get(sym) or {}).get("name")
            all_f.append(feat)
            if ret >= 3:
                winners.append(feat)
                ind_strong[ind] += 1
            elif ret <= -1:
                losers.append(feat)

        def stats(xs, key, fn=lambda x: x):
            vals = [fn(x[key]) for x in xs if x.get(key) is not None]
            if not vals:
                return None
            return {
                "n": len(vals),
                "mean": round(float(np.mean(vals)), 3),
                "median": round(float(np.median(vals)), 3),
                "p25": round(float(np.percentile(vals, 25)), 3),
                "p75": round(float(np.percentile(vals, 75)), 3),
            }

        def rate(xs, pred):
            return round(100 * sum(1 for x in xs if pred(x)) / len(xs), 1) if xs else None

        # 行业相对强度：当日强势密度
        ind_density = {
            k: round(ind_strong[k] / ind_total[k], 3)
            for k in ind_total
            if ind_total[k] >= 20
        }
        top_ind = sorted(ind_density.items(), key=lambda x: -x[1])[:12]

        # 网格搜索简单规则在 winners 上的 lift
        rules = []
        for up in (True, False):
            for vr_lo, vr_hi in [(0.8, 1.5), (1.0, 2.0), (1.2, 2.5), (1.5, 99), (0.5, 1.2)]:
                for main_pos in (True, False):
                    for ma60 in (True, False):
                        for board_main in (True, False):
                            def pred(x, up=up, vr_lo=vr_lo, vr_hi=vr_hi, main_pos=main_pos, ma60=ma60, board_main=board_main):
                                if up and not x.get("uptrend_ma"):
                                    return False
                                vr = x.get("vol_ratio5") or 0
                                if not (vr_lo <= vr < vr_hi):
                                    return False
                                if main_pos and not (x.get("main5") is not None and x["main5"] > 0):
                                    return False
                                if ma60 and not x.get("above_ma60"):
                                    return False
                                if board_main and x.get("board") != "main":
                                    return False
                                return True

                            sel = [x for x in all_f if pred(x)]
                            if len(sel) < 15:
                                continue
                            hit = sum(1 for x in sel if x["trade_ret"] >= 3)
                            avg = float(np.mean([x["trade_ret"] for x in sel]))
                            base_hit = sum(1 for x in all_f if x["trade_ret"] >= 3) / max(len(all_f), 1)
                            prec = hit / len(sel)
                            rules.append(
                                {
                                    "uptrend": up,
                                    "vr": [vr_lo, vr_hi],
                                    "main5+": main_pos,
                                    "ma60": ma60,
                                    "main_board": board_main,
                                    "n": len(sel),
                                    "prec_ge3": round(100 * prec, 2),
                                    "lift": round(prec / base_hit, 2) if base_hit else None,
                                    "avg_ret": round(avg, 2),
                                }
                            )

        rules.sort(key=lambda x: (-(x["avg_ret"]), -x["lift"] if x["lift"] else 0))
        # 再按 lift 排序取前
        by_lift = sorted(rules, key=lambda x: (-(x["lift"] or 0), -x["avg_ret"]))[:15]
        by_ret = sorted(rules, key=lambda x: (-x["avg_ret"], -(x["lift"] or 0)))[:15]

        # 加入行业密度：T-1 无法知 T 密度，用 T-1 的强势密度作为 sticky
        prev_strong = Counter()
        prev_tot = Counter()
        if sig:
            for sym, g in groups.items():
                ret = day_ret(g, sig)
                if ret is None:
                    continue
                ind = (imap.get(sym) or {}).get("industry_l1") or "NA"
                prev_tot[ind] += 1
                if ret >= 3:
                    prev_strong[ind] += 1
        prev_density = {
            k: prev_strong[k] / prev_tot[k]
            for k in prev_tot
            if prev_tot[k] >= 20
        }
        hot_inds = {k for k, v in prev_density.items() if v >= 0.08}  # 昨日≥8%个股涨超3%
        hot_inds_top = {k for k, _ in sorted(prev_density.items(), key=lambda x: -x[1])[:6]}

        def with_hot(hot_set, extra_pred=None):
            sel = []
            for x in all_f:
                if x.get("industry_l1") not in hot_set:
                    continue
                if extra_pred and not extra_pred(x):
                    continue
                sel.append(x)
            if not sel:
                return None
            return {
                "n": len(sel),
                "prec_ge3": round(100 * sum(1 for x in sel if x["trade_ret"] >= 3) / len(sel), 2),
                "avg_ret": round(float(np.mean([x["trade_ret"] for x in sel])), 2),
                "hot_inds": sorted(hot_set),
            }

        sector_tests = {
            "hot_density_8pct": with_hot(hot_inds),
            "hot_top6": with_hot(hot_inds_top),
            "hot_top6+uptrend": with_hot(hot_inds_top, lambda x: x.get("uptrend_ma")),
            "hot_top6+up+vr_1_2": with_hot(
                hot_inds_top,
                lambda x: x.get("uptrend_ma") and 1.0 <= (x.get("vol_ratio5") or 0) < 2.0,
            ),
            "hot_top6+up+vr_1_2+main5": with_hot(
                hot_inds_top,
                lambda x: x.get("uptrend_ma")
                and 1.0 <= (x.get("vol_ratio5") or 0) < 2.0
                and (x.get("main5") or 0) > 0,
            ),
            "hot_top6+up+vr_mild+main_board": with_hot(
                hot_inds_top,
                lambda x: x.get("uptrend_ma")
                and 0.9 <= (x.get("vol_ratio5") or 0) < 1.8
                and x.get("board") == "main"
                and (x.get("main5") or 0) > 0
                and (x.get("ret5_pre") is None or -2 <= x["ret5_pre"] <= 12),
            ),
        }

        # Top score within best rule
        best_rule_sel = None
        br = sector_tests.get("hot_top6+up+vr_mild+main_board")
        if br and br["n"] > 0:
            sel = [
                x
                for x in all_f
                if x.get("industry_l1") in hot_inds_top
                and x.get("uptrend_ma")
                and 0.9 <= (x.get("vol_ratio5") or 0) < 1.8
                and x.get("board") == "main"
                and (x.get("main5") or 0) > 0
                and (x.get("ret5_pre") is None or -2 <= x["ret5_pre"] <= 12)
            ]
            # rank by relative strength proxy: ret5 + mild vr
            sel.sort(key=lambda x: -((x.get("vol_ratio5") or 0) + (x.get("ret5_pre") or 0) / 10 + (10 if x.get("above_ma60") else 0)))
            top5 = sel[:5]
            best_rule_sel = {
                "n": len(sel),
                "top5": [
                    {
                        "symbol": x["symbol"],
                        "name": x.get("name"),
                        "ind": x.get("industry_l1"),
                        "ret": x["trade_ret"],
                        "vr5": x.get("vol_ratio5"),
                        "ret5": x.get("ret5_pre"),
                    }
                    for x in top5
                ],
                "top5_avg": round(float(np.mean([x["trade_ret"] for x in top5])), 2) if top5 else None,
                "top5_hit_ge3": sum(1 for x in top5 if x["trade_ret"] >= 3),
                "top10_avg": round(float(np.mean([x["trade_ret"] for x in sel[:10]])), 2) if sel else None,
            }

        reports.append(
            {
                "day": day,
                "signal": sig,
                "n_all": len(all_f),
                "n_winners": len(winners),
                "base_ge3_pct": round(100 * len(winners) / max(len(all_f), 1), 2),
                "winner_vs_loser": {
                    "vr5": {"W": stats(winners, "vol_ratio5"), "L": stats(losers, "vol_ratio5")},
                    "ret5_pre": {"W": stats(winners, "ret5_pre"), "L": stats(losers, "ret5_pre")},
                    "uptrend_pct": {"W": rate(winners, lambda x: x.get("uptrend_ma")), "L": rate(losers, lambda x: x.get("uptrend_ma"))},
                    "ma60_pct": {"W": rate(winners, lambda x: x.get("above_ma60")), "L": rate(losers, lambda x: x.get("above_ma60"))},
                    "main5_pos_pct": {
                        "W": rate(winners, lambda x: (x.get("main5") or 0) > 0),
                        "L": rate(losers, lambda x: (x.get("main5") or 0) > 0),
                    },
                    "main_board_pct": {
                        "W": rate(winners, lambda x: x.get("board") == "main"),
                        "L": rate(losers, lambda x: x.get("board") == "main"),
                    },
                    "chip70": {"W": stats(winners, "chip_conc70", float), "L": stats(losers, "chip_conc70", float)},
                },
                "same_day_top_ind_density": top_ind,
                "prev_day_hot_ind": sorted(prev_density.items(), key=lambda x: -x[1])[:10],
                "sector_combo_tests": sector_tests,
                "best_rule_topn": best_rule_sel,
                "top_rules_by_lift": by_lift,
                "top_rules_by_ret": by_ret,
            }
        )
        print(
            f"{day}: winners={len(winners)} base={reports[-1]['base_ge3_pct']}% "
            f"best_top5={best_rule_sel}",
            flush=True,
        )

    OUT.write_text(json.dumps({"days": reports}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved", OUT)


if __name__ == "__main__":
    main()
