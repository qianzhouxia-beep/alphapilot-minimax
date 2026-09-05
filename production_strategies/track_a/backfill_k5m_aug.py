# -*- coding: utf-8 -*-
"""Backfill missing 5m kline for August symbols via mootdx (freq=0 = 5m).
Writes parquet into D:/alphapilot/data/kline5m_full_backfill/{sym}.parquet
in the same schema as bt_dyn_confirm_long.load_k5m expects:
  date, time, datetime, open, high, low, close, amount, volume
"""
import os
import sys
import time
import warnings

warnings.filterwarnings("ignore")

import pandas as pd

OUT_DIR = r"D:\alphapilot\data\kline5m_full_backfill"

# TDX frequency 0 = 5-minute
FREQ = 0


def _bare(sym):
    return str(sym).split(".")[0]


def fetch_all_5m(client, code):
    """Fetch as many 5m bars as available (paged, 800 per page)."""
    all_rows = []
    start = 0
    for _ in range(40):  # 40 pages * 800 = 32000 bars max (~660 days)
        try:
            bars = client.bars(symbol=code, frequency=FREQ, start=start,
                               offset=800)
        except Exception:
            break
        if bars is None or len(bars) == 0:
            break
        all_rows.append(bars)
        if len(bars) < 800:
            break
        start += 800
    if not all_rows:
        return None
    return pd.concat(all_rows, ignore_index=True)


def normalize(df):
    """Map mootdx columns to bt_dyn_confirm_long schema."""
    df = df.copy()
    df["datetime"] = pd.to_datetime(df["datetime"])
    out = pd.DataFrame({
        "date": df["datetime"].dt.strftime("%Y-%m-%d"),
        "time": df["datetime"].dt.strftime("%H:%M"),
        "datetime": df["datetime"],
        "open": df["open"].astype(float),
        "high": df["high"].astype(float),
        "low": df["low"].astype(float),
        "close": df["close"].astype(float),
        "amount": df["amount"].astype(float),
        "volume": df["volume"].astype(float)
        if "volume" in df.columns else df["vol"].astype(float),
    })
    out = out.sort_values("datetime").reset_index(drop=True)
    out = out.drop_duplicates(subset=["datetime"]).reset_index(drop=True)
    return out


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    from mootdx.quotes import Quotes
    client = Quotes.factory(market="std", multithread=True)

    syms = [s for s in sys.argv[1:] if s] or ["600519"]
    t0 = time.time()
    for i, code in enumerate(syms):
        out = os.path.join(OUT_DIR, f"{_bare(code)}.parquet")
        if os.path.exists(out):
            print(f"  skip {code} (exists)", flush=True)
            continue
        df = fetch_all_5m(client, code)
        if df is None or len(df) == 0:
            print(f"  FAIL {code}", flush=True)
            continue
        n = normalize(df)
        n.to_parquet(out)
        days = n["date"].nunique()
        rng = f"{n['date'].iloc[0]}~{n['date'].iloc[-1]}"
        print(f"  {code}: {len(n)} bars / {days} days ({rng}) "
              f"{time.time()-t0:.0f}s", flush=True)
    print(f"done in {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
