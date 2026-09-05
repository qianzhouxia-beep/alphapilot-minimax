#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kelly + 风险预算仓位模块 — 替换原等权分配。

流程：
  1. 每只候选票：score → 历史百分位 → 预期胜率 p、盈亏比 b（从回测校准）
  2. Half-Kelly：f* = (p·b − q)/b，再 × KELLY_FRAC
  3. 波动率调整：20日对数收益年化标准差锚定中位数，高波动缩量
  4. 行业集中度：同行业总权重 ≤ KELLY_INDUSTRY_CAP
  5. 归一化 → entry_weight

用法：
  from kelly_sizing import apply_kelly
  # 在 paper_trading_signals.py 中替代原等权
  picks = apply_kelly(picks, equity, kline_df)

环境变量：
  KELLY_ENABLE=1           启用（默认关，兼容旧等权）
  KELLY_FRAC=0.5           Half-Kelly 分数
  KELLY_MAX_POS=0.25       单票权益占比上限
  KELLY_VOL_TARGET=0.20    组合年化波动率目标
  KELLY_INDUSTRY_CAP=0.40  同行业总权重上限
  KELLY_MIN_SCORE=0        低于此分不分配仓位
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# ── 环境开关 ──
KELLY_ENABLE = os.environ.get("KELLY_ENABLE", "1").strip().lower() in (
    "1", "true", "yes", "on")
KELLY_FRAC = float(os.environ.get("KELLY_FRAC", "0.5") or 0.5)
KELLY_MAX_POS = float(os.environ.get("KELLY_MAX_POS", "0.25") or 0.25)
KELLY_VOL_TARGET = float(os.environ.get("KELLY_VOL_TARGET", "0.20") or 0.20)
KELLY_INDUSTRY_CAP = float(os.environ.get("KELLY_INDUSTRY_CAP", "0.40") or 0.40)
KELLY_MIN_SCORE = float(os.environ.get("KELLY_MIN_SCORE", "0.0") or 0.0)

# ── 回测校准默认表（score 百分位 → (win_rate, payoff)）────
# 可从 backtest 结果替换
_SCORE_BINS: list[tuple[float, float, float]] = [
    (0.95, 0.58, 2.10),
    (0.90, 0.55, 1.90),
    (0.80, 0.52, 1.80),
    (0.00, 0.50, 1.80),
]

# ── 工具函数 ──


def _annual_vol(close_series: pd.Series) -> float:
    if len(close_series) < 5:
        return 0.50
    prices = close_series.dropna().values
    if len(prices) < 5:
        return 0.50
    log_rets = np.log(prices[1:] / prices[:-1])
    return float(np.nanstd(log_rets) * np.sqrt(252))


def _zfill_sym(s: str) -> str:
    return "".join(c for c in str(s) if c.isdigit())[-6:].zfill(6)


def _norm_sym(s: str) -> str:
    raw = str(s).strip()
    for pfx in ("sh", "sz", "bj", "SH", "SZ", "BJ"):
        if raw.lower().startswith(pfx.lower()):
            raw = raw[len(pfx):]
            break
    digits = "".join(c for c in raw if c.isdigit())
    return digits[-6:].zfill(6) if digits else raw


# ── hist_stats 构建 ──


