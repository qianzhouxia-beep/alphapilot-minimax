#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""个股连续净流入天数（App 口径）— 同源 fund_flow_history。

定义：从最近交易日往前，连续 main_net > 0 的天数。
与板块侧 consecutive_inflow_days 口径一致（非 5 日窗口计数）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
FUND_HIST = ROOT / "data" / "fund_flow_history.json"

_cache: dict[str, Any] | None = None


def _bare(sym: str) -> str:
    s = str(sym or "").lower().replace("sh", "").replace("sz", "").replace("bj", "")
    digits = "".join(ch for ch in s if ch.isdigit())
    return digits[-6:] if len(digits) >= 6 else digits


def load_fund_hist(path: Path | None = None) -> dict[str, dict[str, float]]:
    global _cache
    p = path or FUND_HIST
    if _cache is not None and path is None:
        return _cache
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, dict[str, float]] = {}
    for k, v in (raw or {}).items():
        code = _bare(k)
        if not code or not isinstance(v, dict):
            continue
        series: dict[str, float] = {}
        for d, net in v.items():
            try:
                series[str(d)] = float(net)
            except (TypeError, ValueError):
                continue
        out[code] = series
    if path is None:
        _cache = out
    return out


def clear_cache() -> None:
    global _cache
    _cache = None


def consecutive_inflow_days(
    hist: dict[str, float] | None,
    *,
    asof: str | None = None,
    max_lookback: int = 30,
) -> int:
    """从 asof（含）或最新日往前，连续净流入>0 的天数。"""
    if not hist:
        return 0
    dates = sorted(hist.keys(), reverse=True)
    if asof:
        dates = [d for d in dates if d <= asof]
    if not dates:
        return 0
    streak = 0
    for d in dates[: max(1, max_lookback)]:
        try:
            net = float(hist[d])
        except (TypeError, ValueError, KeyError):
            break
        if net > 0:
            streak += 1
        else:
            break
    return streak


def consec_for_symbol(
    symbol: str,
    fund_hist: dict[str, dict[str, float]] | None = None,
    *,
    asof: str | None = None,
) -> int:
    fh = fund_hist if fund_hist is not None else load_fund_hist()
    return consecutive_inflow_days(fh.get(_bare(symbol)), asof=asof)
