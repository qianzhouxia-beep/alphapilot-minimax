# -*- coding: utf-8 -*-
"""搜 BUY 相关输出 (08-28 vs 08-31) (一次性)"""
import re

for f in [r"D:\国金证券QMT交易端\userdata\log\XtClient_FormulaOutput_20260828.log",
          r"D:\国金证券QMT交易端\userdata\log\XtClient_FormulaOutput_20260831.log"]:
    print("="*30, f.split("_")[-1])
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
    hit = 0
    for t, txt in recs:
        if "BUY" in txt or "passorder" in txt or "order" in txt.lower():
            print(t, txt[:250].replace("\n", " | "))
            hit += 1
            if hit >= 25: break
    if not hit:
        print("  no BUY/order lines")
