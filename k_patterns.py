#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""K 系统形态确认（仅在 edge/break 上计分；P+ 不作开仓）。

形态: 顶/底分型、2B、Pinbar、孕线(Inside)。
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _body(o: float, c: float) -> float:
    return abs(c - o)


def _is_yin(o: float, c: float) -> bool:
    return c < o


def _is_yang(o: float, c: float) -> bool:
    return c > o


def detect_patterns(kl: pd.DataFrame) -> dict[str, Any]:
    """在 as-of 截断 K 线上检测形态；返回强度与列表。"""
    out = {
        "patterns": [],
        "pattern_count": 0,
        "pattern_score": 0.0,
        "bullish": False,
        "bearish": False,
        "detail": {},
    }
    if kl is None or len(kl) < 5:
        return out

    sub = kl.sort_values("date").reset_index(drop=True)
    o = sub["open"].astype(float).values if "open" in sub.columns else sub["close"].astype(float).values
    c = sub["close"].astype(float).values
    h = sub["high"].astype(float).values if "high" in sub.columns else c
    lo = sub["low"].astype(float).values if "low" in sub.columns else c

    pats: list[str] = []
    score = 0.0
    bull = bear = False
    detail: dict[str, Any] = {}

    # --- 底/顶分型（最后 3 根）---
    if len(c) >= 3:
        i = len(c) - 1
        # 底分型：中间最低，第三根阳
        if lo[i - 1] < lo[i - 2] and lo[i - 1] < lo[i] and h[i - 1] <= max(h[i - 2], h[i]) + 1e-9:
            if _is_yang(o[i], c[i]):
                strength = 0.6
                if c[i] > max(c[i - 2], c[i - 1]):
                    strength += 0.15
                if _body(o[i], c[i]) >= _body(o[i - 2], c[i - 2]):
                    strength += 0.1
                pats.append("fractal_bottom")
                score += strength
                bull = True
                detail["fractal_bottom"] = round(strength, 3)
        # 顶分型：中间最高，第三根阴
        if h[i - 1] > h[i - 2] and h[i - 1] > h[i] and lo[i - 1] >= min(lo[i - 2], lo[i]) - 1e-9:
            if _is_yin(o[i], c[i]):
                strength = 0.6
                if c[i] < min(c[i - 2], c[i - 1]):
                    strength += 0.15
                pats.append("fractal_top")
                score += strength
                bear = True
                detail["fractal_top"] = round(strength, 3)

    # --- 2B：阴包阳 / 阳包阴（≤3 根）---
    if len(c) >= 2:
        # 优品：今日实体包住昨实体
        b0 = _body(o[-1], c[-1])
        b1 = _body(o[-2], c[-2])
        engulf_bear = _is_yin(o[-1], c[-1]) and _is_yang(o[-2], c[-2]) and c[-1] < o[-2] and o[-1] >= c[-2]
        engulf_bull = _is_yang(o[-1], c[-1]) and _is_yin(o[-2], c[-2]) and c[-1] > o[-2] and o[-1] <= c[-2]
        if engulf_bear:
            tier = "premium" if b0 >= b1 else "ok"
            strength = 0.85 if tier == "premium" else 0.55
            pats.append(f"2b_bear_{tier}")
            score += strength
            bear = True
            detail["2b_bear"] = tier
        if engulf_bull:
            tier = "premium" if b0 >= b1 else "ok"
            strength = 0.85 if tier == "premium" else 0.55
            pats.append(f"2b_bull_{tier}")
            score += strength
            bull = True
            detail["2b_bull"] = tier
        # 三根优品：后两根实体和 > 第一根
        if len(c) >= 3 and not engulf_bull and not engulf_bear:
            if _is_yang(o[-1], c[-1]) and _is_yin(o[-3], c[-3]):
                if _body(o[-1], c[-1]) + _body(o[-2], c[-2]) > _body(o[-3], c[-3]) and c[-1] > o[-3]:
                    pats.append("2b_bull_triple")
                    score += 0.7
                    bull = True
                    detail["2b_bull"] = "triple"
            if _is_yin(o[-1], c[-1]) and _is_yang(o[-3], c[-3]):
                if _body(o[-1], c[-1]) + _body(o[-2], c[-2]) > _body(o[-3], c[-3]) and c[-1] < o[-3]:
                    pats.append("2b_bear_triple")
                    score += 0.7
                    bear = True
                    detail["2b_bear"] = "triple"

    # --- Pinbar ---
    if len(c) >= 1:
        full = max(h[-1] - lo[-1], 1e-9)
        upper = h[-1] - max(o[-1], c[-1])
        lower = min(o[-1], c[-1]) - lo[-1]
        # 上 Pin（止跌，偏多）：下影 ≥ 2/3
        if lower / full >= 0.66 and upper / full <= 0.25:
            pats.append("pinbar_bull")
            score += 0.65
            bull = True
            detail["pinbar"] = "bull"
        # 下 Pin（止涨，偏空）：上影 ≥ 2/3
        if upper / full >= 0.66 and lower / full <= 0.25:
            pats.append("pinbar_bear")
            score += 0.65
            bear = True
            detail["pinbar"] = "bear"

    # --- 孕线：母包子，第三根破母实体定方向（用 -3,-2 为母子，-1 为突破）---
    if len(c) >= 3:
        mo, mc, mh, ml = o[-3], c[-3], h[-3], lo[-3]
        so, sc, sh, sl = o[-2], c[-2], h[-2], lo[-2]
        mother_body_hi, mother_body_lo = max(mo, mc), min(mo, mc)
        son_body_hi, son_body_lo = max(so, sc), min(so, sc)
        wrap_body = son_body_hi <= mother_body_hi + 1e-9 and son_body_lo >= mother_body_lo - 1e-9
        wrap_wick = sh <= mh + 1e-9 and sl >= ml - 1e-9
        if wrap_body and wrap_wick:
            if c[-1] > mother_body_hi:
                pats.append("inside_break_up")
                score += 0.7
                bull = True
                detail["inside"] = "break_up"
            elif c[-1] < mother_body_lo:
                pats.append("inside_break_dn")
                score += 0.7
                bear = True
                detail["inside"] = "break_dn"

    # 归一
    score = float(min(1.5, score) / 1.5)
    out["patterns"] = pats
    out["pattern_count"] = len(pats)
    out["pattern_score"] = round(score, 4)
    out["bullish"] = bull and not (bear and score < 0.4)
    out["bearish"] = bear and not (bull and score < 0.4)
    out["detail"] = detail
    return out


def pattern_confirms_long(loc: dict, pat: dict) -> bool:
    """多头主臂：edge/break 上出现偏多形态，或向上突破确认。"""
    regime = loc.get("box_regime")
    if regime == "box":
        return False  # 箱体内反转形态失效
    if regime == "break":
        return loc.get("edge_side") == "long_edge"
    if loc.get("edge_side") != "long_edge":
        return False
    if not pat.get("bullish"):
        return False
    return int(pat.get("pattern_count") or 0) >= 1
