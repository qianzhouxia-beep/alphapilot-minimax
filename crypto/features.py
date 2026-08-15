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


# ─── OI state combination — OI cheat-sheet quantized (order-flow quant) ───
def add_oi_state(df: pd.DataFrame) -> pd.DataFrame:
    """Open-interest price-state combination factors.

    Classic OI cheat-sheet, quantized to binaries + continuous z:
      price up  + OI up   → fresh longs entering   → trend continuation
      price up  + OI down → shorts covering        → rally exhausts
      price dn  + OI up   → fresh shorts entering  → bearish continuation
      price dn  + OI down → longs exiting          → capitulation flush
    Plus: 5-bar OI change z-score and rolling price-OI correlation.
    """
    if "open_interest" not in df.columns or df["open_interest"].isna().all():
        return df
    oi = df["open_interest"]
    oi_chg = oi.pct_change(5).fillna(0.0)
    oi_chg_z = _rolling_zscore(oi_chg, 60)

    ret5 = df["ret_5"].fillna(0.0)
    up = ret5 > 0.0005
    dn = ret5 < -0.0005
    oi_up = oi_chg > 0.001
    oi_dn = oi_chg < -0.001

    df["oi_confirm_long"] = (up & oi_up).astype(float)   # fresh longs → continuation
    df["oi_exhaust_long"] = (up & oi_dn).astype(float)   # shorts covering → fade rally
    df["oi_confirm_short"] = (dn & oi_up).astype(float)  # fresh shorts → continuation
    df["oi_exhaust_short"] = (dn & oi_dn).astype(float)  # longs exiting → flush
    df["oi_chg_z_5"] = oi_chg_z
    df["oi_ret_corr_20"] = df["ret_1"].rolling(20).corr(oi.pct_change())
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


# ─── Beheading / "断头铡刀" (bearish candle cutting through MAs) ───
def add_beheading(df: pd.DataFrame) -> pd.DataFrame:
    """'断头铡刀' (beheading guillotine) bearish reversal factors.

    Classic retail setup: a big bearish candle simultaneously breaks through
    the 5/10/20-period MAs after the MA fan has converged, ideally on volume.
    Quantified as:
      - ma_bear_align: MA alignment (negative = bearish stack)
      - ma_converge:   MA fan convergence (small = tight range, breakout fuel)
      - beheading:     binary signal — bearish candle breaks all three MAs
      - beheading_vol: same signal but volume-confirmed
      - beheading_hold: price stays below broken MAs next bar (confirmation)
    """
    for w in [5, 10, 20]:
        df[f"beh_ma_{w}"] = df["close"].rolling(w).mean()

    # MA stack alignment: how far below the fast MA is price relative to slow MAs
    df["beh_ma5_ma20"] = (df["beh_ma_5"] - df["beh_ma_20"]) / (df["beh_ma_20"] + 1e-10)
    df["beh_ma10_ma20"] = (df["beh_ma_10"] - df["beh_ma_20"]) / (df["beh_ma_20"] + 1e-10)
    # bear alignment: fast MAs below slow MAs = bearish stack (negative)
    df["ma_bear_align"] = (df["beh_ma_5"] / (df["beh_ma_20"] + 1e-10) - 1) * -1
    # fan convergence: std of the three MA levels normalized by price
    df["ma_converge"] = (
        df[["beh_ma_5", "beh_ma_10", "beh_ma_20"]].std(axis=1) / (df["close"] + 1e-10)
    )

    # bearish candle: close < open, body larger than threshold
    body = (df["open"] - df["close"]).clip(lower=0)
    rng = df["high"] - df["low"] + 1e-10
    bearish = (df["close"] < df["open"]) & (body / rng > 0.5)

    # breaks all three MAs from above
    broke_all = (
        (df["close"].shift(1) > df["beh_ma_5"].shift(1))
        & (df["close"].shift(1) > df["beh_ma_10"].shift(1))
        & (df["close"].shift(1) > df["beh_ma_20"].shift(1))
        & (df["close"] < df["beh_ma_5"])
        & (df["close"] < df["beh_ma_10"])
        & (df["close"] < df["beh_ma_20"])
    )
    # volume confirmation: today volume > 1.5× 20-bar avg
    vol_conf = df["volume"] / (df["volume"].rolling(20).mean() + 1e-10) > 1.5

    df["beheading"] = (bearish & broke_all).astype(float)
    df["beheading_vol"] = (bearish & broke_all & vol_conf).astype(float)
    # confirmation: price still below broken MAs next bar
    below_hold = (
        (df["close"] < df["beh_ma_5"])
        & (df["close"] < df["beh_ma_10"])
        & (df["close"] < df["beh_ma_20"])
    )
    df["beheading_hold"] = df["beheading"].shift(1) * below_hold.astype(float)
    return df


