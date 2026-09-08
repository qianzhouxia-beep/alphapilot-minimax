# -*- coding: utf-8 -*-
"""查 000700 在 QMT 模拟端何时买入 (一次性)"""
import re, os

for date in ["20260825", "20260826", "20260827"]:
    f = r"D:\国金QMT交易端模拟\userdata\log\XtClient_FormulaOutput_{}.log".format(date)
    if not os.path.exists(f):
        continue
    lines = open(f, "r", encoding="utf-8", errors="replace").read().splitlines()
    pat = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*output = (.*)$")
    recs = []
    for s in lines:
        s = s.strip()
        if not s: continue
        m = pat.match(s)
        if m:
            recs.append([m.group(1), m.group(2)])
        elif recs:
            recs[-1][1] += "\n" + s
    for t, txt in recs:
        if "000700" in txt and ("BUY" in txt or "SYNC" in txt or "INIT" in txt):
            print(date, t, txt[:260].replace("\n", " | "))
