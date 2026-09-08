# -*- coding: utf-8 -*-
"""原始查看 08-26 日志 002839/300191 (一次性)"""
import re

LOG = r"D:\国金QMT交易端模拟\userdata\log\XtClient_FormulaOutput_20260826.log"
lines = open(LOG, "r", encoding="utf-8", errors="replace").read().splitlines()
print("total lines:", len(lines))
pat = re.compile(r"^(\d{2}:\d{2}:\d{2}).*output = (.*)$")
cnt = 0
for s in lines:
    s = s.strip()
    if not s: continue
    m = pat.match(s)
    if not m: continue
    t, txt = m.group(1), m.group(2)
    if "002839" in txt or "300191" in txt:
        cnt += 1
        if cnt <= 60:
            print("[%s] %s" % (t, txt[:250]))
print("mentions:", cnt)
