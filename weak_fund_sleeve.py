#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""弱势资金轮动袖套（小仓）

仅在主臂 nuclear（position_exposure=0：severe+crash_day）时启用研究臂。
用个股资金流按行业聚合，判断 3/5/10 日流入结构，再在「持续流入」板块里选 1 只。

与主臂关系：
  - 主臂：满仓/半仓 Top2；severe 非瀑布 → 薄仓 Top1（expo=0.25）；nuclear 才空仓
  - 袖套：仅 nuclear 日研究，默认不自动下单；不与薄仓叠仓
  - 资金口径：3日定锋面、5日定骨架、10日过滤假流入（一日游）
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent

SLEEVE_EXPO = float(os.environ.get("WEAK_FUND_SLEEVE_EXPO", "0.25"))
TOP_N = int(os.environ.get("WEAK_FUND_SLEEVE_TOPN", "1"))
# 行业入选：3日净流入>0 且 5日净流入>0；10日不能显著流出（阈值可调）
MIN_IND_STOCKS = int(os.environ.get("WEAK_FUND_MIN_IND_N", "8"))
STOCK_POS_DAYS_5 = int(os.environ.get("WEAK_FUND_STOCK_POS_DAYS", "3"))  # 近5日至少N日流入


def bare(sym: str) -> str:
    s = str(sym or "").lower().replace("sh", "").replace("sz", "").replace("bj", "")
    return s[-6:]


