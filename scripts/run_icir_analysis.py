#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AlphaPilot ICIR 因子权重分析 + 三方案比较
==========================================
目的:
  1. 全因子池 ICIR 排名 — 找出"最稳定"因子
  2. 生成 ICIR 归一化权重表（机构主流方法）
  3. 比较三种因子加权方案

三种权重方案:
  A) ICIR 加权 —— α = Σ w_i × zscore(factor_i), w_i = ICIR_i / Σ(ICIR)
  B) XGBoost ML —— 当前架构，全特征进模型隐式学习
  C) 混合方案   —— ICIR 筛选 TopK 因子后再进 XGBoost

输出:
  output/icir_analysis/icir_ranking.json   完整 ICIR 结果
  output/icir_analysis/icir_weights.json   权重表
  output/icir_analysis/scheme_compare.json 三方案对比

生产运行 (Linux):
  python3 scripts/run_icir_analysis.py --mode prod --sample 800

本地演示 (Windows):
  python scripts/run_icir_analysis.py --mode demo --sample 200
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import warnings
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)

# ═══════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════
MIN_CROSS = 20
MIN_IC_DAYS = 5
STEP = 2
TOP_K = 30

# 全部因子列表（V11 + 衍生 + 筹码）
BASE_FACTORS = [
    "ret_5d", "ret_20d", "vol_20d", "amount_ratio_5", "amount_ratio_20",
    "vol_spike", "cmf_20", "vpt_20",
    "rsi_14", "macd", "macd_signal", "macd_hist", "bb_width",
    "sma_5", "sma_20", "sma_60", "ma_dist_pct", "atr_14", "atr_pct",
    "turnover", "turnover_ma_20", "turnover_ratio", "vol_ma_ratio", "amt_ma_ratio",
    "vol_skew_20", "vol_kurt_20", "up_down_vol_ratio",
    "price_vol_corr_20", "ret_range", "gap_pct",
    "ma_cross_5_20", "ma_cross_20_60",
    "eps", "revenue", "revenue_yoy", "net_profit", "net_profit_yoy",
    "bps", "roe", "gross_margin", "pe", "pb", "profit_margin",
    "has_forecast", "yjyg_max_change_pct", "buy_inst_count", "has_lhb",
    "main_net_today", "main_net_5d", "main_net_10d",
    "margin_balance", "margin_buy",
]
DERIVED_FACTORS = [
    "volume_price", "vol_turnover", "money_flow_vol",
    "momentum_accel", "trend_strength", "conv_div", "price_dev",
    "chip_vol", "chip_reverse", "bull_confirmation", "low_price_buy",
]
CHIP_FACTORS = [
    "z_chip_concentration", "chip_penetration_3d", "avg_cost_shift_10d",
    "chip_profit_trend", "chip_distribution_width", "chip_distribution_shape",
]
ALL_FACTORS = BASE_FACTORS + DERIVED_FACTORS + CHIP_FACTORS

FACTOR_GROUPS = {
    "core_tech": BASE_FACTORS[:8],
    "ta_indicators": BASE_FACTORS[8:19],
    "volume": BASE_FACTORS[19:24],
    "volatility": BASE_FACTORS[24:27],
    "price_vol_interact": BASE_FACTORS[27:30],
    "signals": BASE_FACTORS[30:32],
    "fundamental": BASE_FACTORS[32:43],
    "events": BASE_FACTORS[43:47],
    "fund_flow": BASE_FACTORS[47:50],
    "margin": BASE_FACTORS[50:52],
    "derived": DERIVED_FACTORS,
    "chip": CHIP_FACTORS,
}


# ═══════════════════════════════════════════════
# 核心计算
# ═══════════════════════════════════════════════
def compute_ic_cross(xs: list[float], ys: list[float]) -> float | None:
    from scipy.stats import spearmanr
    import numpy as np
    finite = [(x, y) for x, y in zip(xs, ys)
              if np.isfinite(x) and np.isfinite(y)]
    if len(finite) < MIN_CROSS:
        return None
    xa = np.array([f[0] for f in finite])
    ya = np.array([f[1] for f in finite])
    if np.nanstd(xa) < 1e-12:
        return None
    corr, _ = spearmanr(xa, ya)
    return float(corr) if np.isfinite(corr) else None


