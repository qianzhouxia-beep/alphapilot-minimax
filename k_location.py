#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""K 系统位置引擎（交易员手册：位置 > 形态）。

输出:
  position_score   0~1，边缘高、腹地低
  box_regime       trend | box | edge | break
  forward_wall_rr  目标墙距 / 止损距（<1 视为南墙，禁入）
  sr_test_count    近端对同一 S/R 的测试次数（事不过三衰减）
  poc_distance     相对筹码 POC / 成本的距离（比例）
  edge_side        long_edge | short_edge | mid | none
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

ROOT_LOOKBACK = 60
SR_BAND = 0.008  # 0.8% 视作同一价位带
POC_BAND = 0.005
EDGE_BAND = 0.015
BOX_RANGE_MAX = 0.08  # 近 N 日振幅 <8% 视为箱体候选
MID_ZONE = (0.35, 0.65)  # 箱体内相对位置


def _bare(sym: str) -> str:
    s = str(sym or "").lower().replace("sh", "").replace("sz", "").replace("bj", "")
    return s[-6:] if len(s) >= 6 else s


def _atr(h: np.ndarray, lo: np.ndarray, c: np.ndarray, n: int = 14) -> float:
    if len(c) < 2:
        return float(c[-1] * 0.02) if len(c) else 0.0
    prev_c = np.roll(c, 1)
    prev_c[0] = c[0]
    tr = np.maximum(h - lo, np.maximum(np.abs(h - prev_c), np.abs(lo - prev_c)))
    w = min(n, len(tr))
    return float(np.mean(tr[-w:]))


def _cluster_levels(prices: np.ndarray, band: float = SR_BAND) -> list[dict]:
    """简单一维聚类：把相近拐点价合并成 S/R 带。"""
    if prices is None or len(prices) == 0:
        return []
    xs = sorted(float(x) for x in prices if x and x > 0)
    if not xs:
        return []
    bands: list[dict] = []
    cur = [xs[0]]
    for p in xs[1:]:
        ref = float(np.mean(cur))
        if abs(p - ref) / max(ref, 1e-9) <= band:
            cur.append(p)
        else:
            bands.append({"price": float(np.mean(cur)), "n": len(cur), "lo": min(cur), "hi": max(cur)})
            cur = [p]
    bands.append({"price": float(np.mean(cur)), "n": len(cur), "lo": min(cur), "hi": max(cur)})
    bands.sort(key=lambda b: (-b["n"], b["price"]))
    return bands


def _swing_points(h: np.ndarray, lo: np.ndarray, w: int = 2) -> tuple[np.ndarray, np.ndarray]:
    highs, lows = [], []
    for i in range(w, len(h) - w):
        if h[i] >= np.max(h[i - w : i + w + 1]):
            highs.append(h[i])
        if lo[i] <= np.min(lo[i - w : i + w + 1]):
            lows.append(lo[i])
    return np.array(highs, float), np.array(lows, float)


def _near(price: float, level: float, band: float) -> bool:
    if price <= 0 or level <= 0:
        return False
    return abs(price - level) / price <= band


def _chip_poc(chip: dict | None) -> float | None:
    if not chip:
        return None
    if isinstance(chip, list):
        chip = chip[-1] if chip else {}
    for k in ("chipAvgCost", "avg_cost", "poc", "chip_avg_cost"):
        v = chip.get(k)
        try:
            f = float(v or 0)
            if f > 1e-6:
                return f
        except Exception:
            continue
    return None


