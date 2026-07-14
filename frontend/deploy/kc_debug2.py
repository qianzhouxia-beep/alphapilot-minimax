#!/usr/bin/env python3
"""kc_debug2.py - 诊断无前缀的k线返回"""
import akshare as ak

symbol = "600000"
print(f">>> stock_zh_a_daily(symbol='{symbol}', adjust='qfq')")
try:
    df = ak.stock_zh_a_daily(symbol=symbol, adjust="qfq")
    print(f"type: {type(df)}")
    print(f"列名: {list(df.columns)}")
    print(f"shape: {df.shape}")
    print(f"dtypes:\n{df.dtypes}")
except Exception as e:
    print(f"FAIL: type={type(e).__name__}: {e}")
    # 看有没有返回df但摸不着date列的情况
    if "date" in str(e):
        import traceback
        traceback.print_exc()