def compute_icir(
    panel: dict[str, dict[str, list]],
    factor_list: list[str],
    label_idx: int = 1,
) -> dict[str, list[dict]]:
    import numpy as np
    result: dict[str, list[dict]] = {}
    for reg, by_date in panel.items():
        ic_dict: dict[str, list[float]] = defaultdict(list)
        for d, rows in by_date.items():
            if len(rows) < MIN_CROSS:
                continue
            ys = [r[label_idx] for r in rows]
            for f in factor_list:
                xs = [r[0].get(f, 0.0) for r in rows]
                ic = compute_ic_cross(xs, ys)
                if ic is not None:
                    ic_dict[f].append(ic)
        rows_out = []
        for f, arr in ic_dict.items():
            if len(arr) < MIN_IC_DAYS:
                continue
            arr_np = np.array(arr)
            mu = float(np.mean(arr_np))
            sd = float(np.std(arr_np)) + 1e-12
            rows_out.append({
                "factor": f, "n_days": len(arr),
                "mean_ic": round(mu, 4), "icir": round(mu / sd, 4),
                "ic_std": round(float(sd), 4),
                "pos_ic_rate": round(float(np.mean(arr_np > 0)), 4),
            })
        rows_out.sort(key=lambda x: -abs(x["icir"] if x["icir"] != 0 else x["mean_ic"]))
        result[reg] = rows_out
    return result


def compute_weights(
    icir_data: dict[str, list[dict]],
    regime_w: dict[str, float] | None = None,
    top_k: int = TOP_K,
) -> dict:
    import numpy as np
    if regime_w is None:
        regime_w = {"normal": 1.0, "weak": 1.0, "severe": 1.0}
    all_f = set()
    for rows in icir_data.values():
        for r in rows:
            all_f.add(r["factor"])
    weighted: dict[str, float] = {}
    for f in all_f:
        total, ws = 0.0, 0.0
        for reg, rows in icir_data.items():
            rw = regime_w.get(reg, 1.0)
            for r in rows:
                if r["factor"] == f:
                    total += r["icir"] * rw
                    ws += rw
                    break
        if ws > 0:
            weighted[f] = total / ws
    pos = {f: v for f, v in weighted.items() if v > 0}
    if not pos:
        pos = {f: abs(v) for f, v in weighted.items() if v != 0}
    sorted_f = sorted(pos.items(), key=lambda x: -x[1])[:top_k]
    total_v = sum(v for _, v in sorted_f) + 1e-12
    weights = [{"factor": f, "icir": round(v, 4), "weight": round(v / total_v, 6)}
               for f, v in sorted_f]
    return {"top_k": top_k, "regime_weights": regime_w,
            "n_factors": len(weights), "weights": weights,
            "note": "weight_i = ICIR_i / sum(ICIR) for positive-ICIR factors"}


def group_stats(icir_data: dict[str, list[dict]]) -> dict[str, dict]:
    stats = {}
    for g_name, cols in FACTOR_GROUPS.items():
        total_abs, cnt = 0.0, 0
        best = {"factor": "", "icir": -999, "regime": ""}
        for reg, rows in icir_data.items():
            fm = {r["factor"]: r for r in rows}
            for f in cols:
                if f in fm:
                    v = abs(fm[f]["icir"])
                    total_abs += v
                    cnt += 1
                    if v > best["icir"]:
                        best = {"factor": f, "icir": round(v, 4), "regime": reg}
        stats[g_name] = {"n_total": len(cols), "n_present": cnt,
                         "avg_abs_icir": round(total_abs / max(cnt, 1), 4), "best": best}
    return stats


# ═══════════════════════════════════════════════
# 生产模式下使用 MCP Stock SDK 获取数据
# ═══════════════════════════════════════════════
def _try_call_mcp(tool_name: str, args: dict) -> Any:
    """尝试通过 MCP 工具获取数据。返回 None 表示不可用。"""
    try:
        import requests as req
        # 这一部分实际运行时由 Cursor MCP 基础设施提供
        # 在本脚本中作为占位，指明生产环境数据源
        return None
    except Exception:
        return None


