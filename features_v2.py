"""
AlphaPilot V11 特征工程 v2 — 50维特征
扩充自 V10 的 31 维，新增经典技术指标、成交量/波动率结构、交互特征
删除冗余的 score_* 评分特征
"""
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")


def compute_technical_features(df: pd.DataFrame) -> pd.DataFrame:
    """基础技术面特征（保留 V10 已验证的 8 维核心）"""
    df = df.sort_values("date").copy()
    df["ret_5d"] = df["close"].pct_change(5)
    df["ret_20d"] = df["close"].pct_change(20)
    df["amount_ratio_5"] = df["amount"] / df["amount"].rolling(5, min_periods=1).mean()
    df["amount_ratio_20"] = df["amount"] / df["amount"].rolling(20, min_periods=1).mean()
    df["vol_20d"] = df["ret_20d"].rolling(20).std()
    df["vol_spike"] = ((df["amount_ratio_5"] > 1.5) & (df["ret_5d"] < 0.02)).astype(float)
    mf_multiplier = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / (df["high"] - df["low"] + 1e-10)
    mf_volume = mf_multiplier * df["volume"]
    df["cmf_20"] = mf_volume.rolling(20).sum() / df["volume"].rolling(20).sum()
    vpt = (df["volume"] * df["close"].pct_change()).fillna(0).cumsum()
    df["vpt_20"] = vpt - vpt.shift(20)
    return df


def compute_ta_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """经典技术指标 — 新增 12 维"""
    df = df.copy()
    
    # RSI (14日)
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(14, min_periods=14).mean()
    avg_loss = loss.rolling(14, min_periods=14).mean()
    rs = avg_gain / (avg_loss + 1e-10)
    df["rsi_14"] = 100 - (100 / (1 + rs))
    
    # MACD (12, 26, 9)
    ema_12 = df["close"].ewm(span=12, adjust=False).mean()
    ema_26 = df["close"].ewm(span=26, adjust=False).mean()
    df["macd"] = ema_12 - ema_26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]
    
    # 布林带 (20日, 2倍标准差)
    bb_mid = df["close"].rolling(20).mean()
    bb_std = df["close"].rolling(20).std()
    df["bb_upper"] = bb_mid + 2 * bb_std
    df["bb_lower"] = bb_mid - 2 * bb_std
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / (bb_mid + 1e-10)
    
    # 均线
    df["sma_5"] = df["close"].rolling(5).mean()
    df["sma_20"] = df["close"].rolling(20).mean()
    df["sma_60"] = df["close"].rolling(60).mean()
    df["ma_dist_pct"] = (df["close"] - df["sma_20"]) / (df["sma_20"] + 1e-10)
    
    # ATR (14日)
    tr = pd.concat([
        df["high"] - df["low"],
        abs(df["high"] - df["close"].shift(1)),
        abs(df["low"] - df["close"].shift(1)),
    ], axis=1).max(axis=1)
    df["atr_14"] = tr.rolling(14).mean()
    df["atr_pct"] = df["atr_14"] / (df["close"] + 1e-10)
    
    return df


def compute_volume_features(df: pd.DataFrame) -> pd.DataFrame:
    """成交量/换手率结构 — 新增 5 维"""
    df = df.copy()
    
    # 换手率（如果数据中有）
    if "turnover" in df.columns:
        df["turnover"] = df["turnover"].fillna(0)
        df["turnover_ma_20"] = df["turnover"].rolling(20).mean()
        df["turnover_ratio"] = df["turnover"] / (df["turnover_ma_20"] + 1e-10)
    else:
        df["turnover"] = 0.0
        df["turnover_ma_20"] = 0.0
        df["turnover_ratio"] = 0.0
    
    # 成交量结构
    df["vol_ma_ratio"] = df["volume"] / (df["volume"].rolling(20).mean() + 1e-10)
    df["amt_ma_ratio"] = df["amount"] / (df["amount"].rolling(20).mean() + 1e-10)
    
    return df


def compute_volatility_features(df: pd.DataFrame) -> pd.DataFrame:
    """波动率结构 — 新增 3 维"""
    df = df.copy()
    daily_ret = df["close"].pct_change()
    
    # 偏度和峰度
    df["vol_skew_20"] = daily_ret.rolling(20).skew()
    df["vol_kurt_20"] = daily_ret.rolling(20).kurt()
    
    # 上涨/下跌波动率比
    pos_vol = daily_ret.clip(lower=0).rolling(20).std()
    neg_vol = (-daily_ret).clip(lower=0).rolling(20).std()
    df["up_down_vol_ratio"] = pos_vol / (neg_vol + 1e-10)
    
    return df