# ─── "神奇基准线" (Magic baseline) mean-reversion factors ───
def add_magic_line(df: pd.DataFrame) -> pd.DataFrame:
    """'神奇基准线' (magic baseline) factors.

    Original 通达信 formula:
        XX2 = MA(CLOSE, 80) - MA(CLOSE, 13) / 3
        magic = MA((CLOSE - XX2) / XX2, 1)
    Buy signal when magic crosses above 0 (price returns above baseline),
    or extreme-low reversal (magic at N-bar low then turning up with a green candle).

    Quantified here:
      - magic_line:  the deviation ratio itself (signal 1: crosses 0)
      - magic_line_z: rolling z-score (extreme readings → reversal candidates)
      - magic_baseline: the baseline price level itself
      - magic_cross_0: binary — magic crosses above 0 (trend-strength return)
      - magic_extreme_low: binary — magic at 20-bar low then turning up
    """
    ma80 = df["close"].rolling(80).mean()
    ma13 = df["close"].rolling(13).mean()
    baseline = ma80 - ma13 / 3.0
    df["magic_baseline"] = baseline
    deviation = (df["close"] - baseline) / (baseline + 1e-10)
    df["magic_line"] = deviation.rolling(1).mean()
    df["magic_line_z"] = _rolling_zscore(df["magic_line"], 40)

    # cross above 0 (from below) — trend return signal
    above = (df["magic_line"] > 0).astype(float)
    prev_above = (df["magic_line"].shift(1) > 0).astype(float)
    df["magic_cross_0"] = (above - prev_above).clip(lower=0)

    # extreme low: magic at 20-bar low then turning up with a green candle
    is_low = df["magic_line"] == df["magic_line"].rolling(20).min()
    prev_not_low = (df["magic_line"].shift(1) != df["magic_line"].rolling(20).min().shift(1)).astype(float)
    green = (df["close"] > df["open"]).astype(float)
    df["magic_extreme_low"] = (is_low & (prev_not_low > 0) & (green > 0)).astype(float)
    return df