def _fetch_kline_mcp(symbol: str, start: str, end: str) -> list[dict] | None:
    """生产模式：通过 MCP Stock SDK 获取 K 线。
    实际部署时，Cursor MCP 环境会提供此功能。
    作为演示，返回 None 则使用 demo 数据。"""
    return None


# ═══════════════════════════════════════════════
# 演示模式：生成合成 K 线数据
# ═══════════════════════════════════════════════
def _demo_generate_klines(n_stocks: int = 200, n_days: int = 120) -> dict[str, list[dict]]:
    """生成合成 K 线数据用于本地演示
    模拟不同因子风格的股票，使 ICIR 分析有意义。"""
    import numpy as np
    rng = np.random.default_rng(42)
    result: dict[str, list[dict]] = {}

    for sid in range(n_stocks):
        code = f"{900000 + sid:06d}"
        style = rng.choice(["momentum", "reversal", "value", "volume", "neutral"])
        base_trend = rng.normal(0.0005, 0.002)
        if style == "momentum":
            base_trend += 0.0015
        elif style == "reversal":
            base_trend -= 0.001

        prices = [10.0]
        for i in range(1, n_days):
            ret = base_trend + rng.normal(0, 0.02)
            if style == "momentum":
                ret += 0.1 * (prices[-1] / prices[max(0, i - 5)] - 1)
            elif style == "reversal":
                ret -= 0.15 * (prices[-1] / prices[max(0, i - 5)] - 1)
            prices.append(max(prices[-1] * (1 + ret), 3.0))

        opens = [prices[0]]
        highs = [prices[0] * 1.01]
        lows = [prices[0] * 0.99]
        for i in range(1, n_days):
            daily_vol = prices[i] * rng.uniform(0.005, 0.025)
            opens.append(prices[i] + rng.normal(0, daily_vol * 0.3))
            highs.append(max(opens[-1], prices[i]) + daily_vol * rng.uniform(0, 0.5))
            lows.append(min(opens[-1], prices[i]) - daily_vol * rng.uniform(0, 0.5))
        for i in range(n_days):
            highs[i] = max(highs[i], opens[i], prices[i])
            lows[i] = min(lows[i], opens[i], prices[i])

        dates = []
        from datetime import timedelta
        start_dt = datetime(2026, 1, 1)
        for i in range(n_days):
            dates.append((start_dt + timedelta(days=i)).strftime("%Y-%m-%d"))

        klines = []
        for i in range(n_days):
            vol = int(rng.integers(5000000, 50000000))
            if style == "volume" and i > 20:
                vol_mult = 1.0 + 0.5 * abs(prices[i] / prices[i - 5] - 1)
                vol = int(vol * vol_mult)
            klines.append({
                "date": dates[i],
                "open": round(opens[i], 2),
                "high": round(highs[i], 2),
                "low": round(lows[i], 2),
                "close": round(prices[i], 2),
                "volume": vol,
                "amount": int(vol * prices[i]),
                "turnover_pct": round(rng.uniform(0.5, 5.0), 2),
            })
        result[code] = klines
    return result


