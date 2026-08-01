"""Feature engineering — adapted from features_v2.py for crypto OHLCV."""
from __future__ import annotations

import numpy as np
import pandas as pd
from .config import TECH_LOOKBACK

FACTOR_GROUP_NAMES = {
    "momentum": "momentum",
    "volatility": "volatility",
    "volume": "volume",
    "trend": "trend",
    "mean_reversion": "mean_reversion",
    "funding": "funding",
    "oi": "oi",
    "price_action": "price_action",
}


# ─── helpers ───
def _zscore(s: pd.Series) -> pd.Series:
    return (s - s.mean()) / (s.std() + 1e-10)


def _rolling_zscore(s: pd.Series, w: int) -> pd.Series:
    return (s - s.rolling(w).mean()) / (s.rolling(w).std() + 1e-10)


# ─── Momentum ───
def add_momentum(df: pd.DataFrame) -> pd.DataFrame:
    df["ret_1"] = df["close"].pct_change(1)
    for p in [2, 5, 10, 20, 40]:
        df[f"ret_{p}"] = df["close"].pct_change(p)
        df[f"z_ret_{p}"] = _rolling_zscore(df[f"ret_{p}"], TECH_LOOKBACK)
    # momentum strength: % of positive returns over window
    for w in [10, 20]:
        pos = (df["ret_1"] > 0).rolling(w).sum()
        df[f"pos_ratio_{w}"] = pos / w
    # serial correlation of returns
    for w in [5, 10]:
        df[f"ret_auto_{w}"] = df["ret_1"].rolling(w).apply(
            lambda s: (s - s.mean()).autocorr() if len(s) > 3 and s.std() > 1e-10 else 0, raw=False
        )
    return df


