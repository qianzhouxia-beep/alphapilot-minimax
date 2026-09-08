# -*- coding: utf-8 -*-
"""确认 000700/002292/003032 的 vwap_broken 何时置位 (一次性)"""
import re, os

for date in ["20260828", "20260827", "20260826"]:
    f = r"D:\国金QMT交易端模拟\userdata\log\XtClient_FormulaOutput_{}.log".format(date)
    if not os.path.exists(f):
        print("MISSING", date); continue
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
    print("\n" + "="*20, date, "records:", len(recs))
    for t, txt in recs:
        if "VWAP" in txt or ("000700" in txt and "SELL" in txt) or ("002292" in txt and "SELL" in txt) or ("003032" in txt and "SELL" in txt):
            print(" ", t, txt[:220].replace("\n", " | "))