def compute_interaction_features(df: pd.DataFrame) -> pd.DataFrame:
    """交互特征 — 新增 3 维"""
    df = df.copy()
    
    # 量价相关性 (20日)
    vol_rank = df["volume"].rolling(20).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False
    )
    close_rank = df["close"].rolling(20).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False
    )
    df["price_vol_corr_20"] = df["close"].rolling(20).corr(df["volume"])
    df["price_vol_corr_20"] = df["price_vol_corr_20"].fillna(0)
    
    # 振幅
    df["ret_range"] = (df["high"] - df["low"]) / (df["low"] + 1e-10)
    df["ret_range_ma_20"] = df["ret_range"].rolling(20).mean()
    
    # 跳空
    df["gap_pct"] = (df["open"] - df["close"].shift(1)) / (df["close"].shift(1) + 1e-10)
    
    return df


def compute_signal_features(df: pd.DataFrame) -> pd.DataFrame:
    """信号特征 — 新增 2 维"""
    df = df.copy()
    
    # 均线交叉信号
    df["ma_cross_5_20"] = ((df["sma_5"] > df["sma_20"]) & 
                           (df["sma_5"].shift(1) <= df["sma_20"].shift(1))).astype(float)
    df["ma_cross_20_60"] = ((df["sma_20"] > df["sma_60"]) & 
                            (df["sma_20"].shift(1) <= df["sma_60"].shift(1))).astype(float)
    
    return df


def compute_fundamental_features(df: pd.DataFrame, fundamentals: dict) -> pd.DataFrame:
    """基本面特征（保留 V10 的 11 维占位，需要有效数据源）"""
    df = df.copy()
    df["eps"] = fundamentals.get("eps", np.nan)
    df["revenue"] = fundamentals.get("revenue", np.nan)
    df["net_profit"] = fundamentals.get("net_profit", np.nan)
    df["bps"] = fundamentals.get("bps", np.nan)
    df["roe"] = fundamentals.get("roe", np.nan)
    if df["eps"].notna().any():
        df["pe"] = df["close"] / (df["eps"] + 1e-10)
    else:
        df["pe"] = np.nan
    if df["bps"].notna().any():
        df["pb"] = df["close"] / (df["bps"] + 1e-10)
    else:
        df["pb"] = np.nan
    df["profit_margin"] = df["eps"] / (df["close"] + 1e-10)
    df["revenue_yoy"] = fundamentals.get("revenue_yoy", np.nan)
    df["net_profit_yoy"] = fundamentals.get("net_profit_yoy", np.nan)
    df["gross_margin"] = fundamentals.get("gross_margin", np.nan)
    return df


def compute_event_features(df: pd.DataFrame, has_forecast: bool = False,
                           yjyg_max_change: float = 0.0,
                           event_data: dict = None) -> pd.DataFrame:
    """事件特征 — 业绩预告数据"""
    df = df.copy()
    if event_data:
        df["has_forecast"] = float(event_data.get("has_forecast", 0))
        df["yjyg_max_change_pct"] = float(event_data.get("yjyg_max_change", 0) or 0)
        df["forecast_type"] = 1 if event_data.get("forecast_type", "") else 0
    else:
        df["has_forecast"] = float(has_forecast)
        df["yjyg_max_change_pct"] = yjyg_max_change
        df["forecast_type"] = 0
    return df


def compute_flow_features(df: pd.DataFrame, buy_inst_count: int = 0,
                          has_lhb: bool = False,
                          fund_hist: dict = None) -> pd.DataFrame:
    """资金流特征 — 新增多日主力净额
    fund_hist: {date_str: main_net_float}
    """
    df = df.copy()
    df["buy_inst_count"] = float(buy_inst_count)
    df["has_lhb"] = float(has_lhb)
    df["main_net_today"] = np.nan
    df["main_net_5d"] = np.nan
    df["main_net_10d"] = np.nan
    
    if fund_hist:
        dates = sorted(fund_hist.keys())
        hist_series = pd.Series({d: float(fund_hist[d]) for d in dates}, name="_main_net")
        hist_series.index = pd.to_datetime(hist_series.index)
        # 对齐到 df 的日期
        df_idx = pd.to_datetime(df["date"]) if "date" in df.columns else df.index
        aligned = hist_series.reindex(df_idx, method=None).fillna(0)
        df["main_net_today"] = aligned.values
        df["main_net_5d"] = aligned.rolling(5, min_periods=3).sum().values
        df["main_net_10d"] = aligned.rolling(10, min_periods=5).sum().values
    
    return df


