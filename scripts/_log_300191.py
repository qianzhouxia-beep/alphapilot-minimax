# -*- coding: utf-8 -*-
"""查 08-31 模拟盘日志 300191 相关记录 (一次性)"""
import re

LOG = r"D:\国金QMT交易端模拟\userdata\log\XtClient_FormulaOutput_20260831.log"
lines = open(LOG, "r", encoding="utf-8", errors="replace").read().splitlines()
pat = re.compile(r"^(\d{2}:\d{2}:\d{2}).*output = (.*)$")
n300 = 0
for s in lines:
    s = s.strip()
    if not s: continue
    m = pat.match(s)
    if not m: continue
    t, txt = m.group(1), m.group(2)
    if "300191" in txt:
        n300 += 1
        print("[%s] %s" % (t, txt[:220]))
print("--- 300191 mentions:", n300)
