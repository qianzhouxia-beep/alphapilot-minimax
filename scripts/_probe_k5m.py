# -*- coding: utf-8 -*-
"""探查 A 股 5 分钟 K 线数据覆盖范围 (在服务器跑)"""
import pandas as pd
import os

BASE = "/home/ubuntu/alphapilot/data/kline5m"
codes = ["000001", "600519", "300750", "000906", "002466"]

for code in codes:
    p = os.path.join(BASE, code + ".parquet")
    if not os.path.exists(p):
        print(code, "MISSING")
        continue
    df = pd.read_parquet(p)
    print("=" * 60)
    print(code, "shape:", df.shape)
    print("  cols:", list(df.columns))
    print("  dtypes:", dict(df.dtypes.astype(str)))
    row0 = df.iloc[0]
    row1 = df.iloc[-1]
    print("  first:", row0.to_dict())
    print("  last:", row1.to_dict())

# 抽查样本：遍历前 50 个文件看时间范围分布
import glob
files = sorted(glob.glob(os.path.join(BASE, "*.parquet")))[:50]
mins, maxs = [], []
for p in files:
    try:
        df = pd.read_parquet(p)
        mins.append(df.iloc[0])
        maxs.append(df.iloc[-1])
    except Exception:
        pass
print("=" * 60)
print("sample first dates:", [str(m.get("datetime") or m.get("time") or m.get("dt"))[:19] for m in mins][:5], "...")
print("sample last dates :", [str(m.get("datetime") or m.get("time") or m.get("dt"))[:19] for m in maxs][:5], "...")
