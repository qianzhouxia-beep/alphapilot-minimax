#!/usr/bin/env python3
"""测试前缀修复"""
from data_fetcher import get_kline_sina

for sym in ["600218", "sh600218", "000001", "sz000001"]:
    df = get_kline_sina(sym, "20250701")
    ok = not df.empty and "date" in df.columns and len(df) >= 5
    print(f"{sym}: {'✅' if ok else '❌'} {len(df)} rows" if ok else f"{sym}: ❌ EMPTY")