# ─── Smart Money Concepts: FVG + Order Blocks — ICT/SMC-inspired ───
def add_fvg(df: pd.DataFrame) -> pd.DataFrame:
    """Fair Value Gap (FVG) + Order Block factors — SMC / ICT quantized.

    FVG: a 3-candle inefficiency where candle[i-2] and candle[i] do not overlap:
      - Bullish FVG: high[i-2] < low[i]   (gap up, price often retraces into it)
      - Bearish FVG: low[i-2]  > high[i]  (gap down, price often rallies into it)
    Order Block (simplified): the last opposite-color candle before a 20-bar
    breakout — a supply/demand zone that price tends to respect.

    Factors:
      - fvg_up_gap_pct / fvg_dn_gap_pct: size of most recent unfilled FVG / price
      - dist_fvg_up / dist_fvg_dn: close relative to the zone edge of the most
        recent unfilled FVG (negative = price already below/above the zone)
      - fvg_up_retest / fvg_dn_retest: price traded inside the recent zone (binary)
      - fvg_up_cnt_20 / fvg_dn_cnt_20: # of FVGs formed in the last 20 bars
      - dist_ob_bull / dist_ob_bear: close relative to the most recent order block
    """
    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    o = df["open"].to_numpy()
    c = df["close"].to_numpy()
    n = len(df)

    bull_gap_pct = np.full(n, np.nan)
    bear_gap_pct = np.full(n, np.nan)
    dist_bull = np.full(n, np.nan)
    dist_bear = np.full(n, np.nan)
    retest_bull = np.zeros(n)
    retest_bear = np.zeros(n)

    cur_bull_lo = cur_bull_hi = None
    cur_bear_lo = cur_bear_hi = None
    for i in range(n):
        # update most recent unfilled FVG before any new formation at bar i
        if cur_bull_hi is not None:
            if l[i] <= cur_bull_lo:          # filled — price swept the zone low
                cur_bull_lo = cur_bull_hi = None
            else:
                dist_bull[i] = (c[i] - cur_bull_lo) / cur_bull_lo
                if l[i] <= cur_bull_hi:      # price traded into the zone → retest
                    retest_bull[i] = 1.0
        if cur_bear_hi is not None:
            if h[i] >= cur_bear_hi:          # filled — price swept the zone high
                cur_bear_lo = cur_bear_hi = None
            else:
                dist_bear[i] = (c[i] - cur_bear_hi) / cur_bear_hi
                if h[i] >= cur_bear_lo:
                    retest_bear[i] = 1.0

        # new FVG formation between bar i-2 and bar i
        if i >= 2:
            if h[i - 2] < l[i]:
                cur_bull_lo, cur_bull_hi = h[i - 2], l[i]
                bull_gap_pct[i] = (l[i] - h[i - 2]) / c[i]
            if l[i - 2] > h[i]:
                cur_bear_lo, cur_bear_hi = h[i], l[i - 2]
                bear_gap_pct[i] = (l[i - 2] - h[i]) / c[i]

    # order blocks: last opposite-color candle before a 20-bar breakout
    ob_bull_dist = np.full(n, np.nan)
    ob_bear_dist = np.full(n, np.nan)
    ob_bull_lo = ob_bull_hi = None
    ob_bear_lo = ob_bear_hi = None
    hi20 = np.full(n, np.nan)
    lo20 = np.full(n, np.nan)
    for i in range(n):
        s = max(0, i - 20)
        hi20[i] = h[s:i].max() if i > s else h[i]
        lo20[i] = l[s:i].min() if i > s else l[i]
    for i in range(1, n):
        if ob_bull_hi is not None:
            if l[i] <= ob_bull_lo:
                ob_bull_lo = ob_bull_hi = None
            else:
                ob_bull_dist[i] = (c[i] - ob_bull_hi) / ob_bull_hi
        if ob_bear_hi is not None:
            if h[i] >= ob_bear_hi:
                ob_bear_lo = ob_bear_hi = None
            else:
                ob_bear_dist[i] = (c[i] - ob_bear_lo) / ob_bear_lo
        # new bull OB: close breaks 20-bar high, prior candle was red
        if c[i] > hi20[i] and o[i - 1] > c[i - 1]:
            ob_bull_lo, ob_bull_hi = l[i - 1], h[i - 1]
        # new bear OB: close breaks 20-bar low, prior candle was green
        if c[i] < lo20[i] and o[i - 1] < c[i - 1]:
            ob_bear_lo, ob_bear_hi = l[i - 1], h[i - 1]

    df["fvg_up_gap_pct"] = bull_gap_pct
    df["fvg_dn_gap_pct"] = bear_gap_pct
    df["dist_fvg_up"] = dist_bull
    df["dist_fvg_dn"] = dist_bear
    df["fvg_up_retest"] = retest_bull
    df["fvg_dn_retest"] = retest_bear
    df["fvg_up_cnt_20"] = (df["high"].shift(2) < df["low"]).rolling(20).sum()
    df["fvg_dn_cnt_20"] = (df["low"].shift(2) > df["high"]).rolling(20).sum()
    df["dist_ob_bull"] = ob_bull_dist
    df["dist_ob_bear"] = ob_bear_dist
    return df


# ─── Order flow / CVD — Binance taker-buy volume (order-flow quant) ───
def add_orderflow(df: pd.DataFrame) -> pd.DataFrame:
    """Cumulative Volume Delta (CVD) order-flow factors.

    delta = aggressive buys − aggressive sells per bar (taker_buy_vol is the
    base-volume executed by market-buy orders; the rest of volume is passive).
    CVD = cumulative delta — the running balance of who is pushing price.
    Divergence: price new high while CVD fails to confirm → buyer exhaustion.

    Factors:
      - taker_buy_ratio:   share of volume that was aggressive buying
      - delta:             net aggressive volume this bar (normalized)
      - cvd:               cumulative delta (per symbol+tf reset by group)
      - cvd_z:             rolling z-score of CVD
      - cvd_slope:         short vs long CVD momentum
      - cvd_div_top:       bearish divergence (price new high, CVD not) binary
      - cvd_div_bot:       bullish divergence (price new low, CVD not) binary
    """
    if "taker_buy_vol" not in df.columns or df["taker_buy_vol"].isna().all():
        return df

    vol = df["volume"].clip(lower=1e-10)
    tb = df["taker_buy_vol"].fillna(0.0)
    df["taker_buy_ratio"] = (tb / vol).clip(-1, 1)

    # net aggressive volume
    delta_raw = 2 * tb - df["volume"]
    vol_ma20 = df["volume"].rolling(20, min_periods=5).mean() + 1e-10
    df["delta"] = delta_raw / vol_ma20

    # cumulative delta normalized by typical volume
    df["cvd"] = delta_raw.cumsum() / vol_ma20

    # rolling z of CVD
    df["cvd_z"] = _rolling_zscore(df["cvd"], 60)
    # CVD short/long momentum ratio
    cvd_ma_fast = df["cvd"].rolling(10).mean()
    cvd_ma_slow = df["cvd"].rolling(40).mean()
    df["cvd_slope"] = (cvd_ma_fast - cvd_ma_slow) / (df["cvd"].rolling(40).std() + 1e-10)

    # Divergence (20-bar window)
    hi20 = df["high"].rolling(20, min_periods=10).max()
    lo20 = df["low"].rolling(20, min_periods=10).min()
    cvd_hi20 = df["cvd"].rolling(20, min_periods=10).max()
    cvd_lo20 = df["cvd"].rolling(20, min_periods=10).min()

    price_new_high = df["close"] >= hi20
    price_new_low = df["close"] <= lo20
    cvd_not_high = df["cvd"] < cvd_hi20 * 0.999
    cvd_not_low = df["cvd"] > cvd_lo20 * 1.001

    # bearish divergence: price pushes to new high but buyers don't confirm
    df["cvd_div_top"] = (price_new_high & cvd_not_high).astype(float)
    # bullish divergence: price makes new low but sellers aren't confirming
    df["cvd_div_bot"] = (price_new_low & cvd_not_low).astype(float)

    # delta persistence: % of last 10 bars with positive net aggressive flow
    df["delta_pos_ratio_10"] = (delta_raw > 0).rolling(10, min_periods=5).mean()
    return df


