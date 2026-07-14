#!/usr/bin/env python3
"""kc_debug.py - k线列名诊断"""
import akshare as ak
import json

symbol = "sh600000"
print(f">>> stock_zh_a_daily(symbol='{symbol}', adjust='qfq')")
df = ak.stock_zh_a_daily(symbol=symbol, adjust="qfq")
cols = list(df.columns)
print(f"列名: {cols}")
print(f"行数: {len(df)}")
print(f"第一行: {df.iloc[0].to_dict()}")
print(f"'date' in cols: {'date' in cols}")

symbol = "600000"
print(f">>> stock_zh_a_daily(symbol='{symbol}', adjust='qfq')")
try:
    df2 = ak.stock_zh_a_daily(symbol=symbol, adjust="qfq")
    print(f"列名: {list(df2.columns)}")
except Exception as e:
    print(f"FAIL: {e}")