def calibrate_from_backtest(
    backtest_path: str | Path = "",
    arm: str = "A0_baseline",
) -> dict:
    """从已有 tradable 回测结果校准 win_rate/payoff 映射表。

    返回 dict { "map": {score_pct_thr: (win_rate, avg_payoff), ...} }。
    """
    if not backtest_path:
        candidates = [
            Path("/home/ubuntu/alphapilot/output/v3_tradable_gated_sleeve_backtest.json"),
            Path("/home/ubuntu/alphapilot/output/v3_tradable_gated_backtest.json"),
            Path("/home/ubuntu/alphapilot/output/v3_tradable_top3_backtest.json"),
        ]
        backtest_path = next((p for p in candidates if p.exists()), None)
    if not backtest_path:
        return {}

    data = json.loads(Path(backtest_path).read_text(encoding="utf-8"))
    trades = (data.get("trades") or {}).get(arm) or []
    if not trades and "trades" in data:
        trades = data["trades"]
    if isinstance(trades, dict):
        trades = next(iter(trades.values()), [])

    scores = []
    pnls = []
    for t in trades:
        if t.get("skipped"):
            continue
        s = float(t.get("score") or 0)
        ret = float(t.get("ret") or t.get("gross_ret") or 0)
        scores.append(s)
        pnls.append(ret)

    if not scores:
        return {}

    arr = np.column_stack([scores, pnls])
    arr = arr[arr[:, 0].argsort()]  # sort by score asc

    n = len(arr)
    bins = [(i, min(i + n // 5, n)) for i in range(0, n, max(n // 5, 1))]
    if bins[-1][1] < n:
        bins[-1] = (bins[-1][0], n)

    score_map = {}
    for lo, hi in bins:
        segment = arr[lo:hi]
        p = float((segment[:, 1] > 0).mean())
        # payoff: avg positive / avg magnitude of negative
        pos = segment[:, 1][segment[:, 1] > 0]
        neg = segment[:, 1][segment[:, 1] < 0]
        avg_win = float(pos.mean()) if len(pos) > 0 else 0.01
        avg_loss = float(abs(neg.mean())) if len(neg) > 0 else 0.01
        b = avg_win / avg_loss if avg_loss > 0 else 1.8
        pct_thr = min(float(hi) / n, 0.99)
        score_map[round(pct_thr, 2)] = (round(p, 4), round(b, 2))

    avg_p = float(np.mean([float(v) > 0 for v in pnls]))
    pos_vals = [v for v in pnls if v > 0]
    neg_vals = [v for v in pnls if v < 0]
    avg_b = (np.mean(pos_vals) / abs(np.mean(neg_vals))) if neg_vals else 1.8

    return {
        "map": dict(sorted(score_map.items())),
        "overall_win_rate": round(float(avg_p), 4),
        "overall_payoff": round(float(avg_b), 2),
        "n_trades": n,
        "source": str(backtest_path),
        "arm": arm,
    }


def _lookup_bin(score_pct: float, stat_map: dict | None) -> tuple[float, float]:
    """score_pct (0~1) → (win_rate, payoff)。"""
    if stat_map and stat_map.get("map"):
        m = stat_map["map"]
        keys = sorted(m.keys())
        for k in keys:
            if score_pct <= k:
                return m[k]
    for thr, p, b in _SCORE_BINS:
        if score_pct >= thr:
            return (p, b)
    return (0.50, 1.8)


# ── 主函数 ──


def apply_kelly(
    candidates: list[dict],
    equity: float,
    kline_df: pd.DataFrame | None = None,
    hist_stats: dict | None = None,
) -> list[dict]:
    """计算 Kelly + 风险预算权重，写入每个 candidate 的 entry_weight。

    candidates 每项需含 symbol, score（或 ml_score）。
    返回原列表，每项增加: kelly_frac, vol_factor, risk_budget_weight, entry_weight。
    """
    if not KELLY_ENABLE or not candidates or equity <= 0:
        w = 1.0 / max(len(candidates), 1)
        for c in candidates:
            c["kelly_enabled"] = False
            c["entry_weight"] = round(w, 4)
            c.setdefault("score", c.get("ml_score") or 0)
        return candidates

    scores = sorted(
        [float(c.get("score") or c.get("ml_score") or 0) for c in candidates],
        reverse=True,
    )

    # ── 1. Half-Kelly ──
    for c in candidates:
        sc = float(c.get("score") or c.get("ml_score") or 0)
        c["score"] = c.get("score") or c.get("ml_score") or sc  # ensure field
        if sc < KELLY_MIN_SCORE:
            c["kelly_frac"] = 0.0
            c["entry_weight"] = 0.0
            c["kelly_enabled"] = True
            continue

        pct = sum(1 for s in scores if s <= sc) / max(len(scores), 1)
        p, b = _lookup_bin(pct, hist_stats)
        q = 1.0 - p
        k_full = max(0.0, (p * b - q) / b) if b > 0 else 0.0
        c["kelly_frac"] = min(k_full * KELLY_FRAC, KELLY_MAX_POS)
        c["_pct"] = round(pct, 3)
        c["entry_score_pct"] = round(pct, 4)

    # ── 2. 波动率调整 ──
    if kline_df is not None and not kline_df.empty:
        df = kline_df.copy()
        df["_sym"] = df["symbol"].astype(str).map(_norm_sym) if "symbol" in df.columns else df.index
        vol_map: dict[str, float] = {}
        for sym, grp in df.groupby("_sym"):
            vol_map[sym] = _annual_vol(grp["close"])
        vols = [v for v in vol_map.values() if v > 0]
        median_vol = float(np.median(vols)) if vols else 0.50

        for c in candidates:
            sym = _zfill_sym(c.get("symbol", ""))
            vol = vol_map.get(sym, median_vol)
            if vol <= 0:
                vol = median_vol
            # 锚定中位数：vol 越高仓位越低
            c["vol_factor"] = min(median_vol / vol, 1.5) if vol > 0 else 1.0
            c["_vol"] = round(vol, 3)
            c["entry_vol"] = round(vol, 4)
    else:
        for c in candidates:
            c["vol_factor"] = 1.0

    # ── 3. 行业集中度 ──
    ind_key = lambda c: str(c.get("industry_l1") or c.get("sector") or "unknown")
    ind_groups: dict[str, list[dict]] = defaultdict(list)
    for c in candidates:
        ind_groups[ind_key(c)].append(c)
    for c in candidates:
        c["industry_count"] = len(ind_groups[ind_key(c)])

    # ── 4. 组合级风险分配 ──
    raw = [float(c.get("kelly_frac") or 0) * float(c.get("vol_factor") or 1.0) for c in candidates]
    total_raw = sum(raw)
    if total_raw > 0:
        for c, r in zip(candidates, raw):
            c["risk_budget_weight"] = r / total_raw
    else:
        eq = 1.0 / max(len(candidates), 1)
        for c in candidates:
            c["risk_budget_weight"] = eq

    # ── 行业超限裁剪 ──
    for ind, grp in ind_groups.items():
        total_w = sum(c.get("risk_budget_weight") or 0 for c in grp)
        if total_w > KELLY_INDUSTRY_CAP and total_w > 0:
            factor = KELLY_INDUSTRY_CAP / total_w
            for c in grp:
                c["risk_budget_weight"] = (c.get("risk_budget_weight") or 0) * factor

    # 重新归一化
    resid = sum(c.get("risk_budget_weight") or 0 for c in candidates)
    if resid > 0 and abs(resid - 1.0) > 0.01:
        factor = 1.0 / resid
        for c in candidates:
            c["risk_budget_weight"] = (c.get("risk_budget_weight") or 0) * factor

    # ── 5. entry_weight ──
    for c in candidates:
        w = c.get("risk_budget_weight") or 0
        c["entry_weight"] = round(w, 4)
        c["kelly_enabled"] = True

    return candidates


def apply_kelly_to_picks(
    picks_data: dict,
    pt: dict | None = None,
    kline_df: pd.DataFrame | None = None,
    hist_stats: dict | None = None,
) -> dict:
    """给 paper_trading_signals.py 调用的便捷包装。

    picks_data: morning_live_picks.json 的完整 dict（含 "picks" 列表）
    pt: data/paper_trading.json（取 equity = cash + market_value）
    """
    candidates = list(picks_data.get("picks") or [])
    if not candidates:
        return picks_data

    equity = 0.0
    if pt:
        cash = float(pt.get("account", {}).get("cash", 0))
        mv = sum(
            float(p.get("quantity", 0)) * float(p.get("current_price", 0) or p.get("buy_price", 0))
            for s in pt.get("strategies", [])
            for p in s.get("positions", [])
        )
        equity = cash + mv
    if equity <= 0:
        equity = float(pt.get("initial_capital") or 1_000_000) if pt else 1_000_000

    candidates = apply_kelly(candidates, equity, kline_df, hist_stats)
    picks_data["picks"] = candidates
    picks_data["kelly_enabled"] = KELLY_ENABLE
    picks_data["kelly_config"] = {
        "frac": KELLY_FRAC,
        "max_pos": KELLY_MAX_POS,
        "vol_target": KELLY_VOL_TARGET,
        "industry_cap": KELLY_INDUSTRY_CAP,
        "min_score": KELLY_MIN_SCORE,
    }
    return picks_data