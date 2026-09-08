# -*- coding: utf-8 -*-
"""QMT 实盘今日日志时间线：汇总 P2 结论分布 + 各时段 (一次性)"""
import re, collections

f = r"D:\国金证券QMT交易端\userdata\log\XtClient_FormulaOutput_20260831.log"
lines = []
with open(f, "r", encoding="utf-8", errors="replace") as fh:
    for ln in fh:
        s = ln.strip()
        if not s:
            continue
        lines.append(s)

# 提取时间与输出
pat = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*output = (.*)$")
recs = []  # (time, text)
for s in lines:
    m = pat.match(s)
    if m:
        recs.append((m.group(1), m.group(2)))
    else:
        # 多行输出 continuation
        if recs:
            recs[-1] = (recs[-1][0], recs[-1][1] + "\n" + s)

print("records:", len(recs))
if not recs:
    print("none"); raise SystemExit

t0 = recs[0][0]
print("first:", t0, "last:", recs[-1][0])

# P2 结论统计
p2 = collections.Counter()
buy = []
wait_names = collections.Counter()
for t, txt in recs:
    for m in re.finditer(r"\[(BUY|WAIT)\] (\d{6}\.S[ZH]) P2=(\w+)", txt):
        kind, code, reason = m.group(1), m.group(2), m.group(3)
        p2[(kind, reason)] += 1
        if kind == "WAIT":
            wait_names[code] += 1
        if kind == "BUY":
            buy.append((t, code, reason))

print("P2 distribution:")
for k, v in sorted(p2.items(), key=lambda x: -x[1]):
    print("  ", k, v)
print("wait by code:", wait_names.most_common())

# 各时间段最后一次结论
def hhmm(ts): return ts[11:16]
for hr in ["09:35","09:40","09:45","09:50","10:00","10:15","10:30","10:45","11:00","11:30","13:00","14:00","14:30","14:45"]:
    seen = [ (t, re.findall(r"\[(BUY|WAIT)\] (\d{6}\.S[ZH]) P2=(\w+)", txt)) for t, txt in recs if hhmm(t) >= hr]
    # 找该时段第一批结论
    for t, ms in seen:
        if ms:
            print(hr, "->", t, ms[:6])
            break
