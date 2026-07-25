#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
集合竞价因子测试脚本
====================
模拟集合竞价开盘数据，验证因子计算的正确性。

用法:
  python scripts/test_auction_factors.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
from call_auction_factors import (
    compute_auction_factors,
    compute_auction_factors_batch,
    build_auction_factor_parquet,
    ALL_FACTORS,
    FACTOR_PREFIX,
)


def make_synthetic_kline(n_days: int = 60) -> pd.DataFrame:
    """生成模拟 K 线数据"""
    np.random.seed(42)
    dates = pd.date_range("2026-06-01", periods=n_days, freq="B")
    base = 50.0 * (1 + np.linspace(0, 0.1, n_days))
    noise = np.random.randn(n_days) * 0.5
    close = base + noise
    open_prices = close.copy()
    for i in range(1, n_days):
        gap_signal = np.random.randn() * 0.8
        open_prices[i] = close[i-1] * (1 + gap_signal / 100)
    high = np.maximum(open_prices, close) * (1 + np.abs(np.random.randn(n_days)) * 0.005)
    low = np.minimum(open_prices, close) * (1 - np.abs(np.random.randn(n_days)) * 0.005)
    volume = (50 + np.random.rand(n_days) * 100) * 10000
    amount = volume * (open_prices + close) / 2

    df = pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "open": open_prices,
        "close": close,
        "high": high,
        "low": low,
        "volume": volume,
        "amount": amount,
    })
    return df


def make_scenario_case(scenario: str) -> pd.DataFrame:
    """
    构造特定场景的 K 线数据用于验证。
    pad_days=20 的前导平稳数据 + 5 天场景数据。

    Scenarios:
    - weak_to_strong: 前日大跌 → 今日大幅高开放量
    - strong_to_weak: 前日大涨 → 今日大幅低开缩量
    - explosive_open: 前日平淡 → 今日 5% 高开 + 巨量
    - fake_gap:       前日平淡 → 今日 4% 高开但极度缩量
    """
    base = 50.0
    pad_days = 20
    total_days = pad_days + 5
    dates = pd.date_range("2026-06-01", periods=total_days, freq="B")

    np.random.seed(scenario.__hash__() % (2**31))
    close_pad = base * (1 + np.cumsum(np.random.randn(pad_days) * 0.002))
    open_pad = close_pad * (1 + np.random.randn(pad_days) * 0.0015)
    high_pad = np.maximum(close_pad, open_pad) * (1 + np.abs(np.random.randn(pad_days)) * 0.003)
    low_pad = np.minimum(close_pad, open_pad) * (1 - np.abs(np.random.randn(pad_days)) * 0.003)
    vol_pad = 5000000 + np.random.randint(-500000, 500000, pad_days)

    last_base = close_pad[-1]

    if scenario == "weak_to_strong":
        closes = [last_base, last_base * 0.995, last_base * 0.998, last_base * 0.96, last_base * 0.99]
        opens = closes[:]
        opens[4] = closes[3] * 1.035
        volumes = [5000000] * 4 + [10000000]

    elif scenario == "strong_to_weak":
        closes = [last_base, last_base * 1.002, last_base * 0.998, last_base * 1.05, last_base * 1.03]
        opens = closes[:]
        opens[4] = closes[3] * 0.98
        volumes = [5000000] * 3 + [8000000] + [3000000]

    elif scenario == "explosive_open":
        closes = [last_base, last_base, last_base, last_base * 1.015, last_base * 1.01]
        opens = closes[:]
        opens[4] = closes[3] * 1.05
        volumes = [5000000] * 4 + [15000000]

    elif scenario == "fake_gap":
        closes = [last_base] * 5
        opens = closes[:]
        opens[4] = closes[3] * 1.04
        volumes = [5000000] * 4 + [2000000]

    else:
        raise ValueError(f"unknown scenario: {scenario}")

    high = [max(o, c) * 1.005 for o, c in zip(opens, closes)]
    low = [min(o, c) * 0.995 for o, c in zip(opens, closes)]

    all_close = list(close_pad) + closes
    all_open = list(open_pad) + opens
    all_high = list(high_pad) + high
    all_low = list(low_pad) + low
    all_vol = list(vol_pad) + volumes
    all_amt = [o * v for o, v in zip(all_open, all_vol)]

    df = pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "open": all_open,
        "close": all_close,
        "high": all_high,
        "low": all_low,
        "volume": all_vol,
        "amount": all_amt,
    })
    return df