# ─── Volatility ───
def add_volatility(df: pd.DataFrame) -> pd.DataFrame:
    df["hi_lo"] = (df["high"] - df["low"]) / df["close"]
    df["hi_lo_ma"] = df["hi_lo"].rolling(20).mean()
    df["hi_lo_std"] = _rolling_zscore(df["hi_lo"], 20)
    for w in [5, 10, 20]:
        df[f"volatility_{w}"] = df["ret_1"].rolling(w).std()
        df[f"z_vol_{w}"] = _rolling_zscore(df[f"volatility_{w}"], TECH_LOOKBACK)
    # ATR
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - df["close"].shift(1)).abs(),
            (df["low"] - df["close"].shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["atr"] = tr
    df["atr_14"] = tr.rolling(14).mean()
    df["atr_pct"] = df["atr_14"] / df["close"]
    # volatility skew
    daily_ret = df["ret_1"]
    up_vol = daily_ret.where(daily_ret > 0, 0).abs().rolling(20).std()
    dn_vol = daily_ret.where(daily_ret < 0, 0).abs().rolling(20).std()
    df["up_dn_vol_ratio"] = up_vol / (dn_vol + 1e-10)
    return df


# ─── Volume ───
def add_volume(df: pd.DataFrame) -> pd.DataFrame:
    df["volume"] = df["volume"].clip(lower=1e-8)
    for w in [5, 10, 20]:
        df[f"vol_ma_{w}"] = df["volume"].rolling(w).mean()
        df[f"vol_ratio_{w}"] = df["volume"] / (df[f"vol_ma_{w}"] + 1e-10)
    # volume volatility
    df["vol_std_20"] = df["volume"].rolling(20).std() / (df["volume"].rolling(20).mean() + 1e-10)
    # volume price correlation
    df["price_vol_corr"] = (
        df["ret_1"]
        .rolling(20)
        .corr(df["volume"].pct_change())
    )
    return df


# ─── Trend (MA-based) ───
def add_trend(df: pd.DataFrame) -> pd.DataFrame:
    for w in [7, 14, 25, 50, 100]:
        df[f"sma_{w}"] = df["close"].rolling(w).mean()
        df[f"ma_dist_{w}"] = (df["close"] - df[f"sma_{w}"]) / df[f"sma_{w}"]
    # MA cross
    df["ma_cross_7_25"] = (df["sma_7"] - df["sma_25"]) / df["sma_25"]
    df["ma_cross_25_50"] = (df["sma_25"] - df["sma_50"]) / df["sma_50"]
    df["ma_cross_50_100"] = (df["sma_50"] - df["sma_100"]) / df["sma_100"]
    # Trend strength (ADX-like simplified)
    for w in [14]:
        up = df["high"].diff(w)
        dn = -df["low"].diff(w)
        pos = up.where((up > 0) & (up > dn), 0)
        neg = dn.where((dn > 0) & (dn > up), 0)
        tr = pd.concat(
            [df["high"] - df["low"], (df["high"] - df["close"].shift(1)).abs(), (df["low"] - df["close"].shift(1)).abs()],
            axis=1,
        ).max(axis=1)
        tr_ma = tr.rolling(w).mean() + 1e-10
        pos_ma = pos.rolling(w).mean() / tr_ma
        neg_ma = neg.rolling(w).mean() / tr_ma
        df["adx"] = (pos_ma - neg_ma).abs() * 100
    return df


# ─── RSI / Mean reversion ───
def add_mean_reversion(df: pd.DataFrame) -> pd.DataFrame:
    for w in [7, 14, 21]:
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(w).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(w).mean()
        rs = gain / (loss + 1e-10)
        df[f"rsi_{w}"] = 100 - (100 / (1 + rs))
    # Bollinger Bands
    for w in [14, 20]:
        mid = df["close"].rolling(w).mean()
        std = df["close"].rolling(w).std()
        df[f"bb_width_{w}"] = 2 * std / mid
        df[f"bb_pos_{w}"] = (df["close"] - mid + 2 * std) / (4 * std + 1e-10)
    # Distance from recent high/low
    for w in [10, 20]:
        df[f"near_high_{w}"] = df["close"] / df["high"].rolling(w).max() - 1
        df[f"near_low_{w}"] = df["close"] / df["low"].rolling(w).min() - 1
    # gap
    df["gap_pct"] = df["open"] / df["close"].shift(1) - 1
    return df


# ─── Funding rate ───
def add_funding(df: pd.DataFrame) -> pd.DataFrame:
    if "funding_rate" not in df.columns or df["funding_rate"].isna().all():
        return df
    df["fr"] = df["funding_rate"]
    for w in [3, 7, 14]:
        df[f"fr_ma_{w}"] = df["fr"].rolling(w).mean()
        df[f"fr_std_{w}"] = df["fr"].rolling(w).std()
    df["fr_z"] = _rolling_zscore(df["fr"], 20)
    # funding regime: consistently positive/negative
    df["fr_pos_ratio_14"] = (df["fr"] > 0).rolling(14).mean()
    return df


# ─── Open Interest ───
def add_open_interest(df: pd.DataFrame) -> pd.DataFrame:
    if "open_interest" not in df.columns or df["open_interest"].isna().all():
        return df
    df["oi"] = df["open_interest"]
    for w in [5, 10, 20]:
        df[f"oi_ma_{w}"] = df["oi"].rolling(w).mean()
        df[f"oi_ratio_{w}"] = df["oi"] / (df[f"oi_ma_{w}"] + 1e-10)
    df["oi_z"] = _rolling_zscore(df["oi"], 20)
    # OI-volume correlation
    df["oi_vol_corr"] = df["oi"].pct_change().rolling(20).corr(df["volume"].pct_change())
    # OI-price divergence: price up but OI down = weak trend
    df["oi_price_div"] = (df["ret_5"] - df["oi"].pct_change(5).fillna(0)).clip(-0.1, 0.1)
    return df


# ─── Price action patterns ───
def add_price_action(df: pd.DataFrame) -> pd.DataFrame:
    # Candle body / wick ratios
    df["body"] = (df["close"] - df["open"]).abs()
    df["upper_wick"] = df["high"] - df[["close", "open"]].max(axis=1)
    df["lower_wick"] = df[["close", "open"]].min(axis=1) - df["low"]
    candle_range = df["high"] - df["low"] + 1e-10
    df["body_ratio"] = df["body"] / candle_range
    df["upper_wick_ratio"] = df["upper_wick"] / candle_range
    df["lower_wick_ratio"] = df["lower_wick"] / candle_range
    # Consecutive candles
    df["green"] = (df["close"] > df["open"]).astype(float)
    df["consec_green"] = df["green"] * (df["green"].groupby((df["green"] != df["green"].shift()).cumsum()).cumcount() + 1)
    df["consec_red"] = (1 - df["green"]) * ((1 - df["green"]).groupby((df["green"] == df["green"].shift()).cumsum()).cumcount() + 1)
    # Doji
    df["doji"] = (df["body"] / candle_range < 0.1).astype(float)
    # Engulfing
    df["engulfing"] = (
        (df["close"] > df["open"])
        & (df["close"].shift(1) < df["open"].shift(1))
        & (df["close"] > df["open"].shift(1))
        & (df["open"] < df["close"].shift(1))
    ).astype(float)
    return df


# ─── Opening Range (ORB) — Fabio-inspired ───
def add_open_range(df: pd.DataFrame) -> pd.DataFrame:
    """Daily opening range factors.

    Day boundary = UTC midnight. OR = first `or_bars` bars of each day.
    Captures: did price break OR high/low, where is price within the OR,
    how wide is today's OR vs recent, and post-break continuation.
    """
    or_bars = 2  # first 2 bars of day (4h on 2h tf)

    df["_date"] = df["timestamp"].dt.date
    df["_bar_in_day"] = df.groupby("_date").cumcount()

    mask = df["_bar_in_day"] < or_bars
    df["_or_high_tmp"] = df["high"].where(mask)
    df["_or_low_tmp"] = df["low"].where(mask)
    or_high = df.groupby("_date")["_or_high_tmp"].transform("max").ffill()
    or_low = df.groupby("_date")["_or_low_tmp"].transform("min").ffill()

    df["or_high"] = or_high
    df["or_low"] = or_low
    df["or_range_pct"] = (or_high - or_low) / df["close"]
    df["or_pos"] = (df["close"] - or_low) / (or_high - or_low + 1e-10)
    df["break_or_high"] = (df["close"] > or_high).astype(float)
    df["break_or_low"] = (df["close"] < or_low).astype(float)
    df["or_break_dir"] = df["break_or_high"].astype(float) - df["break_or_low"].astype(float)
    df["dist_from_or_high"] = df["close"] / or_high - 1
    df["dist_from_or_low"] = df["close"] / or_low - 1
    # OR width vs recent average width (breakout quality: narrow range → big move potential)
    recent_or_width = df.groupby("_date")["or_range_pct"].transform("first").rolling(20, min_periods=5).mean()
    df["or_width_ratio"] = df["or_range_pct"] / (recent_or_width + 1e-10)
    # post-break: bar broke OR high and close stays above
    df["or_break_hold"] = (df["or_break_dir"] > 0).astype(float) * (df["close"] > df["or_high"]).astype(float)

    df = df.drop(columns=["_date", "_bar_in_day", "_or_high_tmp", "_or_low_tmp"])
    return df


# ─── Volume Profile / POC — Fabio-inspired ───
def add_volume_profile(df: pd.DataFrame) -> pd.DataFrame:
    """Volume Profile / POC factors (rolling approximation).

    - vwap_24: rolling volume-weighted average price (24 bars)
    - dist_vwap_24: distance of close from VWAP
    - poc_price: price bin (10 bins) with highest volume in window → Point of Control
    - dist_poc: distance of close from POC
    - poc_zone: is close within high-volume zone (POC ± 1 bin)?
    """
    w = 24
    tp = (df["high"] + df["low"] + df["close"]) / 3
    df["_tp"] = tp

    # VWAP
    num = (df["_tp"] * df["volume"]).rolling(w).sum()
    den = df["volume"].rolling(w).sum()
    df["vwap_24"] = num / (den + 1e-10)
    df["dist_vwap_24"] = df["close"] / df["vwap_24"] - 1

    # POC = highest-volume price bin over rolling window (vectorized per group)
    poc = df["_tp"].to_numpy()
    vols = df["volume"].clip(lower=1e-8).to_numpy()
    n = len(df)
    poc_out = np.full(n, np.nan)
    for i in range(n):
        s = max(0, i - w + 1)
        seg_p = poc[s:i + 1]
        if len(seg_p) < 10:
            continue
        lo, hi = seg_p.min(), seg_p.max()
        if hi - lo < 1e-12:
            poc_out[i] = seg_p.mean()
            continue
        bins = np.linspace(lo, hi, 11)
        idx = np.clip(np.digitize(seg_p, bins) - 1, 0, 9)
        vol_sum = np.zeros(10)
        np.add.at(vol_sum, idx, vols[s:i + 1])
        best = int(np.argmax(vol_sum))
        poc_out[i] = (bins[best] + bins[best + 1]) / 2
    df["poc_price"] = poc_out

    df["dist_poc"] = df["close"] / df["poc_price"] - 1
    df["poc_above"] = (df["close"] > df["poc_price"]).astype(float)
    # in POC zone (± 0.5% around POC)
    df["in_poc_zone"] = (df["dist_poc"].abs() < 0.005).astype(float)
    df["poc_strength"] = df["_tp"].rolling(w).count() / w  # data availability proxy

    df = df.drop(columns=["_tp"])
    return df


# ─── Labels (forward-looking, single group) ───
def add_labels(df: pd.DataFrame, forward: int = 4, threshold: float = 0.02) -> pd.DataFrame:
    """Wrapper — forwards to single-group version."""
    return add_labels_single(df, forward=forward, threshold=threshold)


def add_labels_single(g: pd.DataFrame, forward: int = 4, threshold: float = 0.02) -> pd.DataFrame:
    """Add forward return and binary long/short labels (no groupby — assumes one symbol+tf)."""
    fwd_ret = g["close"].shift(-forward) / g["close"] - 1
    g["fwd_ret"] = fwd_ret
    g["label_long"] = (fwd_ret > threshold).astype(float)
    g["label_short"] = (fwd_ret < -threshold).astype(float)
    g["label_mid"] = ((fwd_ret > 0) & (fwd_ret <= threshold * 0.5)).astype(float)
    g["label_multiclass"] = 0
    g.loc[g["label_long"] == 1, "label_multiclass"] = 1
    g.loc[g["label_short"] == 1, "label_multiclass"] = 2
    return g


# ─── Full pipeline ───
ALL_FACTORS = [
    add_momentum,
    add_volatility,
    add_volume,
    add_trend,
    add_mean_reversion,
    add_funding,
    add_open_interest,
    add_price_action,
    add_open_range,
    add_volume_profile,
]

FACTOR_COLUMNS: list[str] = []  # populated at runtime


def compute_features(
    df: pd.DataFrame,
    forward: int | None = None,
    threshold: float | None = None,
) -> pd.DataFrame:
    """Run full feature pipeline on raw OHLCV data."""
    df = df.copy().sort_values(["symbol", "timeframe", "timestamp"])
    
    # Per-group computation
    groups = ["symbol", "timeframe"] if "symbol" in df.columns and "timeframe" in df.columns else None
    
    if groups and all(c in df.columns for c in groups):
        # groupby.apply drops group columns; save them to re-merge
        result_parts = []
        for name, group in df.groupby(groups):
            g = _compute_group(group, forward=forward, threshold=threshold)
            result_parts.append(g)
        df = pd.concat(result_parts, ignore_index=True)
    else:
        df = _compute_group(df, forward=forward, threshold=threshold)

    global FACTOR_COLUMNS
    if not FACTOR_COLUMNS:
        exclude = {"timestamp", "symbol", "timeframe", "open", "high", "low", "close", "volume",
                    "label_long", "label_short", "label_mid", "label_multiclass", "fwd_ret"}
        FACTOR_COLUMNS = [c for c in df.columns if c not in exclude and df[c].dtype in ("float64", "float32", "int64")]
    return df


def _compute_group(g: pd.DataFrame, forward: int | None, threshold: float | None) -> pd.DataFrame:
    g = g.sort_values("timestamp").reset_index(drop=True)
    for fn in ALL_FACTORS:
        g = fn(g)
    if forward is not None and threshold is not None:
        g = add_labels_single(g, forward=forward, threshold=threshold)
    return g


def list_factors() -> list[str]:
    """Return all factor column names (requires compute_features first)."""
    return FACTOR_COLUMNS
