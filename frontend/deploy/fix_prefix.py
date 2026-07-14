#!/usr/bin/env python3
"""Fix: strip existing sh/sz prefix in get_kline_sina before re-adding"""
import re

with open("/home/ubuntu/alphapilot/data_fetcher.py", "r") as f:
    src = f.read()

old = """    try:
        # AKShare 1.18+ 在部分服务器需要 sh/sz 前缀
        prefix = "sh" if symbol.startswith("6") or symbol.startswith("9") else "sz"
        df = ak.stock_zh_a_daily(symbol=f"{prefix}{symbol}", start_date=start_date, adjust="qfq")"""

new = """    try:
        # AKShare 1.18+ 在部分服务器需要 sh/sz 前缀
        # 先去掉已有前缀避免双重前缀
        clean = symbol[2:] if symbol[:2].lower() in ("sh", "sz") else symbol
        prefix = "sh" if clean.startswith("6") or clean.startswith("9") else "sz"
        df = ak.stock_zh_a_daily(symbol=f"{prefix}{clean}", start_date=start_date, adjust="qfq")"""

if old in src:
    src = src.replace(old, new, 1)
    with open("/home/ubuntu/alphapilot/data_fetcher.py", "w") as f:
        f.write(src)
    print("✅ Fixed get_kline_sina: strip existing prefix before re-adding")
else:
    print("⚠ Could not find old code block in data_fetcher.py")
    print("Checking actual content around get_kline_sina...")
    lines = src.split("\n")
    for i, line in enumerate(lines):
        if "AKShare 1.18" in line:
            for j in range(max(0,i-2), min(len(lines), i+5)):
                print(f"  L{j+1}: {lines[j]}")
