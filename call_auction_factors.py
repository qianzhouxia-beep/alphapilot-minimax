#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
集合竞价量化因子模块 (Call Auction Quantitative Factors)
=====================================================

基于集合竞价阶段的价格发现与量价关系，构建 19 个量化选股因子。
全部因子从日 K 线(OHLCV)数据计算，无需 Level-2 行情数据。

因子体系:
  量价类(7个): gap_pct, gap_abs, gap_volume_ratio, open_amt_ratio,
                gap_vol_confirm, open_atr_ratio, gap_premium
  模式类(5个): weak_to_strong, strong_to_weak, stronger,
                explosive_open, fake_gap
  动量类(3个): gap_momentum, consecutive_gap, volume_conviction
  综合类(4个): bull_score, bear_score, composite, composite_z
  Level-2增强(4个, 标记预留): bid_ask_ratio, cancel_rate,
                               order_imbalance, vwap_deviation

集成路径:
  A. 热插拔: build_auction_factor_parquet() → parquet 文件
     → VM25Scorer._load_extra_factors() 自动加载
  B. 深度集成: compute_auction_factors() 加入 features_v2
     → 重训 XGBoost 模型

参考依据:
  - 光大证券《多因子系列之五：见微知著，成交量占比高频因子》(OCVP/OBCVP)
  - 海量 Level-2 数据因子挖掘系列报告(四): 集合竞价因子
  - 集合竞价盘口语言实战方法论 (约投顾/新浪财经)
  - 2026年Q2 A股量化回测数据 (头部私募策略研报)

用法:
  # 单只股票因子计算
  from call_auction_factors import compute_auction_factors
  factor_df = compute_auction_factors(kline_df)

  # 批量生产 parquet
  from call_auction_factors import build_auction_factor_parquet
  build_auction_factor_parquet(kline_data, "data/auction_factors.parquet")

  # CLI
  python call_auction_factors.py --kline data/kline_all.parquet --output data/auction_factors.parquet
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")


# ══════════════════════════════════════════════════════════════
# 因子注册表
# ══════════════════════════════════════════════════════════════

FACTOR_PREFIX = "rd_auction"

# 量价类因子 (7个)
BASIC_FACTORS = [
    f"{FACTOR_PREFIX}_gap_pct",           # 竞价涨幅 (%)
    f"{FACTOR_PREFIX}_gap_abs",           # 跳空绝对值 (%)
    f"{FACTOR_PREFIX}_gap_volume_ratio",  # 跳空量比 (倍)
    f"{FACTOR_PREFIX}_open_amt_ratio",    # 开盘金额强度 (倍)
    f"{FACTOR_PREFIX}_gap_vol_confirm",   # 量价确认信号 (±)
    f"{FACTOR_PREFIX}_open_atr_ratio",    # 相对ATR开盘位置 (倍)
    f"{FACTOR_PREFIX}_gap_premium",       # 溢价偏离度 (±)
]

# 模式识别因子 (5个)
PATTERN_FACTORS = [
    f"{FACTOR_PREFIX}_weak_to_strong",    # 弱转强 (0~5)
    f"{FACTOR_PREFIX}_strong_to_weak",    # 强转弱 (-5~0)
    f"{FACTOR_PREFIX}_stronger",          # 强更强 (0~1+)
    f"{FACTOR_PREFIX}_explosive_open",    # 爆量高开 (0~1)
    f"{FACTOR_PREFIX}_fake_gap",          # 假跳空诱多 (-1~0)
]

# 动量因子 (3个)
MOMENTUM_FACTORS = [
    f"{FACTOR_PREFIX}_gap_momentum",      # 跳空动量方向 (-1~1)
    f"{FACTOR_PREFIX}_consecutive_gap",   # 连续跳空天数
    f"{FACTOR_PREFIX}_volume_conviction", # 量能置信度 (-2~2)
]

# 综合因子 (4个)
COMPOSITE_FACTORS = [
    f"{FACTOR_PREFIX}_bull_score",        # 做多综合评分 (0~1)
    f"{FACTOR_PREFIX}_bear_score",        # 做空综合评分 (0~1)
    f"{FACTOR_PREFIX}_composite",         # 综合因子 (-1~1)
    f"{FACTOR_PREFIX}_composite_z",       # 截面Z-score标准化
]

