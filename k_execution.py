#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""K 执行层：只做开仓时机 + 时间止损/划痕（不改选股）。

选股维持 A0（VM2.5 + v3.1 金叉漏斗）。
本模块接入 trade_executor：
  1) 开仓时机：时段过滤；追高时把市价买改成限价等待
  2) 时间止损：可卖后若迟迟无向有利方向发展 → 划痕离场

环境变量:
  ENABLE_K_ENTRY_TIMING=1   默认开
  ENABLE_K_TIME_STOP=0      默认关（回测未抬升收益；避免可卖日早盘误划痕）
  K_TIME_STOP_MIN_PEAK=0.01 峰值浮盈未达 1% 视为「没走出预期」
  K_TIME_STOP_MAX_PNL=0.0   当前浮盈 ≤0 才划痕（有小盈可交给 peel/T+2）
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from k_session_filter import session_block_reason


def _env_on(name: str, default: bool = True) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def apply_entry_timing(
    decision: dict[str, Any],
    *,
    now: datetime | None = None,
    gap: float | None = None,
) -> dict[str, Any]:
    """在 GapSoft 决策之上叠加 K 开仓时机。

    - 禁开时段：市价买 → pending/skip
    - 追高（gap 已偏大）且本可市价成交：改为限价等待，避免手册说的「乱枪」
    """
    out = dict(decision or {})
    if not _env_on("ENABLE_K_ENTRY_TIMING", True):
        out["k_entry"] = "disabled"
        return out

    now = now or datetime.now()
    block = session_block_reason(now)
    action = out.get("action")
    g = out.get("gap") if out.get("gap") is not None else gap

    if block and action == "buy":
        # 开盘异动窗：直接跳过更安全；午休/尾盘：挂限价等到可交易或过期
        if block == "open_auction_window":
            out["action"] = "skip"
            out["reason"] = f"k_session:{block}"
            out["k_entry"] = "skip_session"
            return out
        # 改挂单等待（由 pending_limits 消化）
        if out.get("limit") is None and g is not None:
            # 用昨收推一个温和限价：与 GapSoft mid 一致思想
            # 无昨收时保持 skip
            out["action"] = "skip"
            out["reason"] = f"k_session:{block}"
            out["k_entry"] = "skip_session"
            return out
        out["action"] = "pending" if out.get("limit") else "skip"
        out["reason"] = f"k_session:{block}"
        out["k_entry"] = "defer_session"
        return out

    # 追高抑制：gap>1.5% 仍给到 buy(open_ok 不会) — 对 mid_hit/soft_hit 保持；
    # 若将来 open_ok 边界被放宽，这里兜底把偏大 gap 的市价买改成等待。
    if action == "buy" and g is not None and g > 0.015 and not out.get("limit"):
        out["action"] = "pending"
        out["k_entry"] = "defer_chase"
        out["reason"] = (out.get("reason") or "") + "+k_defer_chase"
        # 调用方若无 limit，应补 prev*1.01；此处只打标
        return out

    out["k_entry"] = "ok"
    return out


def time_stop_triggered(
    pos: dict[str, Any],
    *,
    price: float,
    cost: float,
    held_days: int,
    can_sell: bool,
) -> tuple[bool, str]:
    """手册时间止损/划痕：可卖后若行情未给出预期方向，主动离场。

    日频近似：
      - 已持有 ≥1 个交易日（T+1 可卖）
      - 峰值浮盈 < 1%（没走出）
      - 当前浮盈 ≤ 0（还在水下或持平）
    → 划痕卖出，不等到被动 T+2。
    """
    if not _env_on("ENABLE_K_TIME_STOP", False):
        return False, ""
    if not can_sell or cost <= 0 or price <= 0:
        return False, ""
    min_held = int(os.environ.get("K_TIME_STOP_HELD_DAYS", "1"))
    if held_days < min_held:
        return False, ""

    peak = float(pos.get("trailing_high") or cost)
    peak_gain = (peak - cost) / cost
    pnl = (price - cost) / cost
    min_peak = float(os.environ.get("K_TIME_STOP_MIN_PEAK", "0.01"))
    max_pnl = float(os.environ.get("K_TIME_STOP_MAX_PNL", "0.0"))

    if peak_gain < min_peak and pnl <= max_pnl:
        return True, "卖出(时间止损·划痕)"
    return False, ""


def ticket_exec_meta(pick: dict | None = None) -> dict[str, Any]:
    """写入 order ticket 的执行元数据（选股仍 A0，仅执行约定）。"""
    return {
        "k_entry_timing": _env_on("ENABLE_K_ENTRY_TIMING", True),
        "k_time_stop": _env_on("ENABLE_K_TIME_STOP", False),
        "k_time_stop_min_peak": float(os.environ.get("K_TIME_STOP_MIN_PEAK", "0.01")),
        "selection_arm": "A0_baseline",
        "note": "选股维持 A0；K 仅用于开仓时机与时间止损",
    }
