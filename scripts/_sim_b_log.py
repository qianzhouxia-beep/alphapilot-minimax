# -*- coding: utf-8 -*-
"""QMT 模拟端今日日志：B轨卖出 + VWAP broken 时间线 (一次性)"""
import re, collections

f = r"D:\国金QMT交易端模拟\userdata\log\XtClient_FormulaOutput_20260831.log"
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

# INIT 标记: 找 B 轨策略
for t, txt in recs[:30]:
    if "track-B" in txt or "TRACK_B" in txt or "auction" in txt.lower():
        print(t, txt[:300].replace("\n", " | "))

# VWAP broken + SELL 相关
print("\n=== VWAP / SELL / BUY / EXT 输出 ===")
pat2 = re.compile(r"\[(VWAP|SELL|BUY|EXT|BC|ROT|CASH|LOCK)\]")
n = 0
for t, txt in recs:
    for m in pat2.finditer(txt):
        line = m.group(0)
        # 截取该行
        s = txt[max(0, m.start()-40):m.end()+120].replace("\n", " | ")
        print(t, s.strip())
        n += 1
        if n >= 60: break
    if n >= 60: break