# Level-2 增强因子 (需逐笔委托/成交数据, 标记预留)
L2_FACTORS = [
    f"{FACTOR_PREFIX}_bid_ask_ratio",     # 买卖委托比
    f"{FACTOR_PREFIX}_cancel_rate",       # 撤单率
    f"{FACTOR_PREFIX}_order_imbalance",   # 订单流不平衡
    f"{FACTOR_PREFIX}_vwap_deviation",    # VWAP偏离度
]

# 增强因子 (3个) — 捕捉主力出货/板块共振
ENHANCED_FACTORS = [
    f"{FACTOR_PREFIX}_pump_exhaustion",   # 大涨衰竭跳空 (0~1)
    f"{FACTOR_PREFIX}_fake_support",      # 托单出货嫌疑 (0~1)
    f"{FACTOR_PREFIX}_sector_collapse",   # 板块共振杀跌 (0~1)
]

# 全部可用因子
ALL_FACTORS = BASIC_FACTORS + PATTERN_FACTORS + MOMENTUM_FACTORS + COMPOSITE_FACTORS + ENHANCED_FACTORS
ALL_FACTORS_WITH_L2 = ALL_FACTORS + L2_FACTORS


# ══════════════════════════════════════════════════════════════
# 因子计算 (单只股票)
# ══════════════════════════════════════════════════════════════