# ─── 测试用例 ───

def test_basic_computation():
    """基础计算测试"""
    print("=" * 60)
    print("测试 1: 基础因子计算 (合成 60 日 K 线)")
    print("=" * 60)
    df = make_synthetic_kline(60)
    result = compute_auction_factors(df)
    assert result is not None, "计算返回 None"
    for col in ALL_FACTORS:
        assert col in result.columns, f"缺少因子列: {col}"
    latest = result.iloc[-1]
    for col in ALL_FACTORS:
        val = latest[col]
        assert not np.isnan(val) or col.endswith("composite_z"), f"{col} = {val}"
    n_found = sum(1 for c in ALL_FACTORS if result.iloc[-2][c] != 0.0)
    print(f"  OK: {n_found}/{len(ALL_FACTORS)} 因子在倒数第2行有非零值")
    print(f"  OK: 所有 {len(ALL_FACTORS)} 因子列均存在")


def test_scenario_weak_to_strong():
    """弱转强场景"""
    print("\n" + "=" * 60)
    print("测试 2: 弱转强场景")
    print("=" * 60)
    df = make_scenario_case("weak_to_strong")
    result = compute_auction_factors(df)
    latest = result.iloc[-1]
    gap = latest[f"{FACTOR_PREFIX}_gap_pct"]
    w2s = latest[f"{FACTOR_PREFIX}_weak_to_strong"]
    bull = latest[f"{FACTOR_PREFIX}_bull_score"]
    comp = latest[f"{FACTOR_PREFIX}_composite"]
    print(f"  gap_pct = {gap:.2f}%")
    print(f"  weak_to_strong = {w2s:.4f}  (期望 > 0)")
    print(f"  bull_score = {bull:.4f}  (期望 > 0)")
    print(f"  composite  = {comp:.4f}  (期望 > 0)")
    assert gap > 2.5, f"gap_pct({gap}) 应 > 2.5% (弱转强应高开)"
    assert w2s > 0, f"weak_to_strong({w2s}) 应 > 0"
    assert bull > 0, f"bull_score({bull}) 应 > 0"
    assert comp > 0, f"composite({comp}) 应 > 0"


def test_scenario_strong_to_weak():
    """强转弱场景"""
    print("\n" + "=" * 60)
    print("测试 3: 强转弱场景")
    print("=" * 60)
    df = make_scenario_case("strong_to_weak")
    result = compute_auction_factors(df)
    latest = result.iloc[-1]
    gap = latest[f"{FACTOR_PREFIX}_gap_pct"]
    s2w = latest[f"{FACTOR_PREFIX}_strong_to_weak"]
    bear = latest[f"{FACTOR_PREFIX}_bear_score"]
    comp = latest[f"{FACTOR_PREFIX}_composite"]
    print(f"  gap_pct = {gap:.2f}%")
    print(f"  strong_to_weak = {s2w:.4f}  (期望 < 0)")
    print(f"  bear_score = {bear:.4f}  (期望 > 0)")
    print(f"  composite  = {comp:.4f}  (期望 < 0)")
    assert gap < 0, f"gap_pct({gap}) 应 < 0 (强转弱应低开)"
    assert s2w < 0, f"strong_to_weak({s2w}) 应 < 0"
    assert bear > 0, f"bear_score({bear}) 应 > 0"
    assert comp < 0, f"composite({comp}) 应 < 0"


def test_scenario_explosive_open():
    """爆量高开场景"""
    print("\n" + "=" * 60)
    print("测试 4: 爆量高开场景")
    print("=" * 60)
    df = make_scenario_case("explosive_open")
    result = compute_auction_factors(df)
    latest = result.iloc[-1]
    gap = latest[f"{FACTOR_PREFIX}_gap_pct"]
    explosive = latest[f"{FACTOR_PREFIX}_explosive_open"]
    confirm = latest[f"{FACTOR_PREFIX}_gap_vol_confirm"]
    print(f"  gap_pct = {gap:.2f}%  (5% 高开)")
    print(f"  explosive_open = {explosive:.4f}  (期望 > 0)")
    print(f"  gap_vol_confirm = {confirm:.4f}  (期望 > 0)")
    assert 4 <= gap <= 7, f"gap_pct({gap}) 应在 4%~7% 之间"
    assert explosive > 0, f"explosive_open({explosive}) 应 > 0"
    assert confirm > 0, f"gap_vol_confirm({confirm}) 应 > 0"