def compute_margin_features(df: pd.DataFrame, margin_balance: float = 0.0,
                            margin_buy: float = 0.0,
                            margin_data: dict = None) -> pd.DataFrame:
    """融资融券特征"""
    df = df.copy()
    if margin_data:
        df["margin_balance"] = float(margin_data.get("margin_balance", 0) or 0)
        df["margin_buy"] = float(margin_data.get("margin_buy", 0) or 0)
    else:
        df["margin_balance"] = margin_balance
        df["margin_buy"] = margin_buy
    return df


def build_full_features_v2(
    kline_df: pd.DataFrame,
    fundamentals: dict = None,
    has_forecast: bool = False,
    yjyg_max_change: float = 0.0,
    buy_inst_count: int = 0,
    has_lhb: bool = False,
    margin_balance: float = 0.0,
    margin_buy: float = 0.0,
    fund_hist: dict = None,
    event_data: dict = None,
    margin_data: dict = None,
    compute_advanced: bool = True,
) -> pd.DataFrame:
    """完整特征管线 v2 — 50+ 维特征
    
    包含:
    - 8 维核心技术特征 (V10保留)
    - 12 维经典技术指标 (RSI, MACD, BB, MA, ATR)
    - 5 维成交量结构 (换手率, 量比等)
    - 3 维波动率结构 (偏度, 峰度, 上下波动比)
    - 3 维交互特征 (量价相关性, 振幅, 跳空)
    - 2 维信号特征 (均线交叉)
    - 11 维基本面占位 (需要有效数据源)
    - 4 维事件特征
    - 2 维融资融券
    """
    df = compute_technical_features(kline_df)
    
    if compute_advanced:
        df = compute_ta_indicators(df)
        df = compute_volume_features(df)
        df = compute_volatility_features(df)
        df = compute_interaction_features(df)
        df = compute_signal_features(df)
    
    if fundamentals:
        df = compute_fundamental_features(df, fundamentals)
    
    df = compute_event_features(df, has_forecast, yjyg_max_change, event_data)
    df = compute_flow_features(df, buy_inst_count, has_lhb, fund_hist)
    df = compute_margin_features(df, margin_balance, margin_buy, margin_data)
    
    df = df.replace([np.inf, -np.inf], np.nan)
    
    for col in V11_FEATURE_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan
    
    return df


def compute_training_label(df: pd.DataFrame, forward_days: int = 5,
                           threshold: float = 0.03) -> pd.Series:
    """生成训练标签：未来 forward_days 天收益率 > threshold 为正样本
    
    Returns:
        二进制标签 Series，对齐 df 最后一行为 NaN（未来不可知）
    """
    future_ret = df["close"].shift(-forward_days) / df["close"] - 1
    label = (future_ret > threshold).astype(float)
    label.name = "label"
    return label


# ── 特征顺序（必须与训练时一致）──
V11_FEATURE_COLUMNS = [
    # 核心技术特征 (8)
    "ret_5d", "ret_20d", "vol_20d",
    "amount_ratio_5", "amount_ratio_20", "vol_spike",
    "cmf_20", "vpt_20",
    
    # 技术指标 (12)
    "rsi_14",
    "macd", "macd_signal", "macd_hist",
    "bb_width",
    "sma_5", "sma_20", "sma_60",
    "ma_dist_pct",
    "atr_14", "atr_pct",
    
    # 成交量结构 (5)
    "turnover", "turnover_ma_20", "turnover_ratio",
    "vol_ma_ratio", "amt_ma_ratio",
    
    # 波动率结构 (3)
    "vol_skew_20", "vol_kurt_20", "up_down_vol_ratio",
    
    # 交互特征 (3)
    "price_vol_corr_20", "ret_range", "gap_pct",
    
    # 信号特征 (2)
    "ma_cross_5_20", "ma_cross_20_60",
    
    # 基本面 (11) — 占位，需要有效数据源
    "eps", "revenue", "revenue_yoy", "net_profit", "net_profit_yoy",
    "bps", "roe", "gross_margin", "pe", "pb", "profit_margin",
    
    # 事件 (4)
    "has_forecast", "yjyg_max_change_pct",
    "buy_inst_count", "has_lhb",
    
    # 资金流多日主力净额 (3) — 需传入 fund_hist
    "main_net_today", "main_net_5d", "main_net_10d",

    # 融资融券 (2)
    "margin_balance", "margin_buy",
]