def _load_json(path: Path, default=None):
    if not path.exists():
        return default if default is not None else {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


def load_industry_map() -> dict[str, str]:
    raw = _load_json(ROOT / "data/stock_industry_map.json", {})
    out = {}
    for k, v in raw.items():
        if isinstance(v, dict):
            out[bare(k)] = v.get("industry_l1") or v.get("industry") or ""
        else:
            out[bare(k)] = str(v)
    return out


def load_fund() -> dict[str, dict]:
    raw = _load_json(ROOT / "data/fund_flow_history.json", {})
    return {bare(k): v for k, v in raw.items() if isinstance(v, dict)}


def trading_days_asof(calendar: list[str], asof: str, n: int) -> list[str]:
    days = [d for d in calendar if d <= asof]
    return days[-n:]


def fund_window_sum(hist: dict, days: list[str]) -> float | None:
    vals = []
    for d in days:
        if d in hist:
            try:
                vals.append(float(hist[d]))
            except Exception:
                pass
    if not vals:
        return None
    return float(sum(vals))


def fund_pos_days(hist: dict, days: list[str]) -> int:
    n = 0
    for d in days:
        if d in hist:
            try:
                if float(hist[d]) > 0:
                    n += 1
            except Exception:
                pass
    return n


def classify_flow(sum3: float | None, sum5: float | None, sum10: float | None) -> str:
    """sustained_in | pulse_in | outflow | mixed"""
    if sum5 is None and sum3 is None:
        return "unknown"
    s3 = sum3 if sum3 is not None else 0.0
    s5 = sum5 if sum5 is not None else 0.0
    s10 = sum10 if sum10 is not None else 0.0
    if s3 > 0 and s5 > 0 and s10 >= -abs(s5) * 0.5:
        return "sustained_in"
    if s3 > 0 and s5 <= 0:
        return "pulse_in"  # 一日/短锋面，慎做
    if s5 < 0 and s10 < 0:
        return "outflow"
    return "mixed"


def aggregate_industry_flow(
    fund: dict[str, dict],
    imap: dict[str, str],
    calendar: list[str],
    asof: str,
) -> dict[str, dict]:
    d3 = trading_days_asof(calendar, asof, 3)
    d5 = trading_days_asof(calendar, asof, 5)
    d10 = trading_days_asof(calendar, asof, 10)
    acc = defaultdict(lambda: {"sum3": 0.0, "sum5": 0.0, "sum10": 0.0, "n": 0})
    for sym, hist in fund.items():
        ind = imap.get(sym)
        if not ind:
            continue
        s3 = fund_window_sum(hist, d3)
        s5 = fund_window_sum(hist, d5)
        s10 = fund_window_sum(hist, d10)
        if s5 is None and s3 is None:
            continue
        a = acc[ind]
        a["sum3"] += s3 or 0.0
        a["sum5"] += s5 or 0.0
        a["sum10"] += s10 or 0.0
        a["n"] += 1
    out = {}
    for ind, a in acc.items():
        if a["n"] < MIN_IND_STOCKS:
            continue
        cls = classify_flow(a["sum3"], a["sum5"], a["sum10"])
        out[ind] = {
            "industry": ind,
            "n_stocks": a["n"],
            "sum3": round(a["sum3"], 0),
            "sum5": round(a["sum5"], 0),
            "sum10": round(a["sum10"], 0),
            "class": cls,
            "sum3_yi": round(a["sum3"] / 1e8, 2),
            "sum5_yi": round(a["sum5"] / 1e8, 2),
            "sum10_yi": round(a["sum10"] / 1e8, 2),
        }
    return out


def score_stock(
    hist: dict,
    days5: list[str],
    days10: list[str],
    close: float,
    ma20: float | None,
    ret5: float | None,
) -> float:
    s5 = fund_window_sum(hist, days5) or 0.0
    s10 = fund_window_sum(hist, days10) or 0.0
    pos = fund_pos_days(hist, days5)
    # 资金持续 + 价格在均线上方 + 近5日温和
    score = np.tanh(s5 / 5e7) * 40 + np.tanh(s10 / 1e8) * 15 + pos * 4
    if ma20 and close > ma20:
        score += 8
    if ret5 is not None:
        score += max(0.0, 10 - abs(ret5 - 0.02) * 80)  # 甜区约 +2%
    return float(score)


def scan_weak_fund_sleeve(
    asof: str,
    kdf: pd.DataFrame | None = None,
    top_n: int = TOP_N,
    expo: float | None = None,
) -> dict[str, Any]:
    """asof = 信号日（收盘后）。返回袖套候选。"""
    if kdf is None:
        for p in (ROOT / "data/kline_cache/kline_all.parquet", ROOT / "kline_all.parquet"):
            if p.exists():
                kdf = pd.read_parquet(p)
                break
        if kdf is None:
            raise FileNotFoundError("kline parquet missing")
        kdf = kdf.copy()
        kdf["date"] = kdf["date"].astype(str).str[:10]
        kdf["symbol"] = kdf["symbol"].astype(str).map(bare)

    imap = load_industry_map()
    fund = load_fund()
    cal = sorted(kdf["date"].unique().tolist())
    if asof not in cal:
        # snap to last available
        le = [d for d in cal if d <= asof]
        if not le:
            return {"asof": asof, "picked": [], "skip_reason": "no_calendar"}
        asof = le[-1]

    ind_flow = aggregate_industry_flow(fund, imap, cal, asof)
    allow = [
        v
        for v in ind_flow.values()
        if v["class"] == "sustained_in" and v["sum5"] > 0
    ]
    allow.sort(key=lambda x: (-x["sum5"], -x["sum3"]))
    allow_names = {x["industry"] for x in allow[:12]}
    deny = [v for v in ind_flow.values() if v["class"] == "outflow"]
    deny.sort(key=lambda x: x["sum5"])

    days5 = trading_days_asof(cal, asof, 5)
    days10 = trading_days_asof(cal, asof, 10)
    groups = {s: g.sort_values("date").reset_index(drop=True) for s, g in kdf.groupby("symbol")}

    cands = []
    for sym, g in groups.items():
        ind = imap.get(sym)
        if not ind or ind not in allow_names:
            continue
        hist = fund.get(sym)
        if not hist:
            continue
        idxs = g.index[g["date"] == asof]
        if len(idxs) == 0:
            continue
        ai = int(idxs[0])
        if ai < 20:
            continue
        close = float(g.loc[ai, "close"])
        prev = float(g.loc[ai - 1, "close"]) if ai >= 1 else close
        # 近涨停不买（信号日）
        chg = close / prev - 1 if prev > 0 else 0
        if chg >= 0.09:
            continue
        ma20 = float(g.loc[ai - 19 : ai, "close"].mean())
        if close < ma20 * 0.98:  # 明显跌破均线不要
            continue
        ret5 = None
        if ai >= 5:
            c0 = float(g.loc[ai - 5, "close"])
            if c0 > 0:
                ret5 = close / c0 - 1
        if ret5 is not None and (ret5 < -0.08 or ret5 > 0.18):
            continue
        pos5 = fund_pos_days(hist, days5)
        s5 = fund_window_sum(hist, days5)
        if s5 is None or s5 <= 0 or pos5 < STOCK_POS_DAYS_5:
            continue
        sc = score_stock(hist, days5, days10, close, ma20, ret5)
        cands.append(
            {
                "symbol": sym,
                "name": "",
                "industry_l1": ind,
                "score": round(sc, 3),
                "fund_5d_sum": round(s5, 0),
                "fund_5d_pos_days": pos5,
                "fund_3d_sum": fund_window_sum(hist, trading_days_asof(cal, asof, 3)),
                "ret5": None if ret5 is None else round(ret5, 4),
                "chg": round(chg, 4),
                "close": close,
                "ai": ai,
            }
        )

    cands.sort(key=lambda x: -x["score"])
    # 行业分散
    picked = []
    seen_ind = set()
    for c in cands:
        ind = c["industry_l1"]
        if ind in seen_ind:
            continue
        picked.append(c)
        seen_ind.add(ind)
        if len(picked) >= top_n:
            break

    return {
        "asof": asof,
        "sleeve_exposure": SLEEVE_EXPO if expo is None else expo,
        "top_n": top_n,
        "allow_industries": allow[:15],
        "deny_industries_sample": deny[:10],
        "n_candidates": len(cands),
        "picked": picked,
        "skip_reason": None if picked else ("no_sustained_industry" if not allow else "no_stock_pass"),
        "rules": {
            "industry": "class=sustained_in (3d>0 & 5d>0 & 10d not deep outflow)",
            "stock": f"5d_net>0 and pos_days>={STOCK_POS_DAYS_5}, not near-limit, above MA20",
            "windows": "3d tip / 5d spine / 10d anti-fake",
        },
    }


def pick_for_today() -> dict[str, Any]:
    """生产：读 market env，仅 expo=0 时出袖套票。"""
    env = _load_json(ROOT / "output/market_env_snapshot.json", {})
    rec = _load_json(ROOT / "output/daily_recommend.json", {})
    expo = rec.get("position_exposure")
    if expo is None:
        expo = env.get("position_exposure")
    try:
        expo = float(expo if expo is not None else 1.0)
    except Exception:
        expo = 1.0
    flags = rec.get("market_env_flags") or env.get("flags") or {}
    asof = (
        rec.get("asof")
        or rec.get("date")
        or env.get("asof")
        or env.get("date")
        or datetime.now().strftime("%Y-%m-%d")
    )
    asof = str(asof)[:10]

    if expo > 0:
        out = {
            "asof": asof,
            "enabled": False,
            "reason": "main_arm_active",
            "position_exposure": expo,
            "flags": flags,
            "picked": [],
            "note": "主臂有仓位时不启用袖套，避免叠仓",
        }
    else:
        scan = scan_weak_fund_sleeve(asof, top_n=TOP_N, expo=SLEEVE_EXPO)
        out = {
            "enabled": True,
            "reason": "nuclear_expo_zero",
            "position_exposure_main": expo,
            "auto_trade": False,
            "flags": flags,
            **scan,
        }
    path = ROOT / "output/weak_fund_sleeve_picks.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    out["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


if __name__ == "__main__":
    r = pick_for_today()
    print("enabled", r.get("enabled"), "reason", r.get("reason") or r.get("skip_reason"))
    print("allow", [x["industry"] for x in (r.get("allow_industries") or [])[:8]])
    print("picked", [(p.get("symbol"), p.get("industry_l1"), p.get("score")) for p in r.get("picked") or []])
    print("saved output/weak_fund_sleeve_picks.json")
