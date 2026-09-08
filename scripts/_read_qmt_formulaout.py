# -*- coding: utf-8 -*-
"""读 QMT 实盘 FormulaOutput 日志，找策略打印输出 (一次性)"""
import re, os

p = "D:\\国盛QMT实盘\\userdata\\log\\XtClient_FormulaOutput_20260831.log"
alt = "D:\\国金证券QMT交易端\\userdata\\log\\XtClient_FormulaOutput_20260831.log"
f = p if os.path.exists(p) else alt
print("FILE:", f, os.path.getsize(f))

# FormulaOutput log: 找策略 print 标记
pats = {
    "BUY": r"\[BUY\]",
    "WAIT": r"\[WAIT\]",
    "CAND": r"\[CAND\]",
    "CASH": r"\[CASH\]",
    "SWEET": r"\[SWEET\]",
    "SKIP": r"\[SKIP\]",
    "ST": r"\[ST\]",
    "FUND": r"\[FUND\]",
    "LOCK": r"\[LOCK\]",
    "INIT": r"\[INIT\]",
    "POS": r"\[POS\]",
    "ROT": r"\[ROT\]",
    "SYNC": r"\[SYNC\]",
    "SELL": r"\[SELL\]",
    "FETCH": r"\[FETCH\]",
    "SCORES": r"\[SCORES\]",
    "ABR": r"abr|ABR",
}
counts = {}
lines = []
with open(f, "r", encoding="utf-8", errors="replace") as fh:
    for ln in fh:
        lines.append(ln.rstrip("\n"))

print("total lines:", len(lines))
for name, pat in pats.items():
    c = sum(1 for ln in lines if re.search(pat, ln))
    counts[name] = c
print("counts:", counts)

# 打印带时间戳的 BUY/WAIT/SKIP/FUND/SW EET 行（去重时间）
keep = re.compile(r"\[(BUY|WAIT|SKIP|ST|FUND|LOCK|CASH|SWEET|ROT|SYNC|SELL|INIT|CAND|SCORES)\]|abr")
out = [ln for ln in lines if keep.search(ln)]
print("matched:", len(out))
for ln in out[:250]:
    print(ln[:300])