def compute_location(
    kl: pd.DataFrame,
    *,
    chip: dict | None = None,
    lookback: int = ROOT_LOOKBACK,
) -> dict[str, Any]:
    """基于 as-of 已截断的 K 线计算位置特征。"""
    out = {
        "position_score": 0.0,
        "box_regime": "trend",
        "forward_wall_rr": 0.0,
        "sr_test_count": 0,
        "poc_distance": None,
        "edge_side": "none",
        "nearest_support": None,
        "nearest_resistance": None,
        "atr": None,
        "tradeable": False,
        "reject_reason": "insufficient_bars",
    }
    if kl is None or len(kl) < 30:
        return out

    sub = kl.sort_values("date").reset_index(drop=True)
    if len(sub) > lookback:
        sub = sub.iloc[-lookback:].reset_index(drop=True)

    c = sub["close"].astype(float).values
    h = sub["high"].astype(float).values if "high" in sub.columns else c
    lo = sub["low"].astype(float).values if "low" in sub.columns else c
    o = sub["open"].astype(float).values if "open" in sub.columns else c
    price = float(c[-1])
    if price <= 0:
        out["reject_reason"] = "bad_price"
        return out

    atr = _atr(h, lo, c)
    out["atr"] = round(atr, 4)

    # --- S/R from swings ---
    sh, sl = _swing_points(h, lo, w=2)
    levels = _cluster_levels(np.concatenate([sh, sl]) if len(sh) or len(sl) else c[-20:], SR_BAND)
    supports = [b for b in levels if b["price"] <= price * 1.002]
    resists = [b for b in levels if b["price"] >= price * 0.998]
    nearest_sup = max(supports, key=lambda b: b["price"])["price"] if supports else float(np.min(lo[-20:]))
    nearest_res = min(resists, key=lambda b: b["price"])["price"] if resists else float(np.max(h[-20:]))
    out["nearest_support"] = round(nearest_sup, 4)
    out["nearest_resistance"] = round(nearest_res, 4)

    # --- 20d range / box ---
    win = min(20, len(c))
    hi20 = float(np.max(h[-win:]))
    lo20 = float(np.min(lo[-win:]))
    rng = (hi20 - lo20) / max(price, 1e-9)
    pos_in_range = (price - lo20) / max(hi20 - lo20, 1e-9)

    # 事不过三：近 40 根对 nearest_sup/res 的触及次数
    test_n = 0
    ref_levels = [nearest_sup, nearest_res]
    for i in range(max(0, len(c) - 40), len(c)):
        for lv in ref_levels:
            if _near(float(lo[i]), lv, SR_BAND) or _near(float(h[i]), lv, SR_BAND):
                test_n += 1
                break
    out["sr_test_count"] = int(test_n)
    sr_decay = 0.85 if test_n >= 3 else (0.92 if test_n >= 2 else 1.0)

    # --- POC ---
    poc = _chip_poc(chip)
    poc_dist = None
    near_poc = False
    if poc and poc > 0:
        poc_dist = price / poc - 1.0
        out["poc_distance"] = round(float(poc_dist), 4)
        near_poc = abs(poc_dist) <= POC_BAND

    near_sr = _near(price, nearest_sup, EDGE_BAND) or _near(price, nearest_res, EDGE_BAND)
    near_range_lo = abs(price - lo20) / price <= EDGE_BAND
    near_range_hi = abs(price - hi20) / price <= EDGE_BAND
    near_edge = near_range_lo or near_range_hi or near_sr

    # 实体破位（手册：看实体不看影线）
    body_hi = max(float(o[-1]), float(c[-1]))
    body_lo = min(float(o[-1]), float(c[-1]))
    broke_up = body_lo > hi20 * 0.998 and float(c[-1]) > float(o[-1])
    broke_dn = body_hi < lo20 * 1.002 and float(c[-1]) < float(o[-1])

    if broke_up:
        regime = "break"
        out["edge_side"] = "long_edge"
    elif broke_dn:
        regime = "break"
        out["edge_side"] = "short_edge"
    elif rng <= BOX_RANGE_MAX and MID_ZONE[0] < pos_in_range < MID_ZONE[1]:
        regime = "box"
    elif near_edge:
        regime = "edge"
    else:
        regime = "trend"
    out["box_regime"] = regime

    if out.get("edge_side") in (None, "none") or regime not in ("break",):
        if near_range_lo or _near(price, nearest_sup, EDGE_BAND):
            out["edge_side"] = "long_edge"
        elif near_range_hi or _near(price, nearest_res, EDGE_BAND):
            out["edge_side"] = "short_edge"
        elif MID_ZONE[0] < pos_in_range < MID_ZONE[1]:
            out["edge_side"] = "mid"
        else:
            out["edge_side"] = out.get("edge_side") or "none"

    # --- PositionScore ---
    score = 0.0
    if near_poc:
        score += 0.3
    if near_sr:
        score += 0.3
    # 成交量缺口近似：近端低量价位带（用收盘价分箱）
    try:
        vcol = "volume" if "volume" in sub.columns else ("amount" if "amount" in sub.columns else None)
        if vcol:
            bins = pd.cut(sub["close"].astype(float), bins=12, duplicates="drop")
            vol_by = sub.groupby(bins, observed=False)[vcol].sum()
            if len(vol_by) >= 3:
                thin = vol_by[vol_by <= vol_by.quantile(0.25)]
                for interval in thin.index:
                    if interval is None or (hasattr(interval, "left") and interval.left <= price <= interval.right):
                        score += 0.2
                        break
    except Exception:
        pass
    if near_range_lo or near_range_hi:
        score += 0.2
    if out["edge_side"] == "mid" or regime == "box":
        score -= 0.5

    score = max(0.0, min(1.0, score * sr_decay))
    out["position_score"] = round(float(score), 4)

    # --- forward wall RR（按边缘方向）---
    stop_dist = max(atr, price * 0.01)
    if out["edge_side"] == "long_edge":
        wall = nearest_res
        stop = min(nearest_sup, price - stop_dist)
        reward = max(wall - price, 0.0)
        risk = max(price - stop, stop_dist)
    elif out["edge_side"] == "short_edge":
        # 主臂偏多；空边主要用于拒单/降权，仍给 rr
        wall = nearest_sup
        stop = max(nearest_res, price + stop_dist)
        reward = max(price - wall, 0.0)
        risk = max(stop - price, stop_dist)
    else:
        wall = nearest_res
        stop = price - stop_dist
        reward = max(wall - price, 0.0)
        risk = stop_dist
    rr = float(reward / risk) if risk > 1e-9 else 0.0
    out["forward_wall_rr"] = round(rr, 4)

    # 可交易：位置够 +（非箱体腹地）+ 南墙 RR
    reject = None
    if score < 0.3:
        reject = "position_too_weak"
    elif regime == "box":
        reject = "box_mid_no_reversal"
    elif rr < 1.0 and out["edge_side"] in ("long_edge", "short_edge", "none"):
        # break 突破可放宽墙距要求
        if regime != "break":
            reject = "forward_wall"
    elif out["edge_side"] == "short_edge" and regime != "break":
        # 多头主臂：阻力边不做多（除非突破）
        reject = "short_edge_no_long"

    out["reject_reason"] = reject
    out["tradeable"] = reject is None
    return out


def load_chip_map(chip_doc: dict | None) -> dict[str, dict]:
    if not chip_doc:
        return {}
    out = {}
    for k, v in chip_doc.items():
        if isinstance(v, dict) or isinstance(v, list):
            out[_bare(k)] = v if isinstance(v, dict) else (v[-1] if v else {})
    return out
