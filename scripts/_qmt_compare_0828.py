# -*- coding: utf-8 -*-
"""对比 08-28 QMT 实盘 P2 结论 vs 08-31 (一次性)"""
import re, collections, os

def analyze(f):
    print("="*30, os.path.basename(f))
    if not os.path.exists(f):
        print("MISSING"); return
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
    print("records:", len(recs), "first:", recs[0][0] if recs else "-", "last:", recs[-1][0] if recs else "-")
    p2 = collections.Counter()
    buys = []
    for t, txt in recs:
        for m in re.finditer(r"\[(BUY|WAIT)\] (\d{6}\.S[ZH]) P2=(\w+)", txt):
            p2[(m.group(1), m.group(3))] += 1
            if m.group(1) == "BUY":
                buys.append((t, m.group(2), m.group(3)))
    print("P2:", dict(p2))
    print("BUYS:", buys[:10])

analyze(r"D:\国金证券QMT交易端\userdata\log\XtClient_FormulaOutput_20260828.log")
analyze(r"D:\国金证券QMT交易端\userdata\log\XtClient_FormulaOutput_20260830.log")
