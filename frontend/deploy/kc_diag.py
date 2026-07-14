#!/usr/bin/env python3
"""kc_diag.py — 诊断 K线接口"""
import akshare as ak
import pandas as pd

print("=== AKShare version ===")
from akshare import __version__
print(f"akshare v{__version__}")

print("\n=== Test 1: stock_zh_a_daily(sh600000) ===")
try:
    df = ak.stock_zh_a_daily(symbol="sh600000", adjust="qfq")
    print(f"OK 列数={len(df.columns)} 行数={len(df)}")
    print("列名:", list(df.columns))
    print(df.head(2).to_dict("records"))
except Exception as e:
    print(f"FAIL: {e}")

print("\n=== Test 2: stock_zh_a_hist(600000) ===")
try:
    df = ak.stock_zh_a_hist(symbol="600000", period="daily", adjust="qfq")
    print(f"OK 列数={len(df.columns)} 行数={len(df)}")
    print("列名:", list(df.columns))
except Exception as e:
    print(f"FAIL: {e}")

print("\n=== Test 3: cache_json ===")
cache_path = "/home/ubuntu/alphapilot/output/daily_recommend.json"
with open(cache_path) as f:
    c = __import__("json").load(f)
if isinstance(c, dict):
    print(f"type=dict keys={list(c.keys())}")
    items = c.get("recommendations") or c.get("items") or []
    print("推荐条数:", len(items))
elif isinstance(c, list):
    print(f"type=list len={len(c)}")
    if c: print("first key:", list(c[0].keys()))
else:
    print(f"type={type(c).__name__}")
