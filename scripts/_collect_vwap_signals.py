# -*- coding: utf-8 -*-
"""收集 B轨 QMT模拟 08-19后 所有 vwap_broken 信号 (一次性)"""
import re, os, json

LOG_DIR = r"D:\国金QMT交易端模拟\userdata\log"
DATES = ["20260820", "20260821", "20260824", "20260825", "20260826",
         "20260827", "20260828", "20260831"]

# 收集 vwap_broken 信号: (date, symbol, px, vwap, ret)
signals = []
# 同时收集: 当天是否 SELL (该符号当天有 t2_force / t2_force_after_extend / hard_stop / vwap_weak_early 等)
for d in DATES:
    f = os.path.join(LOG_DIR, "XtClient_FormulaOutput_{}.log".format(d))
    if not os.path.exists(f):
        print("MISSING", d); continue
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
        for m in re.finditer(r"\[VWAP\] (\d{6}\.S[ZH]) day-vwap broken px=([\d.]+) vwap=([\d.]+) ret=([-\d.]+)%", txt):
            signals.append({"date": d, "symbol": m.group(1), "px": float(m.group(2)),
                            "vwap": float(m.group(3)), "ret": float(m.group(4))})

print("vwap_broken signals:", len(signals))
for s in signals:
    print(" ", s)
json.dump(signals, open(r"C:\Users\elvisq\Projects\alphapilot\scripts\_vwap_signals.json", "w"), ensure_ascii=False, indent=1)
