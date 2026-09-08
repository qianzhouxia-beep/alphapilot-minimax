# -*- coding: utf-8 -*-
"""查 TDX A 08-26 早盘 601919/000938/002747 的处理 (一次性)"""
import re

LOG = r"C:\alphapilot\tdx_full_chain.log"
targets = {"601919": "08-25 broken ret=86.5%", "603209": "08-25 broken ret=-1.8%",
           "000938": "08-26 broken", "002747": "08-26 broken",
           "002980": "08-28 broken", "000938b": "08-28 broken"}
# 只扫 08-26~08-28 区间
pat = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
for code in ["601919", "603209"]:
    print("==== %s ====" % code)
    cnt = 0
    for ln in open(LOG, encoding="utf-8", errors="replace"):
        if code not in ln:
            continue
        m = pat.match(ln)
        if not m:
            continue
        d = m.group(1)
        if d >= "2026-08-25" and d <= "2026-08-27" and ("SELL" in ln or "VWAP" in ln or "SYNC" in ln or "EXT" in ln or "peel" in ln or "rotation" in ln or "t2" in ln):
            print(" ", d[11:], ln.strip().split("output = ")[-1][:160])
            cnt += 1
            if cnt > 40:
                break