if __name__ == "__main__":
    # 测试
    dates = pd.date_range("2025-01-01", "2026-07-03", freq="B")
    np.random.seed(42)
    test_df = pd.DataFrame({
        "date": dates,
        "open": 10 + np.random.randn(len(dates)).cumsum() * 0.1,
        "high": 0, "low": 0, "close": 0,
        "volume": np.random.randint(1e7, 5e7, len(dates)),
        "amount": np.random.randint(1e9, 5e9, len(dates)),
        "turnover": np.random.rand(len(dates)) * 5,
    })
    test_df["close"] = test_df["open"] + np.random.randn(len(dates)) * 0.2
    test_df["high"] = test_df[["open", "close"]].max(axis=1) + 0.1
    test_df["low"] = test_df[["open", "close"]].min(axis=1) - 0.1
    test_df["close"] = test_df["close"].clip(lower=5)
    
    feats = build_full_features_v2(test_df)
    label = compute_training_label(test_df)
    
    print(f"V11 特征维度: {len(V11_FEATURE_COLUMNS)}")
    print(f"特征列全否: {all(c in feats.columns for c in V11_FEATURE_COLUMNS)}")
    print(f"缺失列: {[c for c in V11_FEATURE_COLUMNS if c not in feats.columns]}")
    
    latest = feats[V11_FEATURE_COLUMNS].iloc[-1]
    print(f"\n最新行特征数: {latest.notna().sum()}/{len(V11_FEATURE_COLUMNS)}")
    print(f"正样本率: {label.mean():.2%}")
    
    # 打印特征列表确认
    print(f"\n完整特征列表 ({len(V11_FEATURE_COLUMNS)} 维):")
    for i, col in enumerate(V11_FEATURE_COLUMNS, 1):
        print(f"  {i:2d}. {col}")


# ============================================================
# V2.4 新增特征：MA形态 + MACD(12,26,9) + RSI(6/12/24)
# 基于 Chord-hope 三大指标组合实战策略
# ============================================================
def compute_ma_pattern_features(df: pd.DataFrame) -> pd.DataFrame:
    """MA 形态特征 (4维) — 趋势方向"""
    df = df.sort_values("date").copy()
    if "ma_5" not in df.columns:
        df["ma_5"] = df["close"].rolling(5).mean()
    if "ma_20" not in df.columns:
        df["ma_20"] = df["close"].rolling(20).mean()
    if "ma_60" not in df.columns:
        df["ma_60"] = df["close"].rolling(60).mean()
    # 短期多头: ma5 > ma20
    df["ma5_gt_ma20"] = (df["ma_5"] > df["ma_20"]).astype(float)
    # 中期多头: ma20 > ma60
    df["ma20_gt_ma60"] = (df["ma_20"] > df["ma_60"]).astype(float)
    # 股价站稳60日线 (Chord-hope 进场条件)
    df["price_above_ma60"] = (df["close"] > df["ma_60"]).astype(float)
    # 60日均线斜率 (5日变化率)
    df["ma60_slope"] = df["ma_60"].pct_change(5)
    return df


def compute_macd_features(df: pd.DataFrame) -> pd.DataFrame:
    """MACD 特征 (4维) — 趋势动能与拐点"""
    df = df.sort_values("date").copy()
    close = df["close"]
    # 标准参数: EMA12, EMA26, Signal9
    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    dif = ema_12 - ema_26
    dea = dif.ewm(span=9, adjust=False).mean()
    hist = (dif - dea) * 2  # MACD柱状线
    df["macd_dif"] = dif
    df["macd_dea"] = dea
    df["macd_hist"] = hist
    # DIF在零轴上方天数（最近5日累计）,衡量多头持续性
    df["macd_zero_above"] = (dif > 0).rolling(5).sum() / 5.0
    return df


def compute_rsi_features(df: pd.DataFrame) -> pd.DataFrame:
    """RSI 特征 (5维) — 节奏与超买超卖"""
    df = df.sort_values("date").copy()
    for n in [6, 12, 24]:
        delta = df["close"].diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.rolling(n, min_periods=n).mean()
        avg_loss = loss.rolling(n, min_periods=n).mean()
        rs = avg_gain / (avg_loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))
        df[f"rsi_{n}"] = rsi
    # RSI6 最近3天内是否触底回升 (<30)
    rsi6 = df["rsi_6"]
    df["rsi_oversold_recent"] = (rsi6 < 30).rolling(3).max().fillna(0)
    # RSI6 最近3天内是否触及超买 (>70)
    df["rsi_overbought_recent"] = (rsi6 > 70).rolling(3).max().fillna(0)
    return df


# 合并为一个函数
def compute_v24_extra_features(df: pd.DataFrame) -> pd.DataFrame:
    df = compute_ma_pattern_features(df)
    df = compute_macd_features(df)
    df = compute_rsi_features(df)
    return df
