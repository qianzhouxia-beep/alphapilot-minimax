#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""四类启动形态识别 — 替代粗糙「量价金叉」硬过滤。

形态:
  1. accumulation_breakout  底部横盘吸筹 → 放量突破
  2. pullback_rebound       放量上攻后缩量回踩 → 再起
  3. plateau_breakout       平台整理 → 首次放量突破
  4. trend_resume           上升趋势中继 N 形加速

约定:
  - asof 日 = 最近一个已收盘交易日（当日收盘数据 → 预测下一交易日）
  - 不写死日历日期；回测用 asof_idx 截断
"""
from __future__ import annotations

import json
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
KLINE_PARQUET = ROOT / "data" / "kline_cache" / "kline_all.parquet"
FUND_HIST = ROOT / "data" / "fund_flow_history.json"

PATTERN_NAMES = (
    "accumulation_breakout",
    "pullback_rebound",
    "plateau_breakout",
    "trend_resume",
)


def _bare(sym: str) -> str:
    s = str(sym or "").lower().replace("sh", "").replace("sz", "").replace("bj", "")
    return s[-6:] if len(s) >= 6 else s


def _vol_col(kl: pd.DataFrame) -> str:
    return "volume" if "volume" in kl.columns else "amount"


def _prep(kl: pd.DataFrame, asof_idx: int | None = None) -> pd.DataFrame | None:
    if kl is None or kl.empty:
        return None
    sub = kl.sort_values("date").reset_index(drop=True)
    if asof_idx is not None:
        if asof_idx < 0 or asof_idx >= len(sub):
            return None
        sub = sub.iloc[: asof_idx + 1].reset_index(drop=True)
    if len(sub) < 61:
        return None
    return sub


def _series(kl: pd.DataFrame) -> dict[str, np.ndarray]:
    c = kl["close"].astype(float).values
    h = kl["high"].astype(float).values
    lo = kl["low"].astype(float).values
    o = kl["open"].astype(float).values if "open" in kl.columns else c
    v = kl[_vol_col(kl)].astype(float).values
    return {"c": c, "h": h, "lo": lo, "o": o, "v": v}


def _ma(arr: np.ndarray, n: int) -> np.ndarray:
    return pd.Series(arr).rolling(n, min_periods=n).mean().values


def _safe_div(a: float, b: float, default: float = 0.0) -> float:
    if b is None or abs(b) < 1e-12 or math.isnan(b):
        return default
    return a / b


def _fund_net_sum(fund_hist: dict | None, lookback: int = 3) -> float | None:
    """近 lookback 日主力净流入合计；无数据返回 None。"""
    if not fund_hist or not isinstance(fund_hist, dict):
        return None
    series = fund_hist
    if "data" in series and isinstance(series["data"], dict):
        series = series["data"]
    days = sorted(str(d)[:10] for d in series.keys())[-lookback:]
    if len(days) < max(2, lookback - 1):
        return None
    total = 0.0
    for d in days:
        v = series.get(d) or series.get(d.replace("-", ""))
        try:
            if isinstance(v, dict):
                total += float(v.get("main_net") or v.get("net") or 0)
            else:
                total += float(v or 0)
        except (TypeError, ValueError):
            pass
    return total


# ═══════════════════════════════════════════════════════════════
# 形态 1：底部 W / 横盘吸筹突破
# ═══════════════════════════════════════════════════════════════
def is_accumulation_breakout(
    kl: pd.DataFrame,
    fund_hist: dict | None = None,
    asof_idx: int | None = None,
) -> bool:
    """长期横盘(>20日振幅<20%) → 缩量洗 → 放量突破平台 + 资金非流出。"""
    sub = _prep(kl, asof_idx)
    if sub is None or len(sub) < 40:
        return False
    s = _series(sub)
    c, h, lo, v = s["c"], s["h"], s["lo"], s["v"]
    l = len(c) - 1
    win = 20
    platform_hi = float(np.max(h[l - win : l]))  # 不含今日
    platform_lo = float(np.min(lo[l - win : l]))
    if platform_lo <= 0:
        return False
    amp = (platform_hi - platform_lo) / platform_lo
    if amp >= 0.20:
        return False

    vm20 = _ma(v, 20)
    if np.isnan(vm20[l]) or vm20[l] <= 0:
        return False
    # 近 5 日曾缩量，今日放量
    recent_shrink = any(v[l - i] < vm20[l] * 0.65 for i in range(1, 6) if l - i >= 0)
    today_expand = v[l] > vm20[l] * 1.5
    breakout = c[l] > platform_hi * 1.005
    if not (recent_shrink and today_expand and breakout):
        return False

    fund_sum = _fund_net_sum(fund_hist, 3)
    if fund_sum is not None and fund_sum < 0:
        return False
    return True


# ═══════════════════════════════════════════════════════════════
# 形态 2：缩量回踩支撑放量再起
# ═══════════════════════════════════════════════════════════════
def is_pullback_rebound(kl: pd.DataFrame, asof_idx: int | None = None) -> bool:
    """前期放量上攻 → 缩量回踩 MA20/MA60 → 获支撑 → 放量中阳。"""
    sub = _prep(kl, asof_idx)
    if sub is None or len(sub) < 65:
        return False
    s = _series(sub)
    c, h, lo, v = s["c"], s["h"], s["lo"], s["v"]
    l = len(c) - 1
    ma20 = _ma(c, 20)
    ma60 = _ma(c, 60)
    vm60 = _ma(v, 60)
    if any(np.isnan(x[l]) for x in (ma20, ma60, vm60)):
        return False

    # 前期 21~40 日前有放量上涨波段
    prior = slice(max(0, l - 40), max(0, l - 20))
    if prior.stop - prior.start < 5:
        return False
    prior_vol_peak = float(np.max(v[prior]))
    prior_ret = _safe_div(float(c[l - 21]), float(c[max(0, l - 40)]), 1.0) - 1.0
    if prior_vol_peak < vm60[l] * 1.4 or prior_ret < 0.05:
        return False

    # 近 3~5 日缩量回踩
    pull_n = 5
    pull_vols = v[l - pull_n : l]
    if len(pull_vols) < 3:
        return False
    if float(np.mean(pull_vols)) > vm60[l] * 0.75:
        return False
    # 回踩不破 MA60，且触及 MA20±3% 或 MA60±3%
    lows = lo[l - pull_n : l]
    support = float(min(ma20[l], ma60[l]))
    if float(np.min(lows)) < support * 0.97:
        return False
    near_ma = abs(float(np.min(lows)) / ma20[l] - 1.0) < 0.03 or abs(
        float(np.min(lows)) / ma60[l] - 1.0
    ) < 0.04

    # 今日放量中阳 1%~5%
    day_ret = _safe_div(c[l], c[l - 1], 1.0) - 1.0
    today_ok = v[l] > vm60[l] * 1.2 and 0.01 <= day_ret <= 0.05 and c[l] > ma20[l]
    return bool(near_ma and today_ok)


# ═══════════════════════════════════════════════════════════════
# 形态 3：平台突破加速
# ═══════════════════════════════════════════════════════════════
def is_plateau_breakout(kl: pd.DataFrame, asof_idx: int | None = None) -> bool:
    """横向整理平台(>10日, 振幅<15%) → 首次放量突破平台高点。"""
    sub = _prep(kl, asof_idx)
    if sub is None or len(sub) < 25:
        return False
    s = _series(sub)
    c, h, lo, v = s["c"], s["h"], s["lo"], s["v"]
    l = len(c) - 1
    win = 10
    plat_hi = float(np.max(h[l - win : l]))
    plat_lo = float(np.min(lo[l - win : l]))
    if plat_lo <= 0:
        return False
    amp = (plat_hi - plat_lo) / plat_lo
    if amp >= 0.15:
        return False

    vm10 = _ma(v, 10)
    if np.isnan(vm10[l]) or vm10[l] <= 0:
        return False
    day_ret = _safe_div(c[l], c[l - 1], 1.0) - 1.0
    # 今日首次突破：收盘越过平台高 + 放量 + 涨幅>2%
    if not (c[l] > plat_hi * 1.01 and v[l] > vm10[l] * 1.8 and day_ret > 0.02):
        return False
    # 「首次」：近 10 日收盘未超过平台高
    prior_closes = c[l - win : l]
    if np.any(prior_closes > plat_hi * 1.005):
        return False
    return True


# ═══════════════════════════════════════════════════════════════
# 形态 4：趋势中继 N 形加速
# ═══════════════════════════════════════════════════════════════
def is_trend_resume(kl: pd.DataFrame, asof_idx: int | None = None) -> bool:
    """上升趋势中 → 缩量回调 3~5 日 → 今日再次放量上涨（N 字）。"""
    sub = _prep(kl, asof_idx)
    if sub is None or len(sub) < 125:
        return False
    s = _series(sub)
    c, v = s["c"], s["v"]
    l = len(c) - 1
    ma5 = _ma(c, 5)
    ma50 = _ma(c, 50)
    ma120 = _ma(c, 120)
    vm60 = _ma(v, 60)
    if any(np.isnan(x[l]) for x in (ma5, ma50, ma120, vm60)):
        return False
    if not (ma50[l] > ma120[l]):
        return False

    # 前期 20 日内涨幅 >10%
    ret20 = _safe_div(float(c[l - 5]), float(c[max(0, l - 25)]), 1.0) - 1.0
    if ret20 < 0.10:
        return False

    # 近 3~5 日回调 <5% 且缩量
    pull_n = 4
    peak = float(np.max(c[l - pull_n - 5 : l - pull_n + 1]))
    trough = float(np.min(c[l - pull_n : l]))
    pull_ret = _safe_div(trough, peak, 1.0) - 1.0
    if pull_ret < -0.05 or pull_ret > 0:
        # 允许小幅回撤 0~5%
        if not (-0.05 <= pull_ret <= 0.0):
            return False
    pull_vol = float(np.mean(v[l - pull_n : l]))
    if pull_vol > vm60[l] * 0.8:
        return False

    day_ret = _safe_div(c[l], c[l - 1], 1.0) - 1.0
    return bool(v[l] > vm60[l] * 1.15 and day_ret > 0.005 and c[l] > ma5[l])


def classify_launch_patterns(
    kl: pd.DataFrame,
    fund_hist: dict | None = None,
    asof_idx: int | None = None,
) -> list[str]:
    """返回命中的形态名列表（可多命中）。"""
    hits: list[str] = []
    try:
        if is_accumulation_breakout(kl, fund_hist=fund_hist, asof_idx=asof_idx):
            hits.append("accumulation_breakout")
    except Exception:
        pass
    try:
        if is_pullback_rebound(kl, asof_idx=asof_idx):
            hits.append("pullback_rebound")
    except Exception:
        pass
    try:
        if is_plateau_breakout(kl, asof_idx=asof_idx):
            hits.append("plateau_breakout")
    except Exception:
        pass
    try:
        if is_trend_resume(kl, asof_idx=asof_idx):
            hits.append("trend_resume")
    except Exception:
        pass
    return hits


def launch_pattern_asof(kl: pd.DataFrame, asof_idx: int, fund_hist: dict | None = None) -> bool:
    """回测用：asof 日是否命中任一启动形态。"""
    return bool(classify_launch_patterns(kl, fund_hist=fund_hist, asof_idx=asof_idx))


def _load_fund_hist_map() -> dict[str, dict]:
    if not FUND_HIST.exists():
        return {}
    try:
        raw = json.loads(FUND_HIST.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, dict] = {}
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        out[_bare(k)] = v if isinstance(v, dict) else {}
    return out


def _load_kline_groups() -> dict[str, pd.DataFrame] | None:
    if not KLINE_PARQUET.exists():
        return None
    try:
        df = pd.read_parquet(KLINE_PARQUET)
        df["date"] = pd.to_datetime(df["date"])
        df["symbol"] = df["symbol"].astype(str).map(_bare)
        groups = {
            sym: g.sort_values("date").reset_index(drop=True)
            for sym, g in df.groupby("symbol")
        }
        return groups
    except Exception as e:
        print(f"  ⚠️ kline parquet 加载失败: {e}", flush=True)
        return None


def scan_launch_patterns(
    symbols: list[str] | None = None,
    max_workers: int = 24,
    log=print,
) -> tuple[set[str], dict[str, list[str]]]:
    """全市场扫描四类启动形态。

    Returns:
      (code_set, {code: [pattern, ...]})
    兼容旧产物：调用方可把 code_set 写成 volume_gc_pool.json
    """
    log("▶ 全A股启动形态扫描（四类）...")
    fund_map = _load_fund_hist_map()
    groups = _load_kline_groups()

    if symbols is None:
        if groups is not None:
            symbols = sorted(groups.keys())
        else:
            from data_fetcher import get_stock_list

            stocks = get_stock_list()
            symbols = [_bare(s) for s in stocks["symbol"].tolist() if not str(s).startswith("bj")]

    symbols = [_bare(s) for s in symbols if s and not str(s).startswith(("bj", "8", "4"))]
    log(f"  全A股: {len(symbols)} 只 | 源={'parquet' if groups else 'sina_live'}")

    pattern_map: dict[str, list[str]] = {}
    hit_set: set[str] = set()

    def check(sym: str) -> tuple[str, list[str]] | None:
        try:
            if groups is not None:
                kl = groups.get(sym)
                if kl is None or kl.empty:
                    return None
            else:
                from data_fetcher import get_kline_sina
                from datetime import datetime, timedelta

                # 相对日期：取约 180 自然日，覆盖 MA120
                start = (datetime.now() - timedelta(days=220)).strftime("%Y%m%d")
                kl = get_kline_sina(sym, start_date=start)
                if kl is None or kl.empty:
                    return None
            hits = classify_launch_patterns(kl, fund_hist=fund_map.get(sym))
            if hits:
                return sym, hits
            return None
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(check, s): s for s in symbols}
        for i, fut in enumerate(as_completed(futs)):
            r = fut.result()
            if r:
                sym, hits = r
                hit_set.add(sym)
                pattern_map[sym] = hits
            if (i + 1) % 500 == 0:
                log(f"  扫描: {i+1}/{len(symbols)}, 已发现: {len(hit_set)}")

    OUT.mkdir(parents=True, exist_ok=True)
    # 兼容旧文件名 + 新明细
    (OUT / "volume_gc_pool.json").write_text(
        json.dumps(sorted(hit_set), ensure_ascii=False), encoding="utf-8"
    )
    detail = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "asof_logic": "最近已收盘交易日 → 预测下一交易日",
        "n_hit": len(hit_set),
        "n_scan": len(symbols),
        "by_pattern": {
            p: sum(1 for hs in pattern_map.values() if p in hs) for p in PATTERN_NAMES
        },
        "patterns": pattern_map,
    }
    (OUT / "launch_patterns_pool.json").write_text(
        json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(f"  ✅ 启动形态: {len(hit_set)} 只 {detail['by_pattern']}")
    return hit_set, pattern_map


# 兼容旧名
def scan_volume_gc() -> set[str]:
    hit, _ = scan_launch_patterns()
    return hit


if __name__ == "__main__":
    t0 = time.time()
    hits, pm = scan_launch_patterns()
    print(f"done n={len(hits)} elapsed={time.time()-t0:.1f}s")
    for sym, pats in list(pm.items())[:15]:
        print(f"  {sym}: {pats}")
