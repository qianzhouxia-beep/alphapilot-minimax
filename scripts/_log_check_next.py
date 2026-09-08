# -*- coding: utf-8 -*-
"""查 08-26/08-27/08-28 早盘窗口 各 vwap_broken 候选是否被卖出 (一次性)"""
import re

def scan(date, targets):
    LOG = r"D:\国金QMT交易端模拟\userdata\log\XtClient_FormulaOutput_%s.log" % date
    try:
        lines = open(LOG, "r", encoding="utf-8", errors="replace").read().splitlines()
    except FileNotFoundError:
        print("MISSING", LOG); return
    pat = re.compile(r"^(\d{2}:\d{2}:\d{2}).*output = (.*)$")
    print("========== %s ==========" % date)
    for s in lines:
        s = s.strip()
        if not s: continue
        m = pat.match(s)
        if not m: continue
        t, txt = m.group(1), m.group(2)
        for tg in targets:
            if tg in txt and ("SELL" in txt or "vwap" in txt.lower() or "VWAP" in txt or "t2" in txt or "hold" in txt.lower()):
                print("[%s] %s" % (t, txt[:200]))
                break

# 08-25 信号(002839/300191) -> 08-26 早盘
scan("20260826", ["002839", "300191"])
# 08-26 信号(002292) -> 08-27 早盘
scan("20260827", ["002292"])
# 08-27 信号(300191) -> 08-28 早盘
scan("20260828", ["300191"])