def test_scenario_fake_gap():
    """假跳空诱多场景"""
    print("\n" + "=" * 60)
    print("测试 5: 假跳空诱多场景")
    print("=" * 60)
    df = make_scenario_case("fake_gap")
    result = compute_auction_factors(df)
    latest = result.iloc[-1]
    gap = latest[f"{FACTOR_PREFIX}_gap_pct"]
    fake = latest[f"{FACTOR_PREFIX}_fake_gap"]
    confirm = latest[f"{FACTOR_PREFIX}_gap_vol_confirm"]
    bear = latest[f"{FACTOR_PREFIX}_bear_score"]
    print(f"  gap_pct = {gap:.2f}%  (4% 高开但缩量)")
    print(f"  fake_gap = {fake:.4f}  (期望 < 0)")
    print(f"  gap_vol_confirm = {confirm:.4f}  (期望 < 0)")
    print(f"  bear_score = {bear:.4f}  (期望 > 0)")
    assert fake < 0, f"fake_gap({fake}) 应 < 0"
    assert confirm < 0, f"gap_vol_confirm({confirm}) 应 < 0"
    assert bear > 0, f"bear_score({bear}) 应 > 0"


def test_batch_computation():
    """批量计算测试"""
    print("\n" + "=" * 60)
    print("测试 6: 批量计算 + 截面标准化")
    print("=" * 60)
    kline_data = {
        "000001": make_scenario_case("weak_to_strong"),
        "000002": make_scenario_case("strong_to_weak"),
        "000003": make_scenario_case("explosive_open"),
        "000004": make_scenario_case("fake_gap"),
        "000005": make_synthetic_kline(60),
    }
    wide = compute_auction_factors_batch(kline_data)
    assert len(wide) == len(kline_data), f"行数不对: {len(wide)} vs {len(kline_data)}"
    assert f"{FACTOR_PREFIX}_composite_z" in wide.columns, "缺少 composite_z 列"
    z_col = f"{FACTOR_PREFIX}_composite_z"
    z_vals = wide[z_col].dropna()
    assert abs(z_vals.mean()) < 0.01, f"z-score 均值应 ≈ 0, 实际 {z_vals.mean():.4f}"
    assert abs(z_vals.std() - 1.0) < 0.15, f"z-score 标准差应 ≈ 1, 实际 {z_vals.std():.4f}"
    print(f"  OK: {len(wide)} 行数据")
    print(f"  OK: {len([c for c in wide.columns if c.startswith(FACTOR_PREFIX)])} 因子列")
    print(f"  OK: composite_z 均值 = {z_vals.mean():.4f}, 标准差 = {z_vals.std():.4f}")


def test_parquet_output():
    """Parquet 输出测试"""
    print("\n" + "=" * 60)
    print("测试 7: Parquet 标准输出")
    print("=" * 60)
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        kline_data = {
            "000001.SZ": make_scenario_case("weak_to_strong"),
            "000002.SZ": make_scenario_case("explosive_open"),
            "000005": make_synthetic_kline(60),
        }
        out = Path(tmp) / "auction_factors.parquet"
        build_auction_factor_parquet(kline_data, out)
        assert out.exists(), "parquet 文件未创建"
        df = pd.read_parquet(out)
        assert "symbol" in df.columns, "缺少 symbol 列"
        assert "date" in df.columns, "缺少 date 列"
        rd_cols = [c for c in df.columns if c.startswith("rd_")]
        assert len(rd_cols) > 0, f"没有 rd_ 前缀的因子列"
        print(f"  OK: {out}")
        print(f"  OK: {len(rd_cols)} 个 rd_auction_* 因子列")


if __name__ == "__main__":
    test_basic_computation()
    test_scenario_weak_to_strong()
    test_scenario_strong_to_weak()
    test_scenario_explosive_open()
    test_scenario_fake_gap()
    test_batch_computation()
    test_parquet_output()

    print("\n" + "=" * 60)
    print("所有测试通过!")
    print("=" * 60)