# ─── Cross-symbol macro factors — BTC dominance / market breadth ───
def add_cross_symbol(df: pd.DataFrame) -> pd.DataFrame:
    """BTC dominance + market breadth + relative strength (computed ACROSS symbols).

    Must run AFTER per-symbol feature computation. Uses only point-in-time
    data (rolling over past bars), no lookahead:
      - btc_dom:      BTC turnover / total universe turnover
      - btc_dom_z:    rolling z-score of BTC dominance (risk regime)
      - btc_ret_20:   BTC's own 20-bar return (market-wide momentum)
      - rel_btc_20:   symbol return − BTC return (relative strength vs market)
      - market_breadth: fraction of universe above 20-bar SMA (breadth regime)
      - breadth_z:    rolling z-score of breadth
      - eth_btc_z:    ETH/BTC rolling z-score (risk-on/risk-off tilt)
    """
    if "symbol" not in df.columns or "timeframe" not in df.columns:
        return df

    parts = []
    for tf, g in df.groupby("timeframe"):
        g = g.sort_values("timestamp")
        ts = g["timestamp"]
        is_btc = g["symbol"].str.startswith("BTC")
        is_eth = g["symbol"].str.startswith("ETH")

        # 1) BTC dominance by turnover (fallback to volume)
        val_col = "turnover" if "turnover" in g.columns and g["turnover"].notna().any() else "volume"
        total_val = g.groupby("timestamp")[val_col].transform("sum")
        btc_val = g[val_col].where(is_btc, 0.0).groupby(g["timestamp"]).transform("sum")
        dom = btc_val / (total_val + 1e-10)
        g["btc_dom"] = dom.to_numpy()
        dom_uniq = dom.groupby(ts).first()
        g["btc_dom_z"] = _rolling_zscore(dom_uniq, 60).reindex(ts).to_numpy()

        # 2) BTC 20-bar return + symbol relative strength
        btc_close = g["close"].where(is_btc)
        btc_close_uniq = btc_close.groupby(ts).first()
        btc_ret20 = btc_close_uniq.pct_change(20)
        g["btc_ret_20"] = btc_ret20.reindex(ts).to_numpy()
        sym_ret20 = g.groupby("symbol")["close"].transform(lambda s: s.pct_change(20))
        g["rel_btc_20"] = (sym_ret20 - btc_ret20.reindex(ts).to_numpy()).to_numpy()

        # 3) Market breadth: fraction of symbols above their 20-bar SMA
        sma20 = g.groupby("symbol")["close"].transform(lambda s: s.rolling(20).mean())
        above = (g["close"] > sma20).astype(float)
        breadth = above.groupby(ts).transform("mean")
        g["market_breadth"] = breadth.to_numpy()
        g["breadth_z"] = _rolling_zscore(breadth.groupby(ts).first(), 60).reindex(ts).to_numpy()

        # 4) ETH/BTC relative risk tilt
        eth_close = g["close"].where(is_eth)
        eth_uniq = eth_close.groupby(ts).first()
        eb = eth_uniq / (btc_close_uniq + 1e-10)
        g["eth_btc_z"] = _rolling_zscore(eb, 60).reindex(ts).to_numpy()

        parts.append(g)

    if not parts:
        return df
    return pd.concat(parts, ignore_index=True)


