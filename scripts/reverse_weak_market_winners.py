#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""弱市反向复盘：大盘下跌日，谁在涨？属于哪些行业？近5日板块资金是否持续流入？

输出: output/reverse_weak_market_winners.json
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/ubuntu/alphapilot")
OUT = ROOT / "output/reverse_weak_market_winners.json"


def bare(s: str) -> str:
    s = str(s)
    return s[-6:] if len(s) >= 6 else s


def main() -> int:
    kpath = ROOT / "data/kline_cache/kline_all.parquet"
    if not kpath.exists():
        kpath = ROOT / "kline_all.parquet"
    kdf = pd.read_parquet(kpath)
    kdf["date"] = kdf["date"].astype(str).str[:10]
    kdf["symbol"] = kdf["symbol"].astype(str).map(bare)
    kdf = kdf[~kdf["symbol"].str.startswith(("8", "4"))]

    # 指数代理：用沪深300或上证成分近似 — 用全市场等权日收益
    by_day = kdf.groupby("date").apply(
        lambda g: pd.Series(
            {
                "mkt_ret": float((g["close"] / g["open"] - 1).mean()),
                "n": len(g),
                "up_pct": float((g["close"] > g["open"]).mean()),
            }
        ),
        include_groups=False,
    )
    by_day = by_day.sort_index()
    # 近 15 个交易日里市场均收益 < -1% 视为「大跌日」
    recent = by_day.tail(20)
    down_days = recent[recent["mkt_ret"] < -0.01].index.tolist()
    if not down_days:
        down_days = recent.nsmallest(3, "mkt_ret").index.tolist()

    imap = {}
    ip = ROOT / "data/stock_industry_map.json"
    if ip.exists():
        raw = json.loads(ip.read_text(encoding="utf-8"))
        # normalize
        for k, v in raw.items():
            code = bare(k)
            if isinstance(v, dict):
                imap[code] = v.get("industry_l1") or v.get("industry") or v.get("name") or "?"
            else:
                imap[code] = str(v)

    # 板块资金：sector_flow_3day / today（结构因源而异，尽量解析）
    sector_flow = {}
    for name in ("sector_flow_3day.json", "sector_flow_today.json"):
        p = ROOT / "data" / name
        if p.exists():
            sector_flow[name] = json.loads(p.read_text(encoding="utf-8"))

    rot = {}
    rp = ROOT / "output/sector_rotation_snapshot.json"
    if rp.exists():
        rot = json.loads(rp.read_text(encoding="utf-8"))

    env = {}
    ep = ROOT / "output/market_env_snapshot.json"
    if ep.exists():
        env = json.loads(ep.read_text(encoding="utf-8"))

    # 个股资金 5 日
    fund = {}
    fp = ROOT / "data/fund_flow_history.json"
    if fp.exists():
        fund = json.loads(fp.read_text(encoding="utf-8"))

    winners_by_day = {}
    industry_hits = defaultdict(lambda: {"n_up": 0, "n_strong": 0, "examples": []})

    for d in down_days:
        day = kdf[kdf["date"] == d].copy()
        if day.empty:
            continue
        day["ret"] = day["close"] / day["open"] - 1
        # 涨 >=3% / >=5% / 近涨停
        strong = day[day["ret"] >= 0.03].sort_values("ret", ascending=False)
        rows = []
        for _, r in strong.head(80).iterrows():
            sym = r["symbol"]
            ind = imap.get(sym, "?")
            # 近5日主力净额
            hist = fund.get(sym) or fund.get(bare(sym)) or {}
            dates = sorted(hist.keys(), reverse=True)[:5]
            nets = [float(hist[x]) for x in dates if x in hist]
            pos_days = sum(1 for x in nets if x > 0)
            sum5 = float(sum(nets)) if nets else None
            rows.append(
                {
                    "symbol": sym,
                    "ret": round(float(r["ret"]), 4),
                    "industry_l1": ind,
                    "fund_5d_pos_days": pos_days,
                    "fund_5d_sum": None if sum5 is None else round(sum5, 0),
                    "fund_pattern": (
                        "sustained_in"
                        if pos_days >= 4 and (sum5 or 0) > 0
                        else "mostly_in"
                        if pos_days >= 3 and (sum5 or 0) > 0
                        else "one_day_pulse"
                        if pos_days <= 1
                        else "mixed"
                    ),
                }
            )
            industry_hits[ind]["n_up"] += 1
            if float(r["ret"]) >= 0.05:
                industry_hits[ind]["n_strong"] += 1
            if len(industry_hits[ind]["examples"]) < 5:
                industry_hits[ind]["examples"].append(f"{sym}({float(r['ret'])*100:.1f}%)")

        # 资金模式占比
        pat = defaultdict(int)
        for x in rows:
            pat[x["fund_pattern"]] += 1
        winners_by_day[d] = {
            "mkt_ret": round(float(recent.loc[d, "mkt_ret"]), 4),
            "up_pct": round(float(recent.loc[d, "up_pct"]), 4),
            "n_up_ge_3pct": int((day["ret"] >= 0.03).sum()),
            "n_up_ge_5pct": int((day["ret"] >= 0.05).sum()),
            "fund_pattern_counts": dict(pat),
            "top_winners": rows[:30],
        }

    # 行业汇总
    ind_rank = sorted(
        (
            {
                "industry": k,
                "n_up": v["n_up"],
                "n_strong": v["n_strong"],
                "examples": v["examples"],
            }
            for k, v in industry_hits.items()
            if k and k != "?"
        ),
        key=lambda x: (-x["n_strong"], -x["n_up"]),
    )[:25]

    # 从 rotation snapshot 抽 allow/deny
    rot_summary = {}
    if rot:
        rot_summary = {
            "mode": rot.get("mode"),
            "allow_industries": (rot.get("allow_industries") or rot.get("industry_allow") or [])[:20],
            "deny_industries": (rot.get("deny_industries") or rot.get("industry_deny") or [])[:20],
            "keys": list(rot.keys())[:30],
        }
        # try common structures
        for key in ("industries", "sector_status", "l1_status", "dual"):
            if key in rot and isinstance(rot[key], dict):
                allow, deny, neutral = [], [], []
                for name, st in list(rot[key].items())[:200]:
                    if isinstance(st, dict):
                        s = st.get("status") or st.get("state") or st.get("action")
                    else:
                        s = st
                    s = str(s).lower()
                    if "allow" in s or s == "ok":
                        allow.append(name)
                    elif "deny" in s or "reject" in s:
                        deny.append(name)
                    else:
                        neutral.append(name)
                rot_summary[key + "_allow_sample"] = allow[:15]
                rot_summary[key + "_deny_sample"] = deny[:15]

    report = {
        "thesis": "weak_market_winners_via_sustained_sector_fund_flow",
        "market_env_snapshot": {
            "flags": env.get("flags") or env.get("market_env_flags"),
            "position_exposure": env.get("position_exposure"),
        },
        "down_days": down_days,
        "market_recent_tail": {
            d: {
                "mkt_ret": round(float(recent.loc[d, "mkt_ret"]), 4),
                "up_pct": round(float(recent.loc[d, "up_pct"]), 4),
            }
            for d in recent.tail(10).index
        },
        "winners_by_down_day": winners_by_day,
        "industry_rank_on_down_days": ind_rank,
        "sector_rotation_snapshot": rot_summary,
        "implications": [
            "If n_up_ge_3pct >> 0 on down days, empty-book is a risk choice not a data void",
            "Prefer sustained_in / mostly_in fund patterns over one_day_pulse",
            "Industry rank suggests which sleeves to allow when market_severe",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== 弱市反向复盘 ===")
    print("down_days", down_days)
    print("expo", env.get("position_exposure"), "flags", env.get("flags") or env.get("market_env_flags"))
    for d in down_days:
        w = winners_by_day.get(d) or {}
        print(
            f"  {d}: mkt={w.get('mkt_ret')} up%={w.get('up_pct')} "
            f">=3%:{w.get('n_up_ge_3pct')} >=5%:{w.get('n_up_ge_5pct')} "
            f"fund_pat={w.get('fund_pattern_counts')}"
        )
    print("\n行业（跌市中强势出现次数）:")
    for x in ind_rank[:12]:
        print(f"  {x['industry']}: up={x['n_up']} strong5%={x['n_strong']} eg={x['examples'][:3]}")
    print("saved", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
