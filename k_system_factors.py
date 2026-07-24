#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""K 系统门面：位置 + 形态 → 对 VM2.5 候选做硬闸门 / 弱校准。

环境变量:
  ENABLE_K_LOCATION_GATE=0   硬过滤（默认 0；回测显示硬删会伤主臂）
  K_POSITION_MIN=0.3
  K_REQUIRE_PATTERN=0        是否强制贴边形态（默认 0）
  K_SCORE_BOOST_MAX=0.10     通过/标注后最多 +10% 排序微调
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

from k_location import _bare, compute_location, load_chip_map
from k_patterns import detect_patterns, pattern_confirms_long

ROOT = Path(__file__).resolve().parent


def _env_bool(name: str, default: bool = True) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _load_chip() -> dict:
    for p in (ROOT / "chip_data_all.json", ROOT / "data" / "chip_data_all.json"):
        if p.exists():
            try:
                return load_chip_map(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                return {}
    return {}


_CHIP_CACHE: dict[str, dict] | None = None
_KLINE_CACHE: dict[str, pd.DataFrame] | None = None


def _chip() -> dict[str, dict]:
    global _CHIP_CACHE
    if _CHIP_CACHE is None:
        _CHIP_CACHE = _load_chip()
    return _CHIP_CACHE


def load_kline_groups(parquet_path: Path | None = None) -> dict[str, pd.DataFrame]:
    global _KLINE_CACHE
    if _KLINE_CACHE is not None:
        return _KLINE_CACHE
    paths = []
    if parquet_path:
        paths.append(parquet_path)
    paths.extend(
        [
            ROOT / "data" / "kline_cache" / "kline_all.parquet",
            ROOT / "kline_all.parquet",
        ]
    )
    for p in paths:
        if p.exists():
            kdf = pd.read_parquet(p)
            kdf["date"] = kdf["date"].astype(str).str[:10]
            kdf["symbol"] = kdf["symbol"].astype(str).map(_bare)
            _KLINE_CACHE = {
                s: g.sort_values("date").reset_index(drop=True) for s, g in kdf.groupby("symbol")
            }
            return _KLINE_CACHE
    _KLINE_CACHE = {}
    return _KLINE_CACHE


def evaluate_symbol(
    sym: str,
    kl: pd.DataFrame | None,
    *,
    asof_idx: int | None = None,
    chip: dict | None = None,
    require_pattern: bool | None = None,
) -> dict[str, Any]:
    """单票 K 评估。kl 需含 date/open/high/low/close。"""
    # 默认不强制形态：VM2.5+金叉主臂偏趋势，与反转形态硬绑会空仓
    require_pattern = (
        _env_bool("K_REQUIRE_PATTERN", False) if require_pattern is None else require_pattern
    )
    pos_min = float(os.environ.get("K_POSITION_MIN", "0.3"))

    if kl is None or kl.empty:
        return {
            "k_tradeable": False,
            "k_reject": "no_kline",
            "position_score": 0.0,
            "pattern_count": 0,
        }

    sub = kl.sort_values("date").reset_index(drop=True)
    if asof_idx is not None:
        sub = sub.iloc[: asof_idx + 1].reset_index(drop=True)

    code = _bare(sym)
    chip_row = chip if chip is not None else _chip().get(code)

    loc = compute_location(sub, chip=chip_row)
    pat = detect_patterns(sub)
    confirms = pattern_confirms_long(loc, pat)

    reject = loc.get("reject_reason")
    if float(loc.get("position_score") or 0) < pos_min:
        reject = reject or "position_too_weak"
    if loc.get("box_regime") == "box":
        reject = "box_mid_no_reversal"
    if require_pattern and loc.get("box_regime") != "break" and not confirms:
        reject = reject or "no_edge_pattern"
    # 非强制形态：金叉突破常在区间上沿，取消阻力边禁多
    if not require_pattern and reject == "short_edge_no_long":
        reject = None
    # 非强制形态：墙距放宽到 0.5R（突破单）
    if not require_pattern and reject == "forward_wall" and loc.get("box_regime") in (
        "break",
        "trend",
        "edge",
    ):
        if float(loc.get("forward_wall_rr") or 0) >= 0.5:
            reject = None

    tradeable = reject is None

    boost_max = float(os.environ.get("K_SCORE_BOOST_MAX", "0.10"))
    edge_q = float(loc.get("position_score") or 0) * max(float(pat.get("pattern_score") or 0), 0.35)
    boost = min(boost_max, boost_max * edge_q) if tradeable else 0.0

    return {
        "k_tradeable": bool(tradeable),
        "k_reject": reject,
        "position_score": loc.get("position_score"),
        "box_regime": loc.get("box_regime"),
        "forward_wall_rr": loc.get("forward_wall_rr"),
        "edge_side": loc.get("edge_side"),
        "sr_test_count": loc.get("sr_test_count"),
        "poc_distance": loc.get("poc_distance"),
        "pattern_count": pat.get("pattern_count"),
        "pattern_score": pat.get("pattern_score"),
        "patterns": pat.get("patterns"),
        "k_bullish": pat.get("bullish"),
        "k_score_boost": round(boost, 4),
        "k_confirm": "strong" if tradeable and confirms else ("ok" if tradeable else "weak"),
    }


def apply_k_location_gate(
    items: list[dict],
    *,
    groups: dict[str, pd.DataFrame] | None = None,
    asof: str | None = None,
    hard: bool | None = None,
) -> list[dict]:
    """对推荐列表附加 K 字段；hard 时剔除不可交易票。"""
    if hard is None:
        hard = _env_bool("ENABLE_K_LOCATION_GATE", False)
    if not items:
        return items

    groups = groups if groups is not None else load_kline_groups()
    out = []
    for it in items:
        row = dict(it)
        sym = _bare(row.get("symbol"))
        g = groups.get(sym)
        asof_idx = None
        if g is not None and asof:
            idxs = g.index[g["date"] <= asof]
            if len(idxs):
                asof_idx = int(idxs[-1])
        elif g is not None:
            asof_idx = len(g) - 1

        ev = evaluate_symbol(sym, g, asof_idx=asof_idx)
        row.update(ev)

        base = float(row.get("score") or row.get("model_proba") or 0)
        row["k_adjusted_score"] = base * (1.0 + float(ev.get("k_score_boost") or 0))

        if hard and not ev.get("k_tradeable"):
            continue
        out.append(row)

    out.sort(key=lambda x: float(x.get("k_adjusted_score") or x.get("score") or 0), reverse=True)
    return out
