# -*- coding: utf-8 -*-
"""搜 08-25/08-26 日志中 002839/300191 SELL 记录 (一次性)"""
import re

def search(date, kw):
    LOG = r"D:\国金QMT交易端模拟\userdata\log\XtClient_FormulaOutput_%s.log" % date
    lines = open(LOG, encoding="utf-8", errors="replace").read().splitlines()
    hits = 0
    for s in lines:
        if "output = " in s and kw in s:
            # 提取时间 + output内容
            m = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*output = (.*)$", s)
            if m:
                hits += 1
                print("[%s] %s" % (m.group(1)[11:], m.group(2)[:220]))
    print("== %s %s hits=%d ==" % (date, kw, hits))
    print()

search("20260825", "002839")
print("--- 08-26 002839 ---")
search("20260826", "002839")
print("--- 08-26 300191 ---")
search("20260826", "300191")