# ─── Cross-sectional strength / rotation — rank in universe per timestamp ───
def add_cross_sectional(df: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional factors: each symbol's percentile rank in the universe.

    Ranks rolling point-in-time stats (returns, momentum, vol, OI flow,
    turnover flow) across all symbols at the same timestamp, so a factor of 1
    means "strongest in universe", 0 = weakest. Captures rotation (which coins
    are being bid) as opposed to single-symbol absolute strength.

    Factors:
      - xsec_ret_rank_20:  percentile rank of 20-bar return
      - xsec_ret_rank_60:  percentile rank of 60-bar return
      - xsec_mom_rank:     rank of (12-bar − 40-bar) return = momentum accel
      - xsec_vol_rank:     rank of 20-bar volatility (low = stable)
      - xsec_oi_rank:      rank of 5-bar OI change (capital inflow per coin)
      - xsec_flow_rank:    rank of 5-bar turnover change (flow rotation)
      - xsec_rank_chg_20:  how far the 20-bar rank moved over last 20 bars
      - xsec_dispersion:   cross-sectional std of 20-bar returns (regime)
    """
    if "symbol" not in df.columns or "timeframe" not in df.columns:
        return df

    parts = []
    for tf, g in df.groupby("timeframe"):
        g = g.sort_values("timestamp")
        ts = g["timestamp"]

        ret20 = g.groupby("symbol")["close"].transform(lambda s: s.pct_change(20))
        ret60 = g.groupby("symbol")["close"].transform(lambda s: s.pct_change(60))
        ret12 = g.groupby("symbol")["close"].transform(lambda s: s.pct_change(12))
        ret40 = g.groupby("symbol")["close"].transform(lambda s: s.pct_change(40))
        vol20 = g.groupby("symbol")["close"].transform(lambda s: s.pct_change().rolling(20).std())

        # percentile rank of each stat across symbols at the same timestamp
        g["xsec_ret_rank_20"] = ret20.groupby(ts).rank(pct=True)
        g["xsec_ret_rank_60"] = ret60.groupby(ts).rank(pct=True)
        g["xsec_mom_rank"] = (ret12 - ret40).groupby(ts).rank(pct=True)
        g["xsec_vol_rank"] = vol20.groupby(ts).rank(pct=True)

        if "open_interest" in g.columns and g["open_interest"].notna().any():
            oi_chg = g.groupby("symbol")["open_interest"].transform(lambda s: s.pct_change(5))
            g["xsec_oi_rank"] = oi_chg.groupby(ts).rank(pct=True)
        else:
            g["xsec_oi_rank"] = np.nan

        flow_col = "turnover" if "turnover" in g.columns and g["turnover"].notna().any() else None
        if flow_col:
            t_chg = g.groupby("symbol")[flow_col].transform(lambda s: s.pct_change(5))
            g["xsec_flow_rank"] = t_chg.groupby(ts).rank(pct=True)
        else:
            g["xsec_flow_rank"] = np.nan

        # rank momentum: how far the rank moved over 20 bars
        g["xsec_rank_chg_20"] = g.groupby("symbol")["xsec_ret_rank_20"].transform(
            lambda s: s - s.shift(20)
        )

        # dispersion regime: cross-sectional std of 20-bar returns
        disp = ret20.groupby(ts).std()
        g["xsec_dispersion"] = disp.reindex(ts).to_numpy()

        parts.append(g)

    if not parts:
        return df
    return pd.concat(parts, ignore_index=True)
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
    add_beheading,
    add_magic_line,
    add_fvg,
    add_orderflow,
    add_oi_state,
    add_cross_sectional,
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

    # Cross-symbol macro factors (must run after per-symbol features)
    df = add_cross_symbol(df)
    # Cross-sectional rank factors (same constraint — universe-wide at a timestamp)
    df = add_cross_sectional(df)

    global FACTOR_COLUMNS
    if not FACTOR_COLUMNS:
        exclude = {"timestamp", "symbol", "timeframe", "open", "high", "low", "close", "volume",
                    "turnover", "trades", "taker_buy_vol", "taker_buy_amt",
                    "label_long", "label_short", "label_mid", "label_multiclass", "fwd_ret"}
        FACTOR_COLUMNS = [c for c in df.columns if c not in exclude
                          and "fwd_ret" not in c
                          and df[c].dtype in ("float64", "float32", "int64")]
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