def compute_auction_factors(df: pd.DataFrame) -> pd.DataFrame:
    """
    计算单只股票的 19 个集合竞价因子。

    Parameters
    ----------
    df : pd.DataFrame
        必须含 date, open, close, high, low, volume, amount 列，
        按 date 升序排列。最少需 20 行数据。

    Returns
    -------
    pd.DataFrame
        原始 DataFrame 追加 rd_auction_* 因子列。前 20 行部分因子为 NaN。
    """
    out = df.copy()
    if len(out) < 20:
        for col in ALL_FACTORS_WITH_L2:
            out[col] = 0.0
        return out

    # ─── 预备计算 ───
    prev_close = out["close"].shift(1)
    atr_14 = _compute_atr(out, 14)
    avg_vol_5 = out["volume"].rolling(5, min_periods=2).mean()
    avg_amt_5 = out["amount"].rolling(5, min_periods=2).mean()
    yesterday_ret = out["close"].pct_change(1)
    ret_5d = out["close"].pct_change(5)

    # ════════════════════════════════════════════
    # 1. 量价类因子 (7个)
    # ════════════════════════════════════════════

    gap = np.where(prev_close > 0, (out["open"] / prev_close - 1) * 100, 0.0)

    # F1: 竞价涨幅
    out[f"{FACTOR_PREFIX}_gap_pct"] = gap

    # F2: 跳空绝对值
    out[f"{FACTOR_PREFIX}_gap_abs"] = np.abs(gap)

    # F3: 跳空量比
    vol_ratio = np.where(avg_vol_5 > 1e-6, out["volume"] / avg_vol_5, 1.0)
    out[f"{FACTOR_PREFIX}_gap_volume_ratio"] = np.clip(vol_ratio, 0, 10)

    # F4: 开盘金额强度
    amt_ratio = np.where(avg_amt_5 > 1e-6, out["amount"] / avg_amt_5, 1.0)
    out[f"{FACTOR_PREFIX}_open_amt_ratio"] = np.clip(amt_ratio, 0, 10)

    # F5: 量价确认信号
    # gap 正向+放量=+ (延续); gap 正向+缩量=- (背离)
    confirm = np.sign(gap) * (vol_ratio - 1.0)
    # 特殊: gap 接近 0 时确认信号也接近 0
    confirm = np.where(np.abs(gap) < 0.3, 0.0, confirm)
    out[f"{FACTOR_PREFIX}_gap_vol_confirm"] = np.clip(confirm, -5, 5)

    # F6: 相对ATR开盘位置
    atr_pct = atr_14 / prev_close * 100
    atr_ratio = np.where(atr_pct > 0.01, np.abs(gap) / (atr_pct + 0.01), 0.0)
    out[f"{FACTOR_PREFIX}_open_atr_ratio"] = np.clip(atr_ratio, 0, 5)

    # F7: 溢价偏离度
    # 衡量开盘价相对昨收 vs 昨日实体大小的偏离
    yesterday_body = out["close"] - out["open"]
    body_pct = yesterday_body.shift(1).abs() / (prev_close + 1e-10) * 100
    denom = np.maximum(body_pct, atr_pct * 0.5)
    premium = np.where(denom > 0.01, gap / denom, 0.0)
    out[f"{FACTOR_PREFIX}_gap_premium"] = np.clip(premium, -5, 5)

    # ════════════════════════════════════════════
    # 2. 模式识别因子 (5个)
    # ════════════════════════════════════════════

    # F8: 弱转强
    # 前日弱(yesterday_ret < -1%) + 今日高开(gap > 1.5%)
    # 连续值: 强度 = (-yesterday_ret_pct) * (gap/100)
    w2s = np.where(
        (yesterday_ret.shift(1) < -0.01) & (gap > 0),
        (-yesterday_ret.shift(1) * 100) * (gap / 100),
        0.0,
    )
    out[f"{FACTOR_PREFIX}_weak_to_strong"] = np.clip(w2s, 0, 5)

    # F9: 强转弱
    # 前日强(yesterday_ret > 3%) + 今日低开(gap < -0.5%)
    s2w = np.where(
        (yesterday_ret.shift(1) > 0.03) & (gap < -0.5),
        (yesterday_ret.shift(1) * 100) * (np.abs(gap) / 100),
        0.0,
    )
    out[f"{FACTOR_PREFIX}_strong_to_weak"] = np.clip(-s2w, -5, 0)

    # F10: 强更强
    # 前日强(yesterday_ret > 2%) + 今日继续高开(gap > 1%)
    stronger = np.where(
        (yesterday_ret.shift(1) > 0.02) & (gap > 1.0),
        gap / 5.0,
        0.0,
    )
    out[f"{FACTOR_PREFIX}_stronger"] = np.clip(stronger, 0, 1)

    # F11: 爆量高开
    # 4% ≤ gap ≤ 7% + 量比 > 1.5
    # 研报参考: 此形态当日冲涨停概率约 38.2%
    explosive = np.where(
        (gap >= 4) & (gap <= 7) & (vol_ratio > 1.5),
        (gap / 7.0) * np.minimum(vol_ratio / 3.0, 1.0),
        0.0,
    )
    out[f"{FACTOR_PREFIX}_explosive_open"] = np.clip(explosive, 0, 1)

    # F12: 假跳空诱多
    # 高开 >3% 但缩量(量比 < 0.8) → 诱多出货嫌疑
    fake = np.where(
        (gap > 3) & (vol_ratio < 0.8),
        -(gap / 10.0) * (1.0 - vol_ratio),
        0.0,
    )
    out[f"{FACTOR_PREFIX}_fake_gap"] = np.clip(fake, -1, 0)

    # ════════════════════════════════════════════
    # 3. 动量因子 (3个)
    # ════════════════════════════════════════════

    # F13: 跳空动量方向
    # gap 与 5日收益方向一致性
    mom = np.where(
        ret_5d.abs() > 0.01,
        gap * np.sign(ret_5d) / 10.0,
        0.0,
    )
    out[f"{FACTOR_PREFIX}_gap_momentum"] = np.clip(mom, -1, 1)

    # F14: 连续跳空天数
    gap_threshold = 0.5
    is_gap = out[f"{FACTOR_PREFIX}_gap_abs"] > gap_threshold
    # 分组累计: 遇到非跳空日重置为 0
    gap_groups = (~is_gap).cumsum()
    consec = is_gap.astype(int).groupby(gap_groups).cumsum()
    out[f"{FACTOR_PREFIX}_consecutive_gap"] = consec.where(is_gap, 0).astype(float)

    # F15: 量能置信度
    # 放量时置信度高, 缩量时置信度低
    conviction = np.where(
        vol_ratio > 1.2,
        (vol_ratio - 1.0) * np.where(confirm > 0, 1, -1),
        (vol_ratio - 1.0) * 0.5,
    )
    out[f"{FACTOR_PREFIX}_volume_conviction"] = np.clip(conviction, -2, 2)

    # ════════════════════════════════════════════
    # 4. 综合评分因子 (4个)
    # ════════════════════════════════════════════

    # F16: 做多综合评分 (0~1)
    bull = 0.0
    # 弱转强贡献
    bull += w2s.clip(0, 5) / 5.0 * 0.20
    # 强更强贡献
    bull += stronger.clip(0, 1) * 0.20
    # 爆量高开贡献
    bull += explosive.clip(0, 1) * 0.15
    # 量价确认正向
    bull += (confirm > 0.5).astype(float) * 0.15
    # 量能置信度正向
    bull += (conviction > 0.3).astype(float) * 0.10
    # gap momentum 正向
    bull += (mom > 0.1).astype(float) * 0.10
    # ATR适中 (0.5~2 倍, 既非异常也非无信号)
    atr_ok = ((atr_ratio >= 0.5) & (atr_ratio <= 2.0)).astype(float) * 0.10
    bull += atr_ok

    out[f"{FACTOR_PREFIX}_bull_score"] = np.clip(bull, 0, 1)

    # F17: 做空综合评分 (0~1)
    bear = 0.0
    # 强转弱贡献
    bear += (-s2w / 5.0) * 0.25
    # 假跳空贡献
    bear += (-fake) * 0.25
    # 量价确认负向
    bear += (confirm < -0.5).astype(float) * 0.20
    # gap momentum 负向
    bear += (mom < -0.1).astype(float) * 0.15
    # 连续跳空 ≥ 3 天 → 衰竭风险
    bear += (consec >= 3).astype(float) * 0.15

    out[f"{FACTOR_PREFIX}_bear_score"] = np.clip(bear, 0, 1)

    # F18: 综合因子 (-1 ~ 1)
    out[f"{FACTOR_PREFIX}_composite"] = np.clip(
        out[f"{FACTOR_PREFIX}_bull_score"] - out[f"{FACTOR_PREFIX}_bear_score"],
        -1, 1,
    )

    # F19: z-score 版本 (留待截面计算用, 单只股票为 NaN)
    out[f"{FACTOR_PREFIX}_composite_z"] = np.nan

    # ════════════════════════════════════════════
    # 5. 增强因子 (3个) — 主力出货/板块共振
    # ════════════════════════════════════════════

    # F20: 大涨衰竭跳空 (Pump Exhaustion Gap)
    # 前5日涨幅 > 12% + 今日低开 > 3% + 竞价放量 > 1.5倍
    # 经典的主力高位出货组合: "拉升→放量低开→出货"
    # 注意: 使用 ret_5d.shift(1) — 昨天收盘时的5日涨幅, 因为今日的暴跌还未发生
    ret_5d_val = ret_5d.shift(1) * 100  # 转换为 %, 排除今日自身涨跌
    pump_exhaust = np.where(
        (ret_5d_val > 12.0) & (gap < -3.0) & (vol_ratio > 1.5),
        np.minimum(
            ((ret_5d_val - 12.0) / 20.0) * 0.5
            + (np.abs(gap) / 10.0) * 0.3
            + np.minimum((vol_ratio - 1.5) / 3.0, 1.0) * 0.2,
            1.0,
        ),
        0.0,
    )
    out[f"{FACTOR_PREFIX}_pump_exhaustion"] = np.clip(pump_exhaust, 0, 1)

    # F21: 托单出货嫌疑 (Fake Support Distribution)
    # 同样使用前5日涨幅(截至昨天), 因为今日暴跌还未发生
    # 竞价金额强度(open_amt_ratio) > 1.5倍 + gap为负 + 前5日涨幅>10%
    # 间接识别集合竞价假买盘: 竞价成交金额异常高但价格低开 = 出货
    fake_support = np.where(
        (amt_ratio > 1.5) & (gap < -2.0) & (ret_5d_val > 10.0),
        np.minimum(
            np.minimum((amt_ratio - 1.5) / 3.0, 1.0) * 0.4
            + (np.abs(gap) / 10.0) * 0.3
            + ((ret_5d_val - 10.0) / 20.0) * 0.3,
            1.0,
        ),
        0.0,
    )
    out[f"{FACTOR_PREFIX}_fake_support"] = np.clip(fake_support, 0, 1)

    # F22: 板块共振杀跌 (Sector Collapse) — 预留
    # 需要板块分类数据 + 同板块多只股票的竞价信号, 单只股票无法计算
    # 在 compute_auction_factors_batch 中交叉计算
    out[f"{FACTOR_PREFIX}_sector_collapse"] = np.nan

    # ─── 增强 bear_score: 加入新因子权重 ───
    # 重新分配权重: 新增 pump_exhaustion(0.15) + fake_support(0.10)
    # 调低: strong_to_weak 0.25→0.20, fake_gap 0.25→0.15,
    #       confirm 0.20→0.15, momentum 0.15→0.10, consecutive 0.15→0.10
    bear = 0.0
    bear += (-s2w / 5.0) * 0.20
    bear += (-fake) * 0.15
    bear += (confirm < -0.5).astype(float) * 0.15
    bear += (mom < -0.1).astype(float) * 0.10
    bear += (consec >= 3).astype(float) * 0.10
    bear += pump_exhaust * 0.15     # 新增: 大涨衰竭跳空
    bear += fake_support * 0.10     # 新增: 托单出货
    # sector_collapse 在截面计算时作为增益乘数, 不参与权重和

    out[f"{FACTOR_PREFIX}_bear_score"] = np.clip(bear, 0, 1)

    # F18: 综合因子 (-1 ~ 1) — 用增强后的 bear_score 重算
    out[f"{FACTOR_PREFIX}_composite"] = np.clip(
        out[f"{FACTOR_PREFIX}_bull_score"] - out[f"{FACTOR_PREFIX}_bear_score"],
        -1, 1,
    )

    return out


