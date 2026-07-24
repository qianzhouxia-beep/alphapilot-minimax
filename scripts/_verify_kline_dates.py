#!/usr/bin/env python3
from pathlib import Path
import pandas as pd

for p in [Path("data/kline_cache/kline_all.parquet"), Path("kline_all.parquet")]:
    if not p.exists():
        print(p, "MISSING")
        continue
    df = pd.read_parquet(p)
    d = df["date"].astype(str)
    print(p, "max", d.max(), "rows", len(df), "syms", df["symbol"].nunique())
    for day in sorted(d.unique())[-6:]:
        n = int((d == day).sum())
        print(" ", day, n)
print("KLINE_OK")
