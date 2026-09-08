# -*- coding: utf-8 -*-
"""查 08-25 日志 SYNC 持仓 + 002839 生命周期 (一次性)"""
import re

LOG = r"D:\国金QMT交易端模拟\userdata\log\XtClient_FormulaOutput_20260825.log"
lines = open(LOG, "r", encoding="utf-8", errors="replace").read().splitlines()
pat = re.compile(r"^(\d{2}:\d{2}:\d{2}).*output = (.*)$")
print("=== 08-25 SYNC + VWAP + SELL ===")
for s in lines:
    s = s.strip()
    if not s: continue
    m = pat.match(s)
    if not m: continue
    t, txt = m.group(1), m.group(2)
    if ("SYNC" in txt and ("002839" in txt or "pos_n" in txt)) or "VWAP" in txt or "002839" in txt:
        print("[%s] %s" % (t, txt[:200]))
