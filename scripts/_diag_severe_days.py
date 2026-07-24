#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnose expo=0 / market_severe days and fund history span."""
from pathlib import Path
import json
import pandas as pd

from market_env_gate import build_env_asof, fetch_all_index_klines

kpath = Path("data/kline_cache/kline_all.parquet")
if not kpath.exists():
    kpath = Path("kline_all.parquet")
kdf = pd.read_parquet(kpath)
kdf["date"] = kdf["date"].astype(str).str[:10]
sym = kdf["symbol"].astype(str)
mask = sym.str.endswith("600519") | (sym == "600519")
dates = sorted(d for d in kdf.loc[mask, "date"].unique() if "2024-01-01" <= d <= "2026-07-17")
print("n_dates", len(dates), "first", dates[0] if dates else None, "last", dates[-1] if dates else None)

index_hist = fetch_all_index_klines(lmt=500)
severe = []
for d in dates:
    env = build_env_asof(index_hist, d)
    expo = float(env.get("position_exposure", 1))
    flags = env.get("flags") or {}
    if expo <= 0 or flags.get("market_severe"):
        severe.append((d, expo, {k: v for k, v in flags.items() if v}))
print("severe_days", len(severe))
for x in severe:
    print(x[0], "expo", x[1], x[2])

fund = json.load(open("data/fund_flow_history.json", encoding="utf-8"))
sample = next(iter(fund.values()))
keys = sorted(sample.keys()) if isinstance(sample, dict) else []
print("fund_n_stocks", len(fund), "sample_days", len(keys), keys[:2], keys[-2:] if keys else None)
