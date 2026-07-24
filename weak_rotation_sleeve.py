#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""弱市轮动卫星袖套：大盘 severe / exposure=0 时，用组合条件抓局部强势股。

经验（2026-07-15~17 诊断）：
  - 次日≥3% 强势股在 T-1 的共性：5日收益显著强于弱势股、上升通道占比更高、主板、
    量比温和（非放量高潮）、落在「昨日强势密度」靠前的行业。
  - 错误做法：用量比≥1.5 追高 → 易选到高潮股次日回落。
  - 广度骤降日（强势股数腰斩）→ 袖套空仓或切防御行业，避免追昨日热点。

信号仅用 T-1 收盘可得信息。
"""
from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent

STRONG_CHG_PCT = float(os.environ.get("WEAK_STRONG_CHG", "3.0"))
# 温和量比区间（避免高潮）
VOL_RATIO5_LO = float(os.environ.get("WEAK_VR5_LO", "0.8"))
VOL_RATIO5_HI = float(os.environ.get("WEAK_VR5_HI", "1.8"))
RET5_PRE_MIN = float(os.environ.get("WEAK_RET5_MIN", "-1.0"))
RET5_PRE_MAX = float(os.environ.get("WEAK_RET5_MAX", "12.0"))
CHIP_CONC70_MIN = float(os.environ.get("WEAK_CHIP70_MIN", "8.0"))
CHIP_CONC70_MAX = float(os.environ.get("WEAK_CHIP70_MAX", "18.0"))
HOT_IND_TOPK = int(os.environ.get("WEAK_HOT_TOPK", "6"))
MIN_IND_SIZE = int(os.environ.get("WEAK_MIN_IND_SIZE", "20"))
BREADTH_COLLAPSE_RATIO = float(os.environ.get("WEAK_BREADTH_COLLAPSE", "0.55"))
# 信号日全市场≥3%家数过低 → 局部行情不可持续，袖套空仓
BREADTH_MIN_ABS = int(os.environ.get("WEAK_BREADTH_MIN", "400"))
TOP_N = int(os.environ.get("WEAK_SLEEVE_TOPN", "10"))
MAX_EXPOSURE = float(os.environ.get("WEAK_SLEEVE_EXPOSURE", "0.25"))
DEFENSIVE_INDS = {
    "公用事业",
    "煤炭",
    "石油石化",
    "银行",
    "交通运输",
    "钢铁",
}


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


def load_chip_map() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for cp in (ROOT / "chip_data_all.json", ROOT / "data" / "chip_data_all.json"):
        raw = _load_json(cp, {})
        if not raw:
            continue
        data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
        if not isinstance(data, dict):
            continue
        for k, v in data.items():
            if not isinstance(v, dict):
                continue
            if "chipConcentration70" not in v and "chipProfitRate" not in v:
                continue
            out[bare(k)] = v
        if out:
            break
    return out


def load_industry_map() -> dict[str, dict]:
    raw = _load_json(ROOT / "data" / "stock_industry_map.json", {})
    return {bare(k): v for k, v in raw.items() if isinstance(v, dict)}


def load_fund_flow() -> dict[str, dict]:
    raw = _load_json(ROOT / "data" / "fund_flow_history.json", {})
    return {bare(k): v for k, v in raw.items() if isinstance(v, dict)}


def load_kline() -> pd.DataFrame:
    for p in (ROOT / "data/kline_cache/kline_all.parquet", ROOT / "kline_all.parquet"):
        if p.exists():
            df = pd.read_parquet(p)
            df["date"] = df["date"].astype(str).str[:10]
            df["symbol"] = df["symbol"].astype(str).map(bare)
            return df.sort_values(["symbol", "date"]).reset_index(drop=True)
    raise FileNotFoundError("kline parquet not found")


def _vol_col(g: pd.DataFrame) -> str:
    return "volume" if "volume" in g.columns else "amount"


def features_asof(g: pd.DataFrame, asof: str, chip: dict | None = None) -> dict[str, Any] | None:
    idxs = g.index[g["date"] == asof]
    if len(idxs) == 0:
        return None
    ai = int(idxs[0])
    if ai < 20:
        return None
    vc = _vol_col(g)
    c = float(g.loc[ai, "close"])
    o = float(g.loc[ai, "open"])
    v = float(g.loc[ai, vc])
    prev = float(g.loc[ai - 1, "close"]) if ai >= 1 else None
    if c <= 0 or prev is None or prev <= 0:
        return None

    closes = g.loc[:ai, "close"].astype(float)
    ma5 = float(closes.tail(5).mean())
    ma20 = float(closes.tail(20).mean())
    ma60 = float(closes.tail(60).mean()) if ai >= 59 else None

    vol5 = float(g.loc[ai - 5 : ai - 1, vc].astype(float).mean())
    vol20 = float(g.loc[max(0, ai - 20) : ai - 1, vc].astype(float).mean())
    vr5 = (v / vol5) if vol5 > 0 else None
    vr20 = (v / vol20) if vol20 > 0 else None

    ret5 = float(g.loc[ai, "close"]) / float(g.loc[ai - 5, "close"]) - 1 if ai >= 5 else None
    chg = c / prev - 1

    code = bare(str(g.loc[ai, "symbol"]))
    lim = 0.20 if code.startswith(("300", "301", "688")) else 0.10
    near_limit = chg >= lim * 0.97
    one_word = o >= prev * (1 + lim * 0.97)

    feat = {
        "symbol": code,
        "asof": asof,
        "close": c,
        "chg": chg,
        "ma5": ma5,
        "ma20": ma20,
        "ma60": ma60,
        "uptrend_ma": bool(c > ma20 and ma5 > ma20),
        "above_ma60": bool(ma60 and c > ma60),
        "vol_ratio5": vr5,
        "vol_ratio20": vr20,
        "ret5_pre": ret5 * 100 if ret5 is not None else None,
        "near_limit": near_limit,
        "one_word": one_word,
        "board": "chinext"
        if code.startswith(("300", "301"))
        else ("star" if code.startswith("688") else "main"),
    }
    if chip:
        ch = chip.get(code) or {}
        feat["chip_conc70"] = ch.get("chipConcentration70")
        feat["chip_conc90"] = ch.get("chipConcentration90")
        feat["chip_profit"] = ch.get("chipProfitRate")
    return feat


def main_net_5d(fund: dict[str, dict], sym: str, asof: str) -> float | None:
    fh = fund.get(bare(sym)) or {}
    dates = sorted(d for d in fh if str(d)[:10] <= asof)
    if len(dates) < 3:
        return None
    return float(sum(float(fh[d] or 0) for d in dates[-5:]))


def day_return(g: pd.DataFrame, day: str) -> float | None:
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


def build_strong_universe(
    kdf: pd.DataFrame,
    imap: dict,
    days: list[str],
    thr_pct: float = STRONG_CHG_PCT,
) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    groups = {s: g.reset_index(drop=True) for s, g in kdf.groupby("symbol")}
    for day in days:
        rows = []
        for sym, g in groups.items():
            ret = day_return(g, day)
            if ret is None or ret < thr_pct:
                continue
            ind = imap.get(sym) or {}
            rows.append(
                {
                    "date": day,
                    "symbol": sym,
                    "name": ind.get("name") or "",
                    "chg": round(ret, 2),
                    "industry_l1": ind.get("industry_l1"),
                    "industry_l2": ind.get("industry_l2"),
                    "industry_l3": ind.get("industry_l3"),
                }
            )
        out[day] = sorted(rows, key=lambda x: -x["chg"])
    return out


def industry_density(
    strong_rows: list[dict],
    imap: dict,
    universe_syms: list[str] | None = None,
) -> dict[str, float]:
    """行业内强势股占比。"""
    strong_cnt = Counter(r.get("industry_l1") for r in strong_rows if r.get("industry_l1"))
    if universe_syms is None:
        # 用行业映射规模近似
        tot = Counter()
        for sym, meta in imap.items():
            ind = meta.get("industry_l1")
            if ind:
                tot[ind] += 1
    else:
        tot = Counter()
        for sym in universe_syms:
            ind = (imap.get(sym) or {}).get("industry_l1")
            if ind:
                tot[ind] += 1
    dens = {}
    for ind, n in strong_cnt.items():
        t = tot.get(ind, 0)
        if t >= MIN_IND_SIZE:
            dens[ind] = n / t
    return dens


def hot_industries_from_day(
    strong_by_day: dict[str, list[dict]],
    day: str,
    imap: dict,
    topk: int = HOT_IND_TOPK,
) -> list[tuple[str, float]]:
    dens = industry_density(strong_by_day.get(day) or [], imap)
    return sorted(dens.items(), key=lambda x: -x[1])[:topk]


def detect_breadth_collapse(strong_by_day: dict[str, list[dict]], signal_day: str, dates: list[str]) -> dict:
    """信号日相对前一日，强势股广度是否坍塌。"""
    earlier = [d for d in dates if d <= signal_day]
    if len(earlier) < 2:
        return {"collapse": False, "n": len(strong_by_day.get(signal_day) or []), "prev_n": None, "ratio": None}
    cur = earlier[-1]
    prev = earlier[-2]
    n = len(strong_by_day.get(cur) or [])
    pn = len(strong_by_day.get(prev) or [])
    ratio = (n / pn) if pn > 0 else 1.0
    collapse = (pn > 0 and ratio <= BREADTH_COLLAPSE_RATIO) or n < BREADTH_MIN_ABS
    return {"collapse": collapse, "n": n, "prev_n": pn, "ratio": round(ratio, 3) if pn else None}


def passes_combo(
    feat: dict,
    main5: float | None,
    industry: str | None,
    hot_inds: set[str],
    defensive_mode: bool = False,
) -> tuple[bool, list[str]]:
    reasons = []
    # 核心：相对强弱（T-1 近5日）
    ret5 = feat.get("ret5_pre")
    if ret5 is None or ret5 < RET5_PRE_MIN or ret5 > RET5_PRE_MAX:
        reasons.append("ret5_out")
    if not feat.get("uptrend_ma"):
        reasons.append("no_uptrend")
    vr = feat.get("vol_ratio5")
    if vr is None or not (VOL_RATIO5_LO <= vr < VOL_RATIO5_HI):
        reasons.append("vr_not_mild")
    if feat.get("board") != "main":
        reasons.append("non_main")
    if feat.get("one_word") or feat.get("near_limit"):
        reasons.append("near_limit")
    # 信号日当天已大涨的，次日更易回吐
    if (feat.get("chg") or 0) >= 0.05:
        reasons.append("signal_day_extended")
    if main5 is None or main5 <= 0:
        reasons.append("main5_neg")
    # 行业：优先粘性热点
    allow = set(hot_inds)
    if defensive_mode:
        allow |= DEFENSIVE_INDS
    if not industry or industry not in allow:
        reasons.append("not_hot_ind")
    # 筹码：有则约束，无则跳过
    c70 = feat.get("chip_conc70")
    if c70 is not None:
        if not (CHIP_CONC70_MIN <= float(c70) <= CHIP_CONC70_MAX):
            reasons.append("chip_conc")
    return (len(reasons) == 0), reasons


def combo_score(feat: dict, main5: float | None, ind_density: float = 0.0) -> float:
    """排序：偏好「已转强但未高潮」——ret5 靠近 2~5%，量比温和；禁止按最大涨幅排序。"""
    ret5 = float(feat.get("ret5_pre") or 0)
    vr5 = float(feat.get("vol_ratio5") or 1.0)
    # 甜区：近5日约 +3%，量比约 1.2
    ret_score = 12 - abs(ret5 - 3.0) * 1.6
    vr_score = 10 - abs(vr5 - 1.2) * 7
    s = ret_score + vr_score + ind_density * 35
    if feat.get("uptrend_ma"):
        s += 6
    if main5 is not None and main5 > 0:
        s += 4
    c70 = feat.get("chip_conc70")
    if c70 is not None and CHIP_CONC70_MIN <= float(c70) <= CHIP_CONC70_MAX:
        s += 2
    return round(s, 2)


def diversify_picks(cands: list[dict], top_n: int, max_per_ind: int = 2) -> list[dict]:
    """行业分散，避免同一热点扎堆。"""
    picked = []
    ind_cnt: Counter = Counter()
    for c in cands:
        ind = c.get("industry_l1") or "_"
        if ind_cnt[ind] >= max_per_ind:
            continue
        picked.append(c)
        ind_cnt[ind] += 1
        if len(picked) >= top_n:
            break
    return picked


def scan_sleeve(
    asof_signal: str,
    trade_day: str | None = None,
    kdf: pd.DataFrame | None = None,
    strong_by_day: dict | None = None,
    top_n: int = TOP_N,
    force_trade: bool = False,
) -> dict[str, Any]:
    if kdf is None:
        kdf = load_kline()
    imap = load_industry_map()
    fund = load_fund_flow()
    chip = load_chip_map()
    dates = sorted(kdf["date"].unique().tolist())
    groups = {s: g.reset_index(drop=True) for s, g in kdf.groupby("symbol")}

    if strong_by_day is None:
        look = [d for d in dates if d <= asof_signal][-5:]
        strong_by_day = build_strong_universe(kdf, imap, look)

    breadth = detect_breadth_collapse(strong_by_day, asof_signal, dates)
    hot = hot_industries_from_day(strong_by_day, asof_signal, imap, HOT_IND_TOPK)
    # 粘性热点：信号日 TopK ∩ 再前一日 Top12；或信号日密度≥0.25 的新主线
    earlier = [d for d in dates if d < asof_signal]
    prev2 = earlier[-1] if earlier else None
    hot_prev = hot_industries_from_day(strong_by_day, prev2, imap, 12) if prev2 else []
    prev_set = {k for k, _ in hot_prev}
    dens_map = dict(hot)
    # 仅保留两日重叠行业（降一日游资源股）；不足则回退信号日 Top4
    sticky_hot = [(n, d) for n, d in hot if n in prev_set]
    if len(sticky_hot) < 2:
        sticky_hot = list(hot)[:4]
    hot_inds = {k for k, _ in sticky_hot}
    defensive_mode = bool(breadth.get("collapse"))

    # 广度坍塌且非强制：默认空仓（比追错热点更安全）
    if defensive_mode and not force_trade and os.environ.get("WEAK_TRADE_ON_COLLAPSE", "0") != "1":
        return {
            "signal_asof": asof_signal,
            "trade_day": trade_day,
            "breadth": breadth,
            "hot_industries": sticky_hot,
            "hot_industries_raw": hot,
            "defensive_mode": True,
            "n_passed": 0,
            "picked": [],
            "skip_reason": "breadth_collapse_empty_sleeve",
            "thresholds": {
                "vr5": [VOL_RATIO5_LO, VOL_RATIO5_HI],
                "ret5": [RET5_PRE_MIN, RET5_PRE_MAX],
                "strong_chg": STRONG_CHG_PCT,
            },
        }

    # 若允许坍塌日交易：切防御行业为主
    if defensive_mode:
        hot_inds = set(DEFENSIVE_INDS) | set(list(hot_inds)[:2])

    cands = []
    for sym, g in groups.items():
        feat = features_asof(g, asof_signal, chip=chip)
        if not feat:
            continue
        ind = (imap.get(sym) or {}).get("industry_l1")
        main5 = main_net_5d(fund, sym, asof_signal)
        ok, reasons = passes_combo(feat, main5, ind, hot_inds, defensive_mode=defensive_mode)
        if not ok:
            continue
        item = {
            **feat,
            "name": (imap.get(sym) or {}).get("name") or "",
            "industry_l1": ind,
            "main_net_5d": main5,
            "ind_density": dens_map.get(ind, 0.0),
            "score": combo_score(feat, main5, dens_map.get(ind, 0.0)),
            "sleeve": True,
            "position_exposure": MAX_EXPOSURE,
            "exec_hint": "weak_rotation_sleeve; buy_t1_open_skip_if_limit",
            "fail_reasons_empty": reasons,
        }
        if trade_day:
            ret = day_return(g, trade_day)
            if ret is not None:
                item["trade_ret"] = round(ret, 2)
                item["hit_strong"] = ret >= STRONG_CHG_PCT
        cands.append(item)

    cands.sort(key=lambda x: -x["score"])
    picked = diversify_picks(cands, top_n=top_n, max_per_ind=int(os.environ.get("WEAK_MAX_PER_IND", "2")))
    return {
        "signal_asof": asof_signal,
        "trade_day": trade_day,
        "breadth": breadth,
        "hot_industries": sticky_hot,
        "hot_industries_raw": hot,
        "defensive_mode": defensive_mode,
        "n_passed": len(cands),
        "picked": picked,
        "pool_preview": cands[:30],
        "thresholds": {
            "vr5": [VOL_RATIO5_LO, VOL_RATIO5_HI],
            "ret5": [RET5_PRE_MIN, RET5_PRE_MAX],
            "strong_chg": STRONG_CHG_PCT,
            "chip70": [CHIP_CONC70_MIN, CHIP_CONC70_MAX],
        },
    }


def apply_weak_rotation_sleeve(
    items: list,
    mkt_meta: dict | None = None,
    enabled: bool | None = None,
) -> tuple[list, dict]:
    if enabled is None:
        enabled = os.environ.get("ENABLE_WEAK_ROTATION_SLEEVE", "1") == "1"
    meta = {"sleeve_applied": False}
    if not enabled:
        return items, meta
    expo = 1.0
    if mkt_meta:
        try:
            expo = float(mkt_meta.get("position_exposure", 1.0))
        except Exception:
            expo = 1.0
    if expo > 0 and items:
        return items, meta

    kdf = load_kline()
    dates = sorted(kdf["date"].unique().tolist())
    if not dates:
        return items, meta
    asof = str(dates[-1])
    look = [str(d) for d in dates if d <= asof][-5:]
    strong = build_strong_universe(kdf, load_industry_map(), look)
    result = scan_sleeve(asof_signal=asof, strong_by_day=strong, kdf=kdf)
    picked = result["picked"]
    meta = {
        "sleeve_applied": True,
        "sleeve_n": len(picked),
        "sleeve_hot": result.get("hot_industries"),
        "sleeve_breadth": result.get("breadth"),
        "sleeve_skip": result.get("skip_reason"),
        "sleeve_signal_asof": asof,
        "position_exposure": MAX_EXPOSURE if picked else 0.0,
    }
    return picked, meta
