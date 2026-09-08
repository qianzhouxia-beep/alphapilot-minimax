# -*- coding: utf-8 -*-
"""深挖 QMT 实盘日志：002328 时间线 + 所有非wait结论 + 5m bars 线索 (一次性)"""
import re, collections

f = r"D:\国金证券QMT交易端\userdata\log\XtClient_FormulaOutput_20260831.log"
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

# 1. 002328 全部出现（第一次/最后一次 + 次数）
t2328 = [(t, txt) for t, txt in recs if "002328" in txt]
print("002328 appears:", len(t2328), "first:", t2328[0][0] if t2328 else None,
      "last:", t2328[-1][0] if t2328 else None)

# 002328 最后 5 条
print("\n--- 002328 last 5 ---")
for t, txt in t2328[-5:]:
    print(t, txt[:200].replace("\n", " | "))

# 002328 第一次出现前后 20 条
print("\n--- first 6 ---")
for t, txt in t2328[:6]:
    print(t, txt[:200].replace("\n", " | "))

# 2. 全日志非 WAIT 结论
print("\n--- 非 WAIT 的 P2/SKIP/FUND 输出 (去重) ---")
seen = set()
for t, txt in recs:
    for m in re.finditer(r"\[(BUY|WAIT|SKIP|ST|FUND|LOCK|SWEET|CASH|ROT|SYNC)\] .*", txt):
        s = m.group(0).strip()
        if s.startswith("[WAIT]"):
            continue
        if s in seen: continue
        seen.add(s)
        print(t, s[:160])

# 3. 每个整点 002328 是否还出现
print("\n--- 002328 各时段出现次数 ---")
hourly = collections.Counter(t[11:16] for t, _ in t2328)
for k in sorted(hourly): print("  ", k, hourly[k])

# 4. 找 m5/5m/kline/bar 相关错误
print("\n--- 5m/kline 相关线索 ---")
m5pat = re.compile(r"(no_m5|m5|5m|kline|K线|get_market_data|bars)", re.I)
c = collections.Counter()
for t, txt in recs:
    for m in m5pat.findall(txt):
        c[m] += 1
print(c.most_common(15))
