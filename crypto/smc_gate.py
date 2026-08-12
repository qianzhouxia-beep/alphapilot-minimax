"""SMC direction gate — "trend first" filter (SMC Layer ①).

Implements the Smart Money Concepts "direction" layer from the strategy doc:
  - Trend must be read FIRST (multi-timeframe structural alignment)
  - Only entries WITH the trend are allowed
  - No static per-symbol direction labels — the gate is dynamic, computed
    from the current price structure on each bar.

Trend = Higher-Time-Frame structural alignment:
  1. Daily (1d) bias      — EMA20/EMA50 ordering + price above/below
  2. 4h structure         — swing high/low (BOS) + EMA ordering on 4h
  3. 2h confirmation      — price vs EMA20 on 2h + momentum (ROC)

Direction is decided per-symbol per-bar; long signals only pass when the
gate says UPTREND, short signals only when it says DOWNTREND.  In a chop
regime (no clear alignment) the gate blocks entries entirely — "no trade
is a position".

Backtest hook: `trend_state(df_cache, sym, asof_ts)` returns ("up"|"down"|"chop")
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ─── EMA helpers ───
def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()


def _swing_points(high: pd.Series, low: pd.Series, left: int = 2, right: int = 2):
    """Return (swing_highs, swing_lows) boolean masks over the series window."""
    n = len(high)
    sh = np.zeros(n, dtype=bool)
    sl = np.zeros(n, dtype=bool)
    for i in range(left, n - right):
        if high.iloc[i] == high.iloc[i - left:i + right + 1].max():
            sh[i] = True
        if low.iloc[i] == low.iloc[i - left:i + right + 1].min():
            sl[i] = True
    return sh, sl


def _bos_trend(high: pd.Series, low: pd.Series, close: pd.Series, lookback: int = 10) -> float:
    """Return trend score in [-1, 1] from structural BOS (break of structure).

    +1 = strong uptrend (higher highs + higher lows), -1 = strong downtrend.
    Chop ≈ 0 (fractal highs/lows mixed, no net break).
    """
    n = len(close)
    if n < lookback + 2:
        return 0.0
    sub_h = high.iloc[-lookback:]
    sub_l = low.iloc[-lookback:]
    sub_c = close.iloc[-lookback:]

    sh, sl = _swing_points(sub_h, sub_l, left=1, right=1)
    hh = 0  # higher highs
    ll = 0  # lower lows
    last_h = None
    last_l = None
    for i in range(len(sub_h)):
        if sh[i]:
            if last_h is not None and sub_h.iloc[i] > last_h:
                hh += 1
            last_h = sub_h.iloc[i]
        if sl[i]:
            if last_l is not None and sub_l.iloc[i] < last_l:
                ll += 1
            last_l = sub_l.iloc[i]

    # price vs the last structural points
    px = float(sub_c.iloc[-1])
    up_strength = 0.0
    dn_strength = 0.0
    if last_h is not None and px > last_h:
        up_strength += 1.0
    if last_l is not None and px < last_l:
        dn_strength += 1.0
    if last_l is not None and px > last_l:
        up_strength += 0.5
    if last_h is not None and px < last_h:
        dn_strength += 0.5

    score = (hh - ll) / max(1, (hh + ll)) + up_strength - dn_strength
    # normalize to [-1, 1]
    return float(np.clip(score / 4.0, -1.0, 1.0))


def _tf_trend(g: pd.DataFrame) -> tuple[str, float]:
    """Trend of a single timeframe series -> ("up"|"down"|"chop", score)."""
    close = g["close"]
    high = g["high"]
    low = g["low"]
    if len(close) < 30:
        return "chop", 0.0

    ema20 = _ema(close, 20)
    ema50 = _ema(close, 50)
    px = float(close.iloc[-1])
    e20 = float(ema20.iloc[-1])
    e50 = float(ema50.iloc[-1])

    # Momentum (ROC over 20 bars)
    roc20 = px / float(close.iloc[-21]) - 1 if len(close) > 21 else 0.0

    score = 0.0
    score += 1.0 if px > e20 else -1.0
    score += 1.0 if e20 > e50 else -1.0
    score += 1.0 if px > e50 else -1.0
    score += np.clip(roc20 * 40, -1.0, 1.0)

    bos = _bos_trend(high, low, close)
    score += bos * 2.0

    if score >= 2.0:
        return "up", score
    if score <= -2.0:
        return "down", score
    return "chop", score


def trend_state(df_cache: pd.DataFrame, sym: str, asof_ts, grouped: dict | None = None) -> tuple[str, float, dict]:
    """SMC Layer ①: multi-timeframe trend direction for one symbol.

    Returns (direction, score, breakdown):
      direction: "up" | "down" | "chop"
      score:     signed strength (roughly -5..+5)
      breakdown: {tf: ("up"|"down"|"chop", score)} per timeframe

    `grouped` (optional) is {tf: {sym: DataFrame}} to avoid re-slicing.
    """
    if grouped is None:
        sym_df = df_cache[df_cache["symbol"] == sym]
        if sym_df.empty:
            return "chop", 0.0, {}
    else:
        sym_df = None

    breakdown = {}
    score_total = 0.0
    weights = {"1d": 1.5, "4h": 1.2, "2h": 1.0}
    for tf, w in weights.items():
        if grouped is not None:
            g = grouped.get(tf, {}).get(sym)
            if g is None or g.empty:
                continue
            g = g.copy()
        else:
            g = sym_df[sym_df["timeframe"] == tf]
            if g.empty:
                continue
        if asof_ts is not None:
            g = g[g["timestamp"] <= asof_ts]
        if g.empty:
            continue
        g = g.sort_values("timestamp")
        if len(g) < 30:
            continue
        d, s = _tf_trend(g)
        breakdown[tf] = (d, round(float(s), 3))
        score_total += s * w

    if not breakdown:
        return "chop", 0.0, breakdown

    # Weighted alignment decides the gate
    if score_total >= 2.0:
        return "up", round(score_total, 3), breakdown
    if score_total <= -2.0:
        return "down", round(score_total, 3), breakdown
    return "chop", round(score_total, 3), breakdown


def direction_allowed(direction: str, trend: str) -> bool:
    """Whether an entry direction passes the SMC gate."""
    if trend == "chop":
        return False
    if direction == "long":
        return trend == "up"
    if direction == "short":
        return trend == "down"
    return False


def is_counter_trend(direction: str, trend: str) -> bool:
    """True when the entry fights the prevailing HTF trend."""
    if trend == "chop":
        return False
    if direction == "long":
        return trend == "down"
    if direction == "short":
        return trend == "up"
    return False


def counter_trend_min_signal() -> float:
    """Higher entry floor for counter-trend trades (selective gate).

    Backtest evidence: low-signal counter-trend entries are the leak
    (50-55 band win rate 54.7%), while high-signal counter-trend trades
    (70+) keep 77.6% win rate. So we block the weak ones, keep the strong.
    """
    try:
        from crypto import config as C
        return float(getattr(C, "SMC_COUNTER_TREND_MIN_SIGNAL", 0.50))
    except Exception:
        return 0.50


def chop_min_signal() -> float:
    """Minimum signal floor for entries allowed in a chop (no-trend) regime.

    Aug-12 tune: allowing chop entries when the signal is strong (~0.55)
    raised recent trade count +33% while win rate rose 63.5%→65.2%.
    """
    try:
        from crypto import config as C
        return float(getattr(C, "SMC_CHOP_MIN_SIGNAL", 0.50))
    except Exception:
        return 0.50


def explain(breakdown: dict) -> str:
    parts = []
    for tf in ("1d", "4h", "2h"):
        if tf in breakdown:
            d, s = breakdown[tf]
            parts.append(f"{tf}:{d}({s:+.1f})")
    return " ".join(parts) if parts else "no-data"
