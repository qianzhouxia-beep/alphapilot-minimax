#!/bin/bash
set -e
cd /home/ubuntu/alphapilot
echo "=== scripts ==="
head -n 60 cache_kline.py
echo "==== v2 ===="
head -n 120 patch_refresh_kline_v2.py
echo "==== parquet ==="
python3 <<'PY'
import pandas as pd
from pathlib import Path
for p in [Path("data/kline_cache/kline_all.parquet"), Path("kline_all.parquet")]:
    if not p.exists():
        print(p, "MISSING")
        continue
    df = pd.read_parquet(p)
    d = df["date"].astype(str)
    print(p, "cols", list(df.columns))
    print("  min", d.min(), "max", d.max(), "rows", len(df), "syms", df["symbol"].nunique())
PY