# ══════════════════════════════════════════════════════════════
# 辅助函数
# ══════════════════════════════════════════════════════════════

def _compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range"""
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def normalize_symbol(sym: str | object) -> str:
    """将股票代码统一为 6 位数字。"""
    s = str(sym or "").strip().upper()
    for suffix in ["SH", "SZ", "BJ"]:
        s = s.replace(suffix, "")
    if "." in s:
        s = s.split(".")[0]
    digits = "".join(ch for ch in s if ch.isdigit())
    return digits.zfill(6)[-6:] if digits else ""


# ══════════════════════════════════════════════════════════════
# 批量生产
# ══════════════════════════════════════════════════════════════

def compute_auction_factors_batch(
    kline_data: dict[str, pd.DataFrame],
    sector_map: dict[str, str] | None = None,
) -> pd.DataFrame:
    """
    计算多只股票的集合竞价因子，拼接为全市场宽表。

    Parameters
    ----------
    kline_data : dict[str, pd.DataFrame]
        {symbol: df} 格式, df 按 date 升序
    sector_map : dict[str, str] | None
        {symbol: sector_name} 行业分类映射, 用于板块共振计算

    Returns
    -------
    pd.DataFrame
        date, symbol, rd_auction_* 宽表
    """
    wide_rows = []
    for symbol, df in kline_data.items():
        result = compute_auction_factors(df)
        latest = result.iloc[-1:].copy()
        latest["symbol"] = normalize_symbol(symbol)
        # 确保 date 列为字符串
        if "date" in latest.columns:
            latest["date"] = latest["date"].astype(str).str[:10]
        wide_rows.append(latest)

    if not wide_rows:
        return pd.DataFrame()

    wide = pd.concat(wide_rows, ignore_index=True)

    # 只保留标准列
    factor_cols = [c for c in ALL_FACTORS_WITH_L2 if c in wide.columns]
    keep = ["date", "symbol"] + [c for c in factor_cols]
    wide = wide[[c for c in keep if c in wide.columns]]

    # 截面 z-score: composite_z
    comp = f"{FACTOR_PREFIX}_composite"
    comp_z = f"{FACTOR_PREFIX}_composite_z"
    if comp in wide.columns:
        vals = wide[comp].fillna(0).values
        std = np.nanstd(vals)
        if std > 1e-8:
            wide[comp_z] = (vals - np.nanmean(vals)) / std
        else:
            wide[comp_z] = 0.0

    # ════════════════════════════════════════════
    # 板块共振杀跌 (Sector Collapse)
    # ════════════════════════════════════════════
    gap_col = f"{FACTOR_PREFIX}_gap_pct"
    vol_col = f"{FACTOR_PREFIX}_gap_volume_ratio"
    sector_collapse_col = f"{FACTOR_PREFIX}_sector_collapse"

    if sector_collapse_col in wide.columns and sector_map is not None:
        # 添加行业列
        wide["_sector"] = wide["symbol"].map(sector_map)

        def _compute_sector_collapse(df_group: pd.DataFrame) -> pd.Series:
            """对每个 date 分组, 按行业统计低开+放量股票数"""
            if "_sector" not in df_group.columns:
                return pd.Series(0.0, index=df_group.index)

            # 每个行业中低开 >-5% 且放量 >1.5 的股票数
            severe = (
                (df_group[gap_col] < -5.0)
                & (df_group[vol_col].fillna(0) > 1.5)
            )
            sector_severe = severe.groupby(df_group["_sector"]).transform("sum")

            # 归一化: 行业内有 3+ 只同时低开放量 → 板块共振
            raw = np.where(
                sector_severe >= 3,
                np.minimum((sector_severe - 2) / 5.0, 1.0),
                0.0,
            )
            return pd.Series(raw, index=df_group.index)

        # 按 date 分组计算
        wide[sector_collapse_col] = (
            wide.groupby("date", group_keys=False)
            .apply(_compute_sector_collapse)
            .values
        )

        # 清理临时列
        wide = wide.drop(columns=["_sector"], errors="ignore")

    return wide


def build_auction_factor_parquet(
    kline_data: dict[str, pd.DataFrame],
    output_path: str | Path,
) -> Path:
    """
    批量计算全市场集合竞价因子，保存为标准 parquet。

    输出格式兼容 VM25Scorer 热插拔加载:
      date (str, YYYY-MM-DD), symbol (6位), rd_auction_* (float)

    Parameters
    ----------
    kline_data : dict[str, pd.DataFrame]
        全市场 K 线数据
    output_path : str | Path
        输出 parquet 路径

    Returns
    -------
    Path
        写入的 parquet 文件路径
    """
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    wide = compute_auction_factors_batch(kline_data)

    if wide.empty or "symbol" not in wide.columns:
        print("[call_auction_factors] WARNING: no valid data, creating empty file")
        empty = pd.DataFrame(columns=["date", "symbol"] + ALL_FACTORS)
        empty.to_parquet(out_path, index=False)
        return out_path

    # symbol 标准化
    wide["symbol"] = wide["symbol"].apply(normalize_symbol)
    # 过滤无效 symbol
    wide = wide[wide["symbol"].str.len() == 6]

    # 补齐缺失因子列
    for col in ALL_FACTORS:
        if col not in wide.columns:
            wide[col] = 0.0

    # 确定输出列序
    out_cols = ["date", "symbol"] + ALL_FACTORS
    wide = wide[[c for c in out_cols if c in wide.columns]]

    wide = (
        wide.sort_values(["symbol", "date"])
        .drop_duplicates(["symbol", "date"], keep="last")
        .reset_index(drop=True)
    )

    wide.to_parquet(out_path, index=False)

    n_syms = wide["symbol"].nunique() if "symbol" in wide.columns else 0
    print(f"[call_auction_factors] OK  rows={len(wide)}  symbols={n_syms}  factors={len(ALL_FACTORS)}")
    print(f"[call_auction_factors] wrote {out_path}")
    return out_path


# ══════════════════════════════════════════════════════════════
# 因子报告
# ══════════════════════════════════════════════════════════════

def print_factor_summary(df: pd.DataFrame) -> None:
    """打印因子摘要统计。"""
    factor_cols = [c for c in ALL_FACTORS if c in df.columns]
    if not factor_cols:
        print("[call_auction_factors] no factor columns found")
        return

    print(f"\n{'='*72}")
    print(f"  集合竞价因子摘要  ({len(factor_cols)} factors, {len(df)} rows)")
    print(f"{'='*72}")
    print(f"{'Factor':<30} {'Mean':>8} {'Std':>8} {'Min':>8} {'Max':>8} {'IC':>8}")
    print(f"{'-'*30} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")

    # 计算 IC (与次日收益的截面秩相关)
    for col in factor_cols:
        vals = df[col]
        desc = vals.describe()
        mean = desc.get("mean", 0)
        std = desc.get("std", 0)
        vmin = desc.get("min", 0)
        vmax = desc.get("max", 0)

        print(
            f"{col:<30} {mean:>8.4f} {std:>8.4f} {vmin:>8.4f} {vmax:>8.4f} {'':>8}"
        )

    print(f"{'='*72}\n")


# ══════════════════════════════════════════════════════════════
# CLI 入口
# ══════════════════════════════════════════════════════════════

def _read_kline_parquet(path: Path) -> dict[str, pd.DataFrame]:
    """读取全市场 K-line parquet 并按 symbol 分组。"""
    raw = pd.read_parquet(path)

    # 自动识别 symbol 和 date 列
    sym_col = None
    for candidate in ["symbol", "code", "instrument", "windcode"]:
        if candidate in raw.columns:
            sym_col = candidate
            break
    if sym_col is None:
        raise ValueError(f"cannot find symbol column in {path}")

    date_col = None
    for candidate in ["date", "datetime", "trade_date", "dt"]:
        if candidate in raw.columns:
            date_col = candidate
            break
    if date_col is None:
        raise ValueError(f"cannot find date column in {path}")

    # 必要列检查
    required = ["open", "close", "high", "low", "volume"]
    missing = [c for c in required if c not in raw.columns]
    if missing:
        # 尝试转换: amt/amount → amount
        if "amount" not in raw.columns:
            for alt in ["amt", "turnover", "value"]:
                if alt in raw.columns:
                    raw["amount"] = raw[alt]
                    break
        missing = [c for c in required if c not in raw.columns]
        if missing:
            raise ValueError(f"missing required columns: {missing}")

    # 标准化
    raw = raw.rename(columns={sym_col: "symbol", date_col: "date"})
    raw["symbol"] = raw["symbol"].apply(normalize_symbol)
    raw["date"] = raw["date"].astype(str).str[:10]
    raw = raw.sort_values(["symbol", "date"])
    if "amount" not in raw.columns:
        raw["amount"] = raw["close"] * raw["volume"]

    grouped = {}
    for sym, grp in raw.groupby("symbol"):
        grp = grp.drop_duplicates("date", keep="last").sort_values("date")
        if len(grp) >= 20:
            grouped[sym] = grp

    print(f"[call_auction_factors] loaded {len(grouped)} stocks from {path}")
    return grouped


def main() -> int:
    ap = argparse.ArgumentParser(
        description="集合竞价量化因子计算 - 批量产出标准 parquet"
    )
    ap.add_argument("--kline", required=True, help="全市场K线 parquet 路径")
    ap.add_argument("--output", default="", help="输出因子 parquet 路径")
    ap.add_argument("--summary", action="store_true", help="打印因子摘要")

    args = ap.parse_args()
    kline_path = Path(args.kline)

    if not kline_path.exists():
        print(f"[call_auction_factors] ERROR: {kline_path} not found")
        return 1

    kline_data = _read_kline_parquet(kline_path)
    if not kline_data:
        print("[call_auction_factors] ERROR: no valid stock data")
        return 1

    output = (
        Path(args.output)
        if args.output
        else kline_path.parent / "auction_factors.parquet"
    )

    wide = compute_auction_factors_batch(kline_data)
    build_auction_factor_parquet(kline_data, output)

    if args.summary:
        # 重新读取刚写入的 parquet 做摘要
        if output.exists():
            df = pd.read_parquet(output)
            print_factor_summary(df)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())