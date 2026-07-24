#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""弱市涨停共性分析：2026-07-15~17（周三~五）。"""
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(os.environ.get("ALPHAPILOT_ROOT", "/home/ubuntu/alphapilot"))
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)

DAYS = ["2026-07-15", "2026-07-16", "2026-07-17"]
OUT = ROOT / "output" / "limitup_weak_market_analysis.json"


def bare(s: str) -> str:
    s = str(s or "").lower().replace("sh", "").replace("sz", "").replace("bj", "")
    return s[-6:]


def limit_pct(sym: str) -> float:
    s = bare(sym)
    if s.startswith(("300", "301", "688")):
        return 0.20
    return 0.10


def main():
    kpath = ROOT / "data/kline_cache/kline_all.parquet"
    if not kpath.exists():
        kpath = ROOT / "kline_all.parquet"
    kdf = pd.read_parquet(kpath)
    kdf["date"] = kdf["date"].astype(str).str[:10]
    kdf["symbol"] = kdf["symbol"].astype(str).map(bare)
    kdf = kdf.sort_values(["symbol", "date"]).reset_index(drop=True)

    imap = {}
    ip = ROOT / "data/stock_industry_map.json"
    if ip.exists():
        imap = json.loads(ip.read_text(encoding="utf-8"))
    cmap = {}
    cp = ROOT / "data/stock_concept_map.json"
    if cp.exists():
        cmap = json.loads(cp.read_text(encoding="utf-8"))

    # chip
    chip = {}
    for p in [ROOT / "chip_data_all.json", ROOT / "data/chip_data_all.json"]:
        if p.exists():
            chip = json.loads(p.read_text(encoding="utf-8"))
            break

    fund = {}
    fh = ROOT / "data/fund_flow_history.json"
    if fh.exists():
        fund = json.loads(fh.read_text(encoding="utf-8"))

    groups = {s: g.reset_index(drop=True) for s, g in kdf.groupby("symbol")}

    day_reports = []
    all_rows = []

    for day in DAYS:
        rows = []
        for sym, g in groups.items():
            idxs = g.index[g["date"] == day]
            if len(idxs) == 0:
                continue
            ai = int(idxs[0])
            if ai < 5:
                continue
            prev = float(g.loc[ai - 1, "close"])
            o = float(g.loc[ai, "open"])
            h = float(g.loc[ai, "high"])
            low = float(g.loc[ai, "low"])
            c = float(g.loc[ai, "close"])
            v = float(g.loc[ai, "volume"] if "volume" in g.columns else g.loc[ai, "amount"])
            if prev <= 0 or c <= 0:
                continue
            chg = c / prev - 1
            lim = limit_pct(sym)
            # 涨停：收盘接近涨停且触及涨停价
            hit_limit = chg >= lim * 0.97 and h >= prev * (1 + lim * 0.97)
            if not hit_limit:
                continue

            # 量能
            vol5 = float(g.loc[ai - 5 : ai - 1, "volume" if "volume" in g.columns else "amount"].astype(float).mean())
            vol_ratio = (v / vol5) if vol5 > 0 else None
            # 近20日均量
            vol20 = float(g.loc[max(0, ai - 20) : ai - 1, "volume" if "volume" in g.columns else "amount"].astype(float).mean()) if ai >= 1 else None
            vol_ratio20 = (v / vol20) if vol20 and vol20 > 0 else None

            # 上升通道：收盘 > MA20 且 MA5 > MA20
            closes = g.loc[:ai, "close"].astype(float)
            ma5 = float(closes.tail(5).mean()) if len(closes) >= 5 else None
            ma20 = float(closes.tail(20).mean()) if len(closes) >= 20 else None
            ma60 = float(closes.tail(60).mean()) if len(closes) >= 60 else None
            uptrend = bool(ma20 and ma5 and c > ma20 and ma5 > ma20)
            above_ma60 = bool(ma60 and c > ma60)

            # 近5日累计收益（不含当日）
            if ai >= 5:
                ret5 = float(g.loc[ai - 1, "close"]) / float(g.loc[ai - 5, "close"]) - 1
            else:
                ret5 = None

            ind = imap.get(sym) or {}
            concepts = []
            ci = cmap.get(sym)
            if isinstance(ci, dict):
                concepts = ci.get("concepts") or ci.get("concept_list") or []
                if isinstance(concepts, str):
                    concepts = [concepts]
            elif isinstance(ci, list):
                concepts = ci

            # 筹码
            ch = chip.get(sym) or chip.get(bare(sym)) or {}
            if isinstance(ch, dict) and "data" in ch and isinstance(ch["data"], dict):
                ch = ch["data"]
            conc70 = ch.get("chipConcentration70") or ch.get("chip_concentration_70")
            conc90 = ch.get("chipConcentration90") or ch.get("chip_concentration_90")
            profit = ch.get("chipProfitRate") or ch.get("chip_profit_rate")

            # 资金 当日/5日
            fh_sym = fund.get(sym) or {}
            main_today = float(fh_sym.get(day, 0) or 0) if isinstance(fh_sym, dict) else 0.0
            dates = sorted([d for d in (fh_sym.keys() if isinstance(fh_sym, dict) else []) if d <= day])
            main5 = float(sum(float(fh_sym[d]) for d in dates[-5:])) if len(dates) >= 3 else None

            # 一字板近似：开盘即涨停
            one_word = o >= prev * (1 + lim * 0.97)

            board = "chinext" if bare(sym).startswith(("300", "301")) else ("star" if bare(sym).startswith("688") else "main")

            rows.append(
                {
                    "date": day,
                    "symbol": sym,
                    "name": ind.get("name") or "",
                    "chg": round(chg * 100, 2),
                    "board": board,
                    "industry_l1": ind.get("industry_l1"),
                    "industry_l2": ind.get("industry_l2"),
                    "industry_l3": ind.get("industry_l3"),
                    "concepts": concepts[:12] if isinstance(concepts, list) else [],
                    "vol_ratio5": round(vol_ratio, 2) if vol_ratio else None,
                    "vol_ratio20": round(vol_ratio20, 2) if vol_ratio20 else None,
                    "uptrend_ma": uptrend,
                    "above_ma60": above_ma60,
                    "ret5_pre": round(ret5 * 100, 2) if ret5 is not None else None,
                    "chip_conc70": conc70,
                    "chip_conc90": conc90,
                    "chip_profit": profit,
                    "main_net_today": main_today,
                    "main_net_5d": main5,
                    "one_word": one_word,
                    "turnover": float(g.loc[ai, "turnover"]) if "turnover" in g.columns else None,
                }
            )

        # 行业/概念计数
        ind_cnt = Counter(r["industry_l1"] for r in rows if r.get("industry_l1"))
        ind3_cnt = Counter(r["industry_l3"] or r["industry_l2"] for r in rows if r.get("industry_l3") or r.get("industry_l2"))
        concept_cnt = Counter()
        for r in rows:
            for c in r.get("concepts") or []:
                if isinstance(c, dict):
                    c = c.get("name") or c.get("concept")
                if c and c not in ("通达信88", "大盘股", "基金重仓", "融资融券", "深股通", "沪股通"):
                    concept_cnt[str(c)] += 1

        # 统计共性
        def pct(cond):
            if not rows:
                return None
            return round(100 * sum(1 for r in rows if cond(r)) / len(rows), 1)

        vr5 = [r["vol_ratio5"] for r in rows if r.get("vol_ratio5") is not None]
        summary = {
            "date": day,
            "n_limit_up": len(rows),
            "by_board": dict(Counter(r["board"] for r in rows)),
            "top_industry_l1": ind_cnt.most_common(12),
            "top_industry_l3": ind3_cnt.most_common(12),
            "top_concepts": concept_cnt.most_common(20),
            "pct_uptrend_ma": pct(lambda r: r["uptrend_ma"]),
            "pct_above_ma60": pct(lambda r: r["above_ma60"]),
            "pct_one_word": pct(lambda r: r["one_word"]),
            "pct_vol_ratio5_ge_1_5": pct(lambda r: (r.get("vol_ratio5") or 0) >= 1.5),
            "pct_vol_ratio5_ge_2": pct(lambda r: (r.get("vol_ratio5") or 0) >= 2.0),
            "pct_main5_pos": pct(lambda r: r.get("main_net_5d") is not None and r["main_net_5d"] > 0),
            "pct_main_today_pos": pct(lambda r: (r.get("main_net_today") or 0) > 0),
            "median_vol_ratio5": round(float(np.median(vr5)), 2) if vr5 else None,
            "median_ret5_pre": round(float(np.median([r["ret5_pre"] for r in rows if r.get("ret5_pre") is not None])), 2)
            if any(r.get("ret5_pre") is not None for r in rows)
            else None,
            "samples": sorted(rows, key=lambda x: -x["chg"])[:25],
        }
        day_reports.append(summary)
        all_rows.extend(rows)
        print(
            f"{day}: limit_up={len(rows)} uptrend={summary['pct_uptrend_ma']}% "
            f"vr>=1.5={summary['pct_vol_ratio5_ge_1_5']}% main5+={summary['pct_main5_pos']}% "
            f"top_ind={summary['top_industry_l1'][:5]}",
            flush=True,
        )

    # 跨日稳定板块：至少两天出现在 top concepts/industries
    ind_days = defaultdict(set)
    con_days = defaultdict(set)
    for dr in day_reports:
        for name, _ in dr["top_industry_l1"][:15]:
            ind_days[name].add(dr["date"])
        for name, _ in dr["top_concepts"][:25]:
            con_days[name].add(dr["date"])

    sticky_ind = sorted(
        [(k, sorted(v), len(v)) for k, v in ind_days.items() if len(v) >= 2],
        key=lambda x: -x[2],
    )
    sticky_con = sorted(
        [(k, sorted(v), len(v)) for k, v in con_days.items() if len(v) >= 2],
        key=lambda x: -x[2],
    )

    # 组合规则回测式覆盖率（在涨停样本上）
    def combo(r):
        return (
            r.get("uptrend_ma")
            and (r.get("vol_ratio5") or 0) >= 1.5
            and (r.get("main_net_5d") is None or r.get("main_net_5d") > 0)
            and not r.get("one_word")  # 可交易：排除一字（难买）
        )

    def combo_strict(r):
        return (
            combo(r)
            and (r.get("vol_ratio20") or 0) >= 1.2
            and (r.get("ret5_pre") is None or -2 <= (r.get("ret5_pre") or 0) <= 15)  # 非高潮末端
        )

    cover = {
        "n_all_limit": len(all_rows),
        "combo_cover_pct": round(100 * sum(1 for r in all_rows if combo(r)) / max(len(all_rows), 1), 1),
        "combo_strict_cover_pct": round(100 * sum(1 for r in all_rows if combo_strict(r)) / max(len(all_rows), 1), 1),
        "combo_tradable_n": sum(1 for r in all_rows if combo(r)),
        "combo_strict_n": sum(1 for r in all_rows if combo_strict(r)),
    }

    # 对比：同日非涨停但 uptrend+量比 的股票次日表现（简易：用 day+1 收益）
    # 只在涨停日池外抽查成本高；这里用涨停样本次日收益分布说明延续性
    next_rets = []
    for r in all_rows:
        g = groups.get(r["symbol"])
        if g is None:
            continue
        idxs = g.index[g["date"] == r["date"]]
        if len(idxs) == 0:
            continue
        ai = int(idxs[0])
        if ai + 1 >= len(g):
            continue
        nr = float(g.loc[ai + 1, "close"]) / float(g.loc[ai, "close"]) - 1
        next_rets.append({"date": r["date"], "symbol": r["symbol"], "next_ret": nr, "combo": combo(r), "one_word": r["one_word"]})

    def avg(xs):
        return round(100 * float(np.mean(xs)), 2) if xs else None

    next_stats = {
        "all_next_avg": avg([x["next_ret"] for x in next_rets]),
        "combo_next_avg": avg([x["next_ret"] for x in next_rets if x["combo"]]),
        "non_oneword_next_avg": avg([x["next_ret"] for x in next_rets if not x["one_word"]]),
        "n_with_next": len(next_rets),
    }

    out = {
        "window": DAYS,
        "note": "Limit-up approximated as close/high near board limit; market was weak (indices severe).",
        "days": day_reports,
        "sticky_industry_l1": sticky_ind[:20],
        "sticky_concepts": sticky_con[:30],
        "combo_coverage": cover,
        "next_day_stats": next_stats,
        "proposed_filter": {
            "name": "weak_market_rotation_combo",
            "logic": [
                "uptrend: close>MA20 and MA5>MA20",
                "volume: vol/vol_ma5 >= 1.5 and vol/vol_ma20 >= 1.2",
                "fund: main_net_5d > 0 (if available)",
                "chip: prefer conc70 in [3,12] if chip present (not too dispersed)",
                "exclude one-word / signal-day near-limit for tradability",
                "sector: industry or concept in sticky inflow/allow list that day",
            ],
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved", OUT)
    print("sticky_ind", sticky_ind[:8])
    print("sticky_con", sticky_con[:12])
    print("combo", cover)
    print("next", next_stats)


if __name__ == "__main__":
    main()
