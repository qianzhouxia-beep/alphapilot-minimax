#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""动态交易成本模型 — 替代硬编码 15bp。

成本构成:
  1. 流动性溢价（换手率）
  2. 买卖价差
  3. 冲击成本（订单金额 / 日均成交额）
  4. 时间段溢价（开盘/尾盘更高）
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any


def _detect_period(now: datetime | None = None) -> str:
    now = now or datetime.now()
    hm = (now.hour, now.minute)
    if hm < (9, 45):
        return "open"
    if hm >= (14, 30):
        return "close"
    return "mid"


def estimate_trade_cost(
    symbol: str,
    order_value: float,
    *,
    direction: str = "buy",
    time_of_day: str | None = None,
    turnover_rate: float | None = None,
    avg_daily_value: float | None = None,
    spread: float | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """动态估计单边交易成本（比例）。

    Returns:
      {
        total, total_bp,
        liq_premium, spread_cost, impact_cost, time_premium,
        ..._bp 字段,
        period, symbol, direction
      }
    """
    period = time_of_day or _detect_period(now)

    # 尝试补全行情侧输入
    if turnover_rate is None or avg_daily_value is None or spread is None:
        try:
            from live_fund_flow import fetch_fund_flow

            live = fetch_fund_flow(symbol) or {}
            if turnover_rate is None and live.get("turnover") is not None:
                turnover_rate = float(live.get("turnover") or 0)
            if live.get("price") and live.get("turnover"):
                # 粗估：无成交额时用价×换手代理（仅兜底）
                pass
        except Exception:
            pass

    to = float(turnover_rate or 3.0)
    adv = float(avg_daily_value or 5e8)  # 默认日均 5 亿
    spr = float(spread if spread is not None else 0.0005)

    # 1) 流动性溢价（基准 10bp）
    liq = 0.0010
    if to < 1.0:
        liq += 0.0008
    elif to < 2.0:
        liq += 0.0003
    elif to > 5.0:
        liq -= 0.0003
    liq = max(0.0004, liq)

    # 2) 价差
    spread_cost = max(0.0002, min(0.003, spr))

    # 3) 冲击
    participation = float(order_value or 0) / max(adv, 1.0)
    impact = 0.0003 * math.sqrt(max(participation, 1e-8) / 0.01)
    impact = min(0.005, impact)

    # 4) 时间段
    time_premium = {"open": 0.0005, "mid": 0.0, "close": 0.0003}.get(period, 0.0)

    # 卖出印花税近似（A股卖出 5bp，买入无）— 可选
    stamp = 0.0005 if direction == "sell" else 0.0

    total = liq + spread_cost + impact + time_premium + stamp
    return {
        "symbol": symbol,
        "direction": direction,
        "period": period,
        "total": round(total, 6),
        "total_bp": round(total * 10000, 1),
        "liq_premium": round(liq, 6),
        "liq_premium_bp": round(liq * 10000, 1),
        "spread_cost": round(spread_cost, 6),
        "spread_bp": round(spread_cost * 10000, 1),
        "impact_cost": round(impact, 6),
        "impact_bp": round(impact * 10000, 1),
        "time_premium": round(time_premium, 6),
        "time_premium_bp": round(time_premium * 10000, 1),
        "stamp": round(stamp, 6),
        "turnover_rate": to,
        "avg_daily_value": adv,
        "participation": round(participation, 6),
    }


def cost_rt_default(symbol: str = "", order_value: float = 100000) -> float:
    """兼容旧 cost_rt 字段：返回动态总成本比例。"""
    return float(estimate_trade_cost(symbol or "000001", order_value)["total"])


if __name__ == "__main__":
    for ov in (5e4, 1.5e5, 5e5):
        print(ov, estimate_trade_cost("600519", ov, turnover_rate=1.2))
