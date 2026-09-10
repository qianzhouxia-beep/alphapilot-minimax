#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""signals: 透明加权打分 + 闸门。

打分 = 各因子横截面 z-score（winsor 1%/99%）× 方向 × 权重 → 加权求和。
基线刻意透明（Phase-1），有 IC 积累再换模型。
"""
import statistics as st

import config as C
import factors as F


def _zscore(vals: dict) -> dict:
    """横截面 z-score，先 winsorize 到 1/99 分位。"""
    if len(vals) < 5:
        return {}
    xs = sorted(vals.values())
    lo = xs[int(0.01 * (len(xs) - 1))]
    hi = xs[int(0.99 * (len(xs) - 1))]
    clipped = {k: min(max(v, lo), hi) for k, v in vals.items()}
    mu = st.mean(clipped.values())
    sd = st.pstdev(clipped.values())
    if not sd:
        return {k: 0.0 for k in clipped}
    return {k: (v - mu) / sd for k, v in clipped.items()}


def load_weights() -> dict:
    import dataio as io
    return io.load(C.F_WEIGHTS, None) or C.DEFAULT_WEIGHTS


def score(ctx: F.Context, date: str, weights: dict | None = None) -> list[dict]:
    """返回按分数降序的 [{code, score, contrib...}]。"""
    weights = weights or load_weights()
    raw = F.compute_all(ctx, date, names=list(weights.keys()))
    # 每因子 z 化 + 方向
    z = {}
    for nm, vals in raw.items():
        spec = weights.get(nm)
        if not spec or not vals:
            continue
        zz = _zscore(vals)
        d = spec.get("dir", 1)
        z[nm] = {k: v * d for k, v in zz.items()}
    # 加权求和（某因子缺失则不计，权重归一到可用因子）
    codes = set()
    for nm in z:
        codes |= set(z[nm].keys())
    scores = {}
    for c in codes:
        tot, wsum = 0.0, 0.0
        for nm, spec in weights.items():
            if nm in z and c in z[nm]:
                w = spec.get("w", 0.0)
                tot += w * z[nm][c]
                wsum += abs(w)
        if wsum > 0:
            scores[c] = tot / wsum
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    return [{"code": c, "score": round(s, 5)} for c, s in ranked]


def apply_gates(ctx: F.Context, date: str, ranked: list[dict]) -> tuple[list[dict], list[dict]]:
    """流动性/数据闸门。池已过流动性；此处再剔除停牌/无当日K线。"""
    passed, rejected = [], []
    for r in ranked:
        c = r["code"]
        bars, i = ctx.bar(c, date)
        if not bars:
            rejected.append({**r, "reason": "no_bar_on_date"})
            continue
        if i < C.POOL_MIN_BARS:
            rejected.append({**r, "reason": "short_history"})
            continue
        passed.append(r)
    return passed, rejected


def pick(ctx: F.Context, date: str, top_n: int = None) -> dict:
    top_n = top_n or C.SCORE_TOP_N
    ranked = score(ctx, date)
    passed, rejected = apply_gates(ctx, date, ranked)
    return {"date": date, "n_universe": len(ctx.pool), "n_scored": len(ranked),
            "n_rejected": len(rejected), "picks": passed[:top_n]}
