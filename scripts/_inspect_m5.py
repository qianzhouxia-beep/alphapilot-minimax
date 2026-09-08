# -*- coding: utf-8 -*-
"""检查 5m 数据格式 (一次性)"""
import json
m5 = json.load(open(r"C:\Users\elvisq\Projects\alphapilot\scripts\_m5_data.json"))
print("symbols:", list(m5.keys()))
for sym6, bars in m5.items():
    print("== ", sym6, "bars:", len(bars))
    if bars:
        print("   first:", bars[0])
        print("   last:", bars[-1])
    break
