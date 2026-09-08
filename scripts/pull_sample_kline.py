#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pull a small sample of A-share kline data for local ICIR analysis."""
import os, sys, pandas as pd
from pathlib import Path

ROOT = Path("C:\\Users\\elvisq\\Projects\\alphapilot")
os.chdir(str(ROOT))

import akshare as ak

# Major liquid stocks + some random small caps
stocks = [
    "000001", "000002", "000333", "000651", "000858", "002415", "002594",
    "300750", "300059", "600519", "600036", "601318", "600887", "600585",
    "601166", "600900", "600309", "601012", "600276", "002714", "000568",
    "002475", "300124", "601899", "600406",
]

rows = []
for sym in stocks:
    try:
        df = ak.stock_zh_a_hist(symbol=sym, period="daily", start_date="20250101", adjust="")
        if df is not None and len(df) > 0:
            rename = {}
            for c in df.columns:
                cl = c.lower()
                if cl in ("日期", "date"): rename[c] = "date"
                elif cl in ("开盘", "open"): rename[c] = "open"
                elif cl in ("收盘", "close"): rename[c] = "close"
                elif cl in ("最高", "high"): rename[c] = "high"
                elif cl in ("最低", "low"): rename[c] = "low"
                elif cl in ("成交量", "volume"): rename[c] = "volume"
                elif cl in ("成交额", "amount"): rename[c] = "amount"
                elif cl in ("换手率", "turnover"): rename[c] = "turnover"
            df = df.rename(columns=rename)
            df = df[["date", "open", "high", "low", "close", "volume", "amount", "turnover"]].copy()
            for c in ["open", "high", "low", "close"]:
                df[c] = df[c].astype(float)
            df["volume"] = df["volume"].astype(float)
            df["amount"] = df["amount"].astype(float)
            df["turnover"] = df["turnover"].fillna(0).astype(float)
            df["symbol"] = sym
            print(f"  {sym}: {len(df)} rows, {df['date'].min()} ~ {df['date'].max()}")
            rows.append(df)
    except Exception as e:
        print(f"  {sym}: SKIP ({e})")

if rows:
    combined = pd.concat(rows, ignore_index=True)
    out_dir = ROOT / "data" / "kline_cache"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "kline_all.parquet"
    combined.to_parquet(out_path, index=False)
    print(f"\nSaved {len(combined)} rows to {out_path}")
    print(f"Stocks: {combined['symbol'].nunique()}, Date range: {combined['date'].min()} ~ {combined['date'].max()}")
else:
    print("ERROR: No data fetched")
    sys.exit(1)