#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""K 系统时段/事件硬过滤（A 股版交易员手册时间维度）。"""
from __future__ import annotations

from datetime import datetime, time
from typing import Any


def session_block_reason(now: datetime | None = None) -> str | None:
    """返回禁开仓原因；None 表示可开。日频回测可跳过本函数。"""
    now = now or datetime.now()
    t = now.time()
    # 开盘异动
    if time(9, 25) <= t < time(9, 35):
        return "open_auction_window"
    # 午休变盘
    if time(11, 30) <= t < time(13, 5):
        return "lunch_regime"
    # 尾盘不做新开
    if t >= time(14, 50):
        return "late_session"
    return None


def near_limit_block(change_pct: float | None, limit_frac: float = 0.10, soft: float = 0.97) -> str | None:
    if change_pct is None:
        return None
    # change_pct 可为 0.09 或 9
    chg = float(change_pct)
    if abs(chg) > 1:
        chg = chg / 100.0
    if chg >= limit_frac * soft:
        return "near_limit_up"
    if chg <= -limit_frac * soft:
        return "near_limit_down"
    return None


def apply_session_meta(item: dict, now: datetime | None = None) -> dict:
    row = dict(item)
    reason = session_block_reason(now)
    row["k_session_block"] = reason
    return row