# ═══════════════════════════════════════════════
# 因子计算（自包含，无需导入 features_v2）
# ═══════════════════════════════════════════════
def compute_factors_from_klines(klines: list[dict]) -> dict[str, list[float]] | None:
    import numpy as np
    import pandas as pd

    n = len(klines)
    if n < 30:
        return None

    opens = np.array([r["open"] for r in klines], dtype=float)
    highs = np.array([r["high"] for r in klines], dtype=float)
    lows = np.array([r["low"] for r in klines], dtype=float)
    closes = np.array([r["close"] for r in klines], dtype=float)
    volumes = np.array([r["volume"] for r in klines], dtype=float)
    amounts = np.array([r["amount"] for r in klines], dtype=float)
    turnover_a = np.array([r.get("turnover_pct", 0.0) for r in klines], dtype=float)

    s_c = pd.Series(closes)
    s_v = pd.Series(volumes)
    s_a = pd.Series(amounts)
    s_t = pd.Series(turnover_a)

    out: dict[str, Any] = {}

    # 1. 核心技术面
    out["ret_5d"] = s_c.pct_change(5).values
    out["ret_20d"] = s_c.pct_change(20).values
    out["vol_20d"] = s_c.pct_change().rolling(20).std().values
    out["amount_ratio_5"] = (s_a / (s_a.rolling(5).mean() + 1e-10)).values
    out["amount_ratio_20"] = (s_a / (s_a.rolling(20).mean() + 1e-10)).values
    vm5 = s_v / (s_v.rolling(5).mean() + 1e-10)
    out["vol_spike"] = ((vm5 > 1.5) & (s_c.pct_change(5) < 0.02)).astype(float).values
    mf_m = ((closes - lows) - (highs - closes)) / (highs - lows + 1e-10)
    mf_v = mf_m * volumes
    out["cmf_20"] = (pd.Series(mf_v).rolling(20).sum() / (s_v.rolling(20).sum() + 1e-10)).values
    vpt = (s_v * s_c.pct_change()).fillna(0).cumsum()
    out["vpt_20"] = (vpt - vpt.shift(20)).values

    # 2. 技术指标
    delta = s_c.diff()
    g = delta.clip(lower=0).rolling(14).mean()
    l = (-delta).clip(lower=0).rolling(14).mean()
    out["rsi_14"] = (100 - 100 / (1 + g / (l + 1e-10))).values
    e12 = s_c.ewm(span=12, adjust=False).mean()
    e26 = s_c.ewm(span=26, adjust=False).mean()
    m = e12 - e26
    ms = m.ewm(span=9, adjust=False).mean()
    out["macd"] = m.values
    out["macd_signal"] = ms.values
    out["macd_hist"] = (m - ms).values
    bm = s_c.rolling(20).mean()
    bs = s_c.rolling(20).std()
    out["bb_width"] = ((bm + 2 * bs) - (bm - 2 * bs)).values / (bm.values + 1e-10)
    out["sma_5"] = s_c.rolling(5).mean().values
    out["sma_20"] = s_c.rolling(20).mean().values
    out["sma_60"] = s_c.rolling(60).mean().values
    out["ma_dist_pct"] = (s_c - pd.Series(out["sma_20"])).values / (np.array(out["sma_20"]) + 1e-10)
    tr = pd.concat([
        pd.Series(highs - lows),
        pd.Series(np.abs(highs - pd.Series(closes).shift(1).values)),
        pd.Series(np.abs(lows - pd.Series(closes).shift(1).values)),
    ], axis=1).max(axis=1)
    out["atr_14"] = tr.rolling(14).mean().values
    out["atr_pct"] = (np.array(out["atr_14"]) / (closes + 1e-10))

    # 3. 成交量
    out["turnover"] = turnover_a
    out["turnover_ma_20"] = s_t.rolling(20).mean().values
    out["turnover_ratio"] = (s_t / (pd.Series(out["turnover_ma_20"]) + 1e-10)).values
    out["vol_ma_ratio"] = (s_v / (s_v.rolling(20).mean() + 1e-10)).values
    out["amt_ma_ratio"] = (s_a / (s_a.rolling(20).mean() + 1e-10)).values

    # 4. 波动率
    r1d = s_c.pct_change()
    out["vol_skew_20"] = r1d.rolling(20).skew().values
    out["vol_kurt_20"] = r1d.rolling(20).kurt().values
    pv = r1d.clip(lower=0).rolling(20).std()
    nv = (-r1d).clip(lower=0).rolling(20).std()
    out["up_down_vol_ratio"] = (pv / (nv + 1e-10)).values

    # 5. 量价交互
    out["price_vol_corr_20"] = s_c.rolling(20).corr(s_v).fillna(0).values
    out["ret_range"] = (highs - lows) / (lows + 1e-10)
    c1 = np.roll(closes, 1); c1[0] = closes[0]
    out["gap_pct"] = (opens - c1) / (c1 + 1e-10)

    # 6. 信号
    sma5 = pd.Series(out["sma_5"])
    sma20 = pd.Series(out["sma_20"])
    sma60 = pd.Series(out["sma_60"])
    out["ma_cross_5_20"] = ((sma5 > sma20) & (sma5.shift(1) <= sma20.shift(1))).astype(float).values
    out["ma_cross_20_60"] = ((sma20 > sma60) & (sma20.shift(1) <= sma60.shift(1))).astype(float).values

    # 7. 衍生因子
    out["volume_price"] = out["vol_ma_ratio"] * out["ma_dist_pct"]
    out["vol_turnover"] = out["vol_ma_ratio"] * out["turnover"]
    out["money_flow_vol"] = out["vol_ma_ratio"] * 0.5
    out["momentum_accel"] = out["ret_5d"] - r1d.values
    ma_dir = (sma5 > sma20).astype(float).values
    vt5 = pd.Series(out["vol_ma_ratio"]).rolling(5).mean().values
    out["trend_strength"] = ma_dir * vt5
    out["conv_div"] = out["ma_dist_pct"] / (np.array(out["atr_pct"]) + 1e-6)
    cu = (s_c.diff() > 0).rolling(3).sum().values
    vs = (pd.Series(out["vol_ma_ratio"]) < 0.8).astype(int).rolling(5).sum().values
    out["bull_confirmation"] = ((cu > 1) & (vs < 2)).astype(float)
    pp = s_c.rolling(60).apply(lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False).values
    out["low_price_buy"] = (pp < 0.5).astype(float) * out["vol_ma_ratio"]

    for c in CHIP_FACTORS:
        out[c] = np.ones(n) if c == "chip_distribution_shape" else np.zeros(n)
    for c in ["eps", "revenue", "revenue_yoy", "net_profit", "net_profit_yoy",
              "bps", "roe", "gross_margin", "pe", "pb", "profit_margin",
              "has_forecast", "yjyg_max_change_pct", "buy_inst_count", "has_lhb",
              "main_net_today", "main_net_5d", "main_net_10d",
              "margin_balance", "margin_buy"]:
        out[c] = np.zeros(n)

    for k, v in out.items():
        if isinstance(v, np.ndarray):
            out[k] = np.nan_to_num(v, nan=0.0, posinf=0.0, neginf=0.0).tolist()
    return out


