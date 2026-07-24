"""
草木皆兵（方正金工行为反转）— AlphaPilot 简化软加分版

完整因子需分钟波动 + 散户成交占比；生产先落地可计算子集：
  惊恐度 × 日内振幅波动 × 注意力衰减 × 收益率
再做 lookback 聚合。因子越负（越恐慌）→ 软加分越大。

不硬删、不独立 STEP 清空漏斗；仅 reorder / 微调 score。
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent


def _bare(sym: str) -> str:
    s = str(sym or "")
    for p in ("sh", "sz", "bj", "SH", "SZ", "BJ"):
        s = s.replace(p, "")
    return s[-6:] if len(s) >= 6 else s


def _load_kline() -> pd.DataFrame | None:
    for p in (ROOT / "data/kline_cache/kline_all.parquet", ROOT / "kline_all.parquet"):
        if p.exists():
            try:
                df = pd.read_parquet(p)
                df["date"] = df["date"].astype(str).str[:10]
                df["symbol"] = (
                    df["symbol"].astype(str).str.replace(r"^(sh|sz|bj)", "", regex=True).str[-6:]
                )
                return df
            except Exception:
                continue
    return None


def _index_daily_returns(mkt_meta: dict | None, kdf: pd.DataFrame | None) -> pd.Series:
    """优先用上证日收益；无则从 kline 里估（缺省则全 0）。"""
    # 若 items 侧已有 env 指数 day 序列则未来可扩展；此处用全市场等权近近似太重，
    # 生产用上证 sec 日 K：从 market snapshot 只给最新 day，不够 lookback。
    # 回退：用 kline 中 000001 若存在，否则用全市场每日中位数收益。
    if kdf is None or kdf.empty:
        return pd.Series(dtype=float)
    for code in ("000001", "399001"):
        g = kdf[kdf["symbol"] == code].sort_values("date")
        if len(g) >= 30:
            r = g["close"].astype(float).pct_change()
            r.index = g["date"].values
            return r
    # 市场代理：每日横截面中位数收益
    tmp = kdf.copy()
    tmp["ret"] = tmp.groupby("symbol")["close"].pct_change()
    med = tmp.groupby("date")["ret"].median()
    return med


def calc_caomujiebing_series(
    stock: pd.DataFrame,
    market_ret: pd.Series,
    lookback: int = 10,
) -> float | None:
    """
    返回最新一期因子值（越负越恐慌）。失败返回 None。
    简化：无散户比；波动用 (H-L)/C；注意力衰减 = max(0, panic - panic.ma2)。
    """
    if stock is None or len(stock) < lookback + 3:
        return None
    s = stock.sort_values("date").copy()
    s["ret"] = s["close"].astype(float).pct_change()
    s["vol"] = (s["high"].astype(float) - s["low"].astype(float)) / (
        s["close"].astype(float) + 1e-10
    )
    dates = s["date"].astype(str)
    mret = market_ret.reindex(dates.values).astype(float)
    # 对齐不到时用 0（同步假设 → 惊恐度偏低，更保守）
    mret = mret.fillna(0.0).values
    sret = s["ret"].fillna(0.0).values
    denom = np.abs(sret) + np.abs(mret) + 1e-10
    panic = np.abs(sret - mret) / denom
    panic_s = pd.Series(panic)
    atten = (panic_s - panic_s.rolling(2, min_periods=1).mean()).clip(lower=0).values
    weighted = atten * s["vol"].fillna(0).values * sret
    w = pd.Series(weighted).iloc[-lookback:]
    if w.isna().all():
        return None
    val = float((w.mean() + w.std(ddof=0)) / 2.0)
    if math.isnan(val) or math.isinf(val):
        return None
    return val


def apply_caomujiebing_soft_boost(
    items: list[dict[str, Any]],
    mkt_meta: dict | None = None,
    lookback: int = 10,
    boost_max: float = 0.08,
    max_stocks: int = 120,
) -> list[dict[str, Any]]:
    """
    对候选做截面相对软加分：因子越低（越恐慌）加分越多。
    仅处理 score 最高的 max_stocks 只以控制 IO；不删除任何票。
    """
    if not items:
        return items
    kdf = _load_kline()
    if kdf is None:
        print("  caomujiebing: no kline cache, skip", flush=True)
        return items

    mret = _index_daily_returns(mkt_meta, kdf)
    ranked = sorted(items, key=lambda x: -float(x.get("score") or 0))
    focus = ranked[:max_stocks]
    focus_codes = {_bare(x.get("symbol")) for x in focus}

    factor_map: dict[str, float] = {}
    for code in focus_codes:
        if not code:
            continue
        g = kdf[kdf["symbol"] == code]
        if g.empty:
            continue
        v = calc_caomujiebing_series(g, mret, lookback=lookback)
        if v is not None:
            factor_map[code] = v

    if len(factor_map) < 3:
        print(f"  caomujiebing: too few factors ({len(factor_map)}), skip", flush=True)
        return items

    vals = np.array(list(factor_map.values()), dtype=float)
    lo, hi = float(np.nanpercentile(vals, 5)), float(np.nanpercentile(vals, 95))
    span = max(hi - lo, 1e-9)

    boosted = 0
    out = []
    for r in items:
        nr = dict(r)
        code = _bare(r.get("symbol"))
        fv = factor_map.get(code)
        if fv is None:
            out.append(nr)
            continue
        # 低分位（更恐慌）→ norm 接近 0 → boost 大
        norm = float(np.clip((fv - lo) / span, 0.0, 1.0))
        # 仅对「相对跑输 + 恐慌」给正 boost：因子为负更可信
        panic_strength = 1.0 - norm
        if fv >= 0:
            panic_strength *= 0.35  # 正值侧减弱
        delta = round(boost_max * panic_strength, 4)
        base = float(nr.get("score") or 0)
        nr["caomujiebing"] = round(fv, 6)
        nr["caomujiebing_norm"] = round(norm, 4)
        nr["caomujiebing_delta"] = delta
        nr["score_pre_caomujiebing"] = round(base, 4)
        nr["score"] = round(max(0.01, base + delta), 4)
        if delta > 1e-6:
            boosted += 1
        out.append(nr)

    out.sort(key=lambda x: -float(x.get("score") or 0))
    print(
        f"  caomujiebing soft_boost: n_factor={len(factor_map)} boosted={boosted} "
        f"lookback={lookback} boost_max={boost_max}",
        flush=True,
    )
    return out
