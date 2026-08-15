"""Data fetcher — Binance perpetual via ccxt."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import SYMBOLS, TIMEFRAMES, DATA_DIR, HISTORY_PATH

# ─── ccxt lazy init ───
_binance: Any = None


def _exchange() -> Any:
    global _binance
    if _binance is None:
        import ccxt

        config = {
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},  # perpetual swap
        }
        # Auto-detect proxy from env (Clash/V2Ray local proxy)
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or ""
        if not proxy:
            proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or ""
        if proxy:
            config["proxies"] = {"http": proxy, "https": proxy}
            print(f"  [proxy] using {proxy}", flush=True)
        _binance = ccxt.binance(config)
    return _binance


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ─── Fetch OHLCV ───
_KLINE_FIELDS = [
    "timestamp", "open", "high", "low", "close", "volume",
    "close_time", "turnover", "trades", "taker_buy_vol", "taker_buy_amt", "_ignore",
]


def fetch_klines(
    symbol: str,
    timeframe: str = "4h",
    limit: int = 500,
    since: str | None = None,
) -> pd.DataFrame:
    """Fetch klines from Binance, including taker-buy volume for order-flow (CVD) factors.

    Returns columns: timestamp, open, high, low, close, volume,
    turnover, trades, taker_buy_vol, taker_buy_amt.
    Uses the raw fapi REST endpoint (12 fields) instead of ccxt's 6-column
    fetch_ohlcv so aggressive-buy volume is not dropped.
    """
    ex = _exchange()
    market_id = symbol.replace("/", "").replace(":USDT", "").replace(":USDC", "").replace(":USD", "")
    params = {"symbol": market_id, "interval": timeframe, "limit": min(limit, 1500)}
    if since:
        params["startTime"] = ex.parse8601(since)
    raw = ex.fapiPublicGetKlines(params)
    df = pd.DataFrame(raw, columns=_KLINE_FIELDS)
    for c in ["timestamp", "close_time"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    for c in ["open", "high", "low", "close", "volume", "turnover", "taker_buy_vol", "taker_buy_amt"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["trades"] = pd.to_numeric(df["trades"], errors="coerce")
    df = df.drop(columns=["close_time", "_ignore"])
    df = df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)
    return df


# ─── Fetch funding rate ───
def fetch_funding_rate(symbol: str, limit: int = 500) -> pd.DataFrame:
    """Fetch historical funding rate. Binance caps at ~900 entries; paginate for more."""
    ex = _exchange()
    all_raw = []
    since = None
    remaining = limit
    while remaining > 0:
        batch = min(remaining, 500)
        raw = ex.fetch_funding_rate_history(symbol, limit=batch, params={"startTime": since} if since else {})
        if not raw:
            break
        all_raw.extend(raw)
        since = raw[-1]["timestamp"]
        remaining -= batch
        if len(raw) < batch:
            break
        time.sleep(0.3)
    if not all_raw:
        return pd.DataFrame()
    df = pd.DataFrame(all_raw)
    df["timestamp"] = pd.to_datetime(
        [r.get("info", {}).get("fundingTime", r.get("timestamp")) for r in all_raw],
        unit="ms",
        utc=True,
    )
    df["funding_rate"] = df["fundingRate"].astype(float)
    return df[["timestamp", "funding_rate"]].drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)


# ─── Fetch open interest ───
def fetch_open_interest(symbol: str, limit: int = 500) -> pd.DataFrame:
    """Fetch historical open interest."""
    ex = _exchange()
    raw = ex.fetch_open_interest_history(symbol, timeframe="1h", limit=limit)
    if not raw:
        return pd.DataFrame()
    df = pd.DataFrame(raw)
    # ccxt standard fields: symbol, timestamp, openInterest (optional openInterestValue, baseVolume, quoteVolume)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    if "openInterest" in df.columns:
        df["open_interest"] = df["openInterest"].astype(float)
    elif "info" in df.columns:
        # fallback: parse from raw binance info dict
        import json as _json
        df["open_interest"] = df["info"].apply(
            lambda x: float(x.get("sumOpenInterest", x.get("openInterest", 0))) if isinstance(x, dict) else 0
        )
    else:
        df["open_interest"] = 0.0
    if "openInterestValue" in df.columns:
        df["oi_value"] = df["openInterestValue"].astype(float)
    elif "quoteVolume" in df.columns:
        df["oi_value"] = df["quoteVolume"].astype(float)
    else:
        df["oi_value"] = df["open_interest"]
    cols = ["timestamp", "open_interest", "oi_value"]
    return df[cols].drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)


# ─── Build & cache full feature+label dataset ───
def build_dataset(
    symbols: list[str] | None = None,
    timeframes: list[str] | None = None,
    limit: int = 500,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Fetch all data, merge, and cache as parquet."""
    if HISTORY_PATH.exists() and not force_refresh:
        log(f"Loading cached dataset: {HISTORY_PATH}")
        return pd.read_parquet(HISTORY_PATH)

    symbols = symbols or SYMBOLS
    timeframes = timeframes or TIMEFRAMES

    all_dfs = []
    base_sym = SYMBOLS[0]  # fetch klines for first symbol as base

    for sym in symbols:
        for tf in timeframes:
            log(f"Fetching {sym} {tf}...")
            df = fetch_klines(sym, timeframe=tf, limit=limit)
            if df.empty:
                continue
            df["symbol"] = sym
            df["timeframe"] = tf
            all_dfs.append(df)
            time.sleep(0.5)  # rate limit

    if not all_dfs:
        raise ValueError("No data fetched")

    # Merge funding + OI to 1h candles (aligned by nearest hour)
    log("Fetching funding rates...")
    fr_all = []
    for sym in symbols:
        fr = fetch_funding_rate(sym, limit=min(limit, 500))
        if not fr.empty:
            fr["symbol"] = sym
            fr_all.append(fr)
        time.sleep(0.5)
    fr_df = pd.concat(fr_all, ignore_index=True) if fr_all else pd.DataFrame()

    log("Fetching open interest...")
    oi_all = []
    for sym in symbols:
        oi = fetch_open_interest(sym, limit=min(limit, 500))
        if not oi.empty:
            oi["symbol"] = sym
            oi_all.append(oi)
        time.sleep(0.5)
    oi_df = pd.concat(oi_all, ignore_index=True) if oi_all else pd.DataFrame()

    full = pd.concat(all_dfs, ignore_index=True).sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    log(f"Raw: {len(full)} rows")

    # Merge funding & OI to klines (asof merge on timestamp)
    if not fr_df.empty:
        fr_df["timestamp"] = fr_df["timestamp"].dt.floor("1h")
        full = full.merge(
            fr_df.groupby(["symbol", "timestamp"], as_index=False)["funding_rate"].mean(),
            on=["symbol", "timestamp"],
            how="left",
        )
    else:
        full["funding_rate"] = np.nan

    if not oi_df.empty:
        oi_df["timestamp"] = oi_df["timestamp"].dt.floor("1h")
        oi_df = oi_df.rename(columns={"oi_value": "oi_value_usdt"})
        full = full.merge(
            oi_df.groupby(["symbol", "timestamp"], as_index=False)[["open_interest", "oi_value_usdt"]].mean(),
            on=["symbol", "timestamp"],
            how="left",
        )
    else:
        full["open_interest"] = np.nan
        full["oi_value_usdt"] = np.nan

    # Forward-fill funding rate within each symbol+tf
    full = full.sort_values(["symbol", "timeframe", "timestamp"])
    grp_cols = ["symbol", "timeframe"]
    full["funding_rate"] = full.groupby(grp_cols)["funding_rate"].ffill()
    full["open_interest"] = full.groupby(grp_cols)["open_interest"].ffill()
    full["oi_value_usdt"] = full.groupby(grp_cols)["oi_value_usdt"].ffill()

    log(f"Merged: {len(full)} rows, {full['symbol'].nunique()} symbols, {full['timeframe'].nunique()} timeframes")
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    full.to_parquet(HISTORY_PATH, index=False)
    log(f"Saved: {HISTORY_PATH}")
    return full


def refresh_dataset() -> pd.DataFrame:
    """Force refresh from exchange."""
    return build_dataset(force_refresh=True)


if __name__ == "__main__":
    df = build_dataset()
    print(f"\nColumns: {list(df.columns)}")
    print(f"Date range: {df['timestamp'].min()} → {df['timestamp'].max()}")
    print(df.tail(5).to_string())