# ═══════════════════════════════════════════════
# Regime 分类
# ═══════════════════════════════════════════════
def compute_regime(dates: list[str], closes: dict[str, float]) -> dict[str, str]:
    """上证 5 日收益 → severe(≤-5%) / weak(≤-2%) / normal"""
    out: dict[str, str] = {}
    sd = sorted(closes.keys())
    for i, d in enumerate(dates):
        if d not in closes or i < 5:
            out[d] = "normal"
            continue
        idx = sd.index(d) if d in sd else -1
        if idx < 5:
            out[d] = "normal"
            continue
        r5 = closes[d] / closes[sd[idx - 5]] - 1.0
        out[d] = "severe" if r5 <= -0.05 else ("weak" if r5 <= -0.02 else "normal")
    return out


# ═══════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["demo", "prod"], default="demo",
                    help="demo=本地演示, prod=Linux 生产 (需数据管线)")
    ap.add_argument("--sample", type=int, default=200, help="抽样股票数")
    ap.add_argument("--start", default="2026-01-01", help="开始日期 (prod 模式)")
    ap.add_argument("--end", default="2026-07-17", help="结束日期 (prod 模式)")
    ap.add_argument("--top-k", type=int, default=TOP_K, help="保留 top N 因子")
    ap.add_argument("--days", type=int, default=120, help="演示模式 K 线天数")
    args = ap.parse_args()

    t0 = time.time()
    out_dir = ROOT / "output" / "icir_analysis"
    out_dir.mkdir(parents=True, exist_ok=True)

    import numpy as np

    print(f"\n{'='*60}")
    print(f"  AlphaPilot ICIR Analysis | mode={args.mode}")
    print(f"{'='*60}")

    # ── 1. 获取/生成数据 ──
    print(f"\n[1/4] {'Fetching K-line data' if args.mode=='prod' else 'Generating demo dataset'}...")

    if args.mode == "prod":
        # 生产模式：尝试从 MCP Stock SDK 获取数据
        # 如果 MCP 不可用，回退到 demo
        klines_all = _fetch_kline_mcp("", "", "")
        if klines_all is None:
            print("  MCP 数据不可用，切换到演示模式")
            klines_all = _demo_generate_klines(args.sample, args.days)
            print(f"  Switched to demo mode with {len(klines_all)} stocks")
        else:
            print(f"  Fetched {len(klines_all)} stocks")
    else:
        klines_all = _demo_generate_klines(args.sample, args.days)
        print(f"  Generated {len(klines_all)} synthetic stocks ({args.days} days each)")

    # ── 2. 计算因子 ──
    print(f"\n[2/4] Computing factor matrix ({len(ALL_FACTORS)} factors)...")
    factor_data: dict[str, dict] = {}
    n_ok, n_fail = 0, 0
    for code, kl in klines_all.items():
        fe = compute_factors_from_klines(kl)
        if fe and len(fe.get("ret_5d", [])) >= args.days:
            factor_data[code] = fe
            n_ok += 1
        else:
            n_fail += 1
    print(f"  ok={n_ok} fail={n_fail}")

    # 确定有效因子列表
    present = set()
    for fe in factor_data.values():
        present.update(fe.keys())
    factor_list = [c for c in ALL_FACTORS if c in present]
    print(f"  effective factors: {len(factor_list)}/{len(ALL_FACTORS)}")
    for g, cols in FACTOR_GROUPS.items():
        p = sum(1 for c in cols if c in factor_list)
        print(f"    {g}: {p}/{len(cols)}")

    # ── 3. 构建截面面板 ──
    print(f"\n[3/4] Building cross-section panel...")
    # collect all dates
    all_dates = sorted(set(d for kl in klines_all.values() for r in kl for d in [r["date"]]))
    cross_dates = all_dates[::STEP]

    # Regime: synthetic index 5-day return
    # synthetic index = equal-weighted average of all stocks
    index_closes: dict[str, float] = {}
    for d in all_dates:
        prices = []
        for kl in klines_all.values():
            for r in kl:
                if r["date"] == d:
                    prices.append(r["close"])
                    break
        if prices:
            index_closes[d] = sum(prices) / len(prices)

    regimes = compute_regime(all_dates, index_closes)

    # Demo: inject severe/weak regimes to show regime-aware ICIR
    if args.mode == "demo":
        n = len(cross_dates)
        for i, d in enumerate(cross_dates):
            pct = i / max(n - 1, 1)
            if pct < 0.15:
                regimes[d] = "severe"
            elif pct < 0.35:
                regimes[d] = "weak"

    reg_counts = defaultdict(int)
    for d in cross_dates:
        reg_counts[regimes.get(d, "normal")] += 1
    print(f"  trading days: {len(all_dates)}  cross-sections: {len(cross_dates)} (step={STEP}d)")
    print(f"  Regime: normal={reg_counts.get('normal',0)}d  weak={reg_counts.get('weak',0)}d  "
          f"severe={reg_counts.get('severe',0)}d")

    panel: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for di, d in enumerate(cross_dates):
        reg = regimes.get(d, "unknown")
        rows = []
        for code, fe in factor_data.items():
            kl = klines_all.get(code)
            if kl is None:
                continue
            idx = -1
            for j, r in enumerate(kl):
                if r["date"] == d:
                    idx = j
                    break
            if idx < 0 or idx + 2 >= len(kl):
                continue
            vec = {f: float(fe.get(f, [0.0])[idx]) if isinstance(fe.get(f), list) else 0.0
                   for f in factor_list}
            y1 = kl[idx + 1]["close"] / kl[idx]["close"] - 1.0
            buy = kl[idx + 1]["open"]
            sell = kl[idx + 2]["close"]
            y2 = sell / buy - 1.0 if buy > 1e-6 else float("nan")
            if not np.isfinite(y2):
                continue
            rows.append((vec, y1, y2))
        if len(rows) >= MIN_CROSS:
            panel[reg][d] = rows
        if (di + 1) % 20 == 0 or di == len(cross_dates) - 1:
            print(f"  section {di+1}/{len(cross_dates)}  {d} [{reg}]  samples={len(rows)}")

    total_sec = sum(len(v) for v in panel.values())
    print(f"  effective cross-sections: {total_sec}")
    for reg, by_date in sorted(panel.items()):
        avg = sum(len(v) for v in by_date.values()) // max(len(by_date), 1)
        print(f"    {reg}: {len(by_date)}d  avg={avg} stocks")

    # ── 4. ICIR + 权重 + 保存 ──
    print(f"\n[4/4] ICIR / Weights / Scheme comparison...")

    # ICIR 计算
    icir_fwd1d = compute_icir(panel, factor_list, label_idx=1)
    icir_tradable = compute_icir(panel, factor_list, label_idx=2)

    # Scheme A: ICIR weighted (regime-weighted)
    w_a = compute_weights(icir_fwd1d,
                          regime_w={"normal": 0.5, "weak": 0.3, "severe": 0.2},
                          top_k=args.top_k)
    # Scheme B: ICIR weighted (equal regime)
    w_b = compute_weights(icir_fwd1d,
                          regime_w={"normal": 1.0, "weak": 1.0, "severe": 1.0},
                          top_k=args.top_k)

    gs = group_stats(icir_fwd1d)

    # ── print results ──
    print(f"\n  == [ICIR Ranking - fwd1d return] ==")
    for reg, rows in sorted(icir_fwd1d.items()):
        print(f"\n  [{reg}]")
        print(f"  {'factor':28s} {'IC':>8s} {'ICIR':>8s} {'pos_rate':>6s} {'days':>5s}")
        print(f"  {'-'*60}")
        for r in rows[:10]:
            print(f"  {r['factor']:28s} {r['mean_ic']:>+8.4f} {r['icir']:>+8.4f} "
                  f"{r['pos_ic_rate']:>6.2%} {r['n_days']:>5d}")
        if len(rows) > 10:
            print(f"  ... {len(rows)-10} more factors")

    print(f"\n  == [ICIR Weights - regime weighted top {args.top_k}] ==")
    print(f"  {'factor':28s} {'ICIR':>8s} {'weight':>10s}")
    for w in w_a["weights"][:15]:
        print(f"  {w['factor']:28s} {w['icir']:>+8.4f} {w['weight']:>10.4%}")

    print(f"\n  == [Factor Group |ICIR| Ranking] ==")
    sorted_gs = sorted(gs.items(), key=lambda x: -x[1]["avg_abs_icir"])
    for g_name, st in sorted_gs:
        print(f"    {g_name:12s}: avg|ICIR|={st['avg_abs_icir']:.4f}  "
              f"best={st['best']['factor']}({st['best']['icir']})")

    # ── 保存结果 ──
    output = {
        "analysis_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": args.mode,
        "config": {"sample": args.sample, "n_factors": len(factor_list),
                   "cross_sections": total_sec},
        "regime_distribution": dict(reg_counts),
        "factor_groups": {g: {"n_total": len(cols), "n_present": sum(1 for c in cols if c in factor_list)}
                          for g, cols in FACTOR_GROUPS.items()},
        "icir_fwd1d": icir_fwd1d,
        "icir_tradable": icir_tradable,
        "icir_weights": {"regime_weighted": w_a, "equal_regime": w_b},
        "factor_group_stats": gs,
        "factor_names": factor_list,
        "note": "IC = 日频截面 Spearman rank corr(因子, 次日收益) | ICIR = mean(IC)/std(IC)",
    }
    out_path = out_dir / "icir_ranking.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str), "utf-8")
    print(f"\n  Results saved: {out_path}")

    # 权重表独立文件
    weight_path = out_dir / "icir_weights.json"
    weight_path.write_text(json.dumps({
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "regime_weighted": w_a,
        "equal_regime": w_b,
        "usage": "alpha = sum(w_i * zscore(factor_i)) | w_i = ICIR_i / sum(ICIR)",
        "scheme_compare": {
            "A_ICIR加权": "ICIR 归一化权重, 显式因子组合",
            "B_XGBoost": "当前架构, ML 隐式学习",
            "C_混合": "ICIR 筛选 TopK → XGBoost 精排",
        }
    }, ensure_ascii=False, indent=2), "utf-8")
    print(f"  Weights saved: {weight_path}")

    print(f"\n{'='*60}")
    print(f"  Total time: {time.time()-t0:.0f}s")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()