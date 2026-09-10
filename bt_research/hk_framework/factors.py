#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""factors: 因子注册表 + 价格族 + 南向族。

因子接口: fn(ctx, date) -> {code: value}
  - date = 打分交易日 T（用截至 T 的信息，不偷看未来）
  - 南向因子内部已扣 T+1 披露滞后（用严格早于 T 的最近截面）
新增因子: 用 @register("名字", "类别")，再在 config.DEFAULT_WEIGHTS 给权重即可。
"""
import statistics as st

REGISTRY: dict[str, dict] = {}


def register(name: str, category: str):
    def deco(fn):
        REGISTRY[name] = {"fn": fn, "category": category}
        return fn
    return deco


class Context:
    """一次打分所需的只读上下文。"""

    def __init__(self, kline: dict, south_hist: dict, pool_codes):
        self.kline = kline
        self.kidx = {c: {b["d"]: i for i, b in enumerate(bars)}
                     for c, bars in kline.items()}
        self.south = south_hist
        self.south_dates = sorted(south_hist.keys())
        self.pool = list(pool_codes)

    # ---- helpers ----
    def bar(self, code: str, date: str):
        km = self.kidx.get(code)
        if not km or date not in km:
            return None, None
        i = km[date]
        return self.kline[code], i

    def price(self, code: str, date: str, field: str = "c"):
        bars, i = self.bar(code, date)
        return bars[i][field] if bars else None

    def south_asof(self, date: str):
        """严格早于 date 的最近持股截面（T+1 披露滞后）。"""
        prev = [d for d in self.south_dates if d < date]
        return prev[-1] if prev else None

    def pool_for(self, date: str):
        """Point-in-time universe：date 当日实际有南向持股截面 ∩ 有K线。
        避免用最新池子回测早期（存活/入选偏差 / 前视）。"""
        sd = self.south_asof(date)
        if sd:
            xs = self.south.get(sd) or {}
            return [c for c in xs if c in self.kline]
        return self.pool


# ---------------- 价格族 ----------------
def _mom(n):
    @register(f"mom_{n}", "price")
    def f(ctx: Context, date: str):
        out = {}
        for c in ctx.pool_for(date):
            bars, i = ctx.bar(c, date)
            if not bars or i - n < 0:
                continue
            p0, p1 = bars[i - n]["c"], bars[i]["c"]
            if p0:
                out[c] = p1 / p0 - 1.0
        return out
    return f


for _n in (20, 60, 120):
    _mom(_n)


@register("trend_ma20", "price")
def trend_ma20(ctx: Context, date: str):
    out = {}
    for c in ctx.pool_for(date):
        bars, i = ctx.bar(c, date)
        if not bars or i - 20 < 0:
            continue
        ma = st.mean(b["c"] for b in bars[i - 20:i])
        if ma:
            out[c] = bars[i]["c"] / ma - 1.0
    return out


@register("vol_20", "price")
def vol_20(ctx: Context, date: str):
    """20 日收益波动（年化前的日频 std）。"""
    out = {}
    for c in ctx.pool_for(date):
        bars, i = ctx.bar(c, date)
        if not bars or i - 21 < 0:
            continue
        rets = []
        for k in range(i - 20, i):
            p0, p1 = bars[k]["c"], bars[k + 1]["c"]
            if p0:
                rets.append(p1 / p0 - 1.0)
        if len(rets) >= 10:
            out[c] = st.pstdev(rets)
    return out


@register("dd_60", "price")
def dd_60(ctx: Context, date: str):
    """距 60 日最高点的回撤（<=0，越接近 0 越强）。"""
    out = {}
    for c in ctx.pool_for(date):
        bars, i = ctx.bar(c, date)
        if not bars or i - 60 < 0:
            continue
        hi = max(b["h"] for b in bars[i - 60:i + 1])
        if hi:
            out[c] = bars[i]["c"] / hi - 1.0
    return out


# ---------------- 南向族（股数/占比口径；已实证为反向/风险信号）----------------
def _sb_change(n):
    @register(f"sb_ratio_chg{n}", "southbound")
    def f(ctx: Context, date: str):
        sd = ctx.south_asof(date)
        if not sd:
            return {}
        idx = ctx.south_dates.index(sd)
        if idx < n:
            return {}
        sd0 = ctx.south_dates[idx - n]
        out = {}
        a, b = ctx.south[sd], ctx.south[sd0]
        for c in ctx.pool_for(date):
            ra, rb = a.get(c, {}).get("r"), b.get(c, {}).get("r")
            if ra is not None and rb is not None:
                out[c] = ra - rb
        return out
    return f


for _n in (5, 20):
    _sb_change(_n)


def _sb_growth(n):
    @register(f"sb_shares_g{n}", "southbound")
    def f(ctx: Context, date: str):
        sd = ctx.south_asof(date)
        if not sd:
            return {}
        idx = ctx.south_dates.index(sd)
        if idx < n:
            return {}
        sd0 = ctx.south_dates[idx - n]
        out = {}
        a, b = ctx.south[sd], ctx.south[sd0]
        for c in ctx.pool_for(date):
            s0, s1 = b.get(c, {}).get("s"), a.get(c, {}).get("s")
            if s0 and s1:
                out[c] = s1 / s0 - 1.0
        return out
    return f


for _n in (5, 20):
    _sb_growth(_n)


@register("sb_ratio_lvl", "southbound")
def sb_ratio_lvl(ctx: Context, date: str):
    sd = ctx.south_asof(date)
    if not sd:
        return {}
    xs = ctx.south[sd]
    return {c: xs[c]["r"] for c in ctx.pool_for(date) if xs.get(c, {}).get("r") is not None}


def compute_all(ctx: Context, date: str, names=None) -> dict:
    names = names or list(REGISTRY.keys())
    out = {}
    for nm in names:
        if nm in REGISTRY:
            out[nm] = REGISTRY[nm]["fn"](ctx, date)
    return out
