# -*- coding: utf-8 -*-
"""查 08-27 早盘 002292 / 002839 08-26 卖出详情 (一次性)"""
import re

# 08-26 002839 closed 的上下文 (找卖出价格)
LOG = r"D:\国金QMT交易端模拟\userdata\log\XtClient_FormulaOutput_20260826.log"
lines = open(LOG, encoding="utf-8", errors="replace").read().splitlines()
print("=== 08-26 09:30-09:40 002839 上下文 ===")
for s in lines:
    if "output = " in s and ("002839" in s):
        m = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*output = (.*)$", s)
        t = m.group(1)[11:16] if m else "?"
        if "09:30" <= t <= "09:40":
            print("[%s] %s" % (t, m.group(2)[:200]))

print()
print("=== 08-27 002292 ===")
LOG2 = r"D:\国金QMT交易端模拟\userdata\log\XtClient_FormulaOutput_20260827.log"
lines2 = open(LOG2, encoding="utf-8", errors="replace").read().splitlines()
for s in lines2:
    if "output = " in s and "002292" in s:
        m = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*output = (.*)$", s)
        if m:
            print("[%s] %s" % (m.group(1)[11:], m.group(2)[:200]))
