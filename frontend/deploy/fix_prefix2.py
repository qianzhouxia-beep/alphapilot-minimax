#!/usr/bin/env python3
"""Fix: strip existing sh/sz/bj prefix in get_kline_sina"""
import re

with open("/home/ubuntu/alphapilot/data_fetcher.py", "r") as f:
    src = f.read()

old = """clean = symbol[2:] if symbol[:2].lower() in ("sh", "sz") else symbol"""
new = """clean = symbol[2:] if symbol[:2].lower() in ("sh", "sz", "bj") else symbol"""

if old in src:
    src = src.replace(old, new, 1)
    with open("/home/ubuntu/alphapilot/data_fetcher.py", "w") as f:
        f.write(src)
    print("✅ Added bj prefix support")
else:
    print("⚠ Could not find old line")
    # locate it
    for i, line in enumerate(src.split("\n")):
        if "clean = symbol[2:]" in line:
            print(f"  L{i+1}: {line}")
