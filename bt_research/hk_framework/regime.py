#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""regime: 市场风险开关（HK，Cursor 2026-09-10）。

动机：港股这套 edge 是 regime 依赖的——多头只是低 beta，空头收益集中在下跌市。
裸跑多空会在上涨市被反噬。故用「指数趋势 + 池内广度」做开关：
  risk_on  = 02800(盈富/恒指ETF) 收盘 > MA20 且 MA20 > MA60   （或广度 > 阈值）
  risk_off = 反之
用法：
  from regime import regime_series, gate_fn
  gate_fn(...) 传给 LongShortEngine.run(gate=...)，返回允许的方向集合。
"""
import config as C

IDX = "02800"     # 盈富基金（跟踪恒生指数）


def _ma(bars, i, n):
    if i - n + 1 < 0:
        return None
    s = 0.0
    for k in range(i - n + 1, i + 1):
        s += bars[k]["c"]
    return s / n


def index_trend(ctx, date, fast=20, slow=60):
    """指数趋势：+1 上升 / -1 下降 / 0 数据不足。"""
    bars, i = ctx.bar(IDX, date)
    if not bars:
        return 0
    mf, ms = _ma(bars, i, fast), _ma(bars, i, slow)
    if mf is None or ms is None:
        return 0
    px = bars[i]["c"]
    if px > mf and mf > ms:
        return 1
    if px < mf and mf < ms:
        return -1
    return 0


def breadth(ctx, date, ma=20):
    """池内广度：收盘 > MA20 的占比。"""
    codes = ctx.pool_for(date)
    up = tot = 0
    for c in codes:
        bars, i = ctx.bar(c, date)
        if not bars or i < ma:
            continue
        m = _ma(bars, i, ma)
        if m is None:
            continue
        tot += 1
        if bars[i]["c"] > m:
            up += 1
    return (up / tot) if tot else None


def regime_series(ctx, days, start=0):
    """逐日 regime 序列，便于回测与可视化。"""
    out = {}
    for d in days[start:]:
        out[d] = {"trend": index_trend(ctx, d), "breadth": breadth(ctx, d)}
    return out


def make_gate(use_breadth=True, breadth_thr=0.5, mode="switch"):
    """返回 gate(ctx,date)->set(['long','short'])。

    mode:
      switch   风险开 → 只多；风险关 → 只空（regime 切换的市场中性）
      shortonly 只做空（且仅在 risk_off）
      both     多空都开（基线对照）
    """
    def gate(ctx, date):
        tr = index_trend(ctx, date)
        br = breadth(ctx, date) if use_breadth else None
        risk_on = (tr >= 0 and (br is None or br >= breadth_thr)) if tr != 0 else (
            (br is not None and br >= breadth_thr))
        # 明确判定：趋势 -1 或 广度低 = risk_off
        if tr == -1:
            risk_on = False
        elif tr == 1:
            risk_on = True if br is None else (br >= breadth_thr)
        else:
            risk_on = (br is not None and br >= breadth_thr)
        if mode == "both":
            return {"long", "short"}
        if mode == "shortonly":
            return {"short"} if not risk_on else set()
        return {"long"} if risk_on else {"short"}
    return gate
