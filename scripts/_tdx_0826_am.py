# -*- coding: utf-8 -*-
"""查 TDX A 08-26 09:45-10:00 所有 SELL 日志 (一次性)"""
import re

LOG = r"C:\alphapilot\tdx_full_chain.log"
pat = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
for ln in open(LOG, encoding="utf-8", errors="replace"):
    m = pat.match(ln)
    if not m:
        continue
    d = m.group(1)
    if "2026-08-26 09:40" <= d <= "2026-08-26 10:05" and ("SELL" in ln or "VWAP" in ln or "EXT" in ln or "rotation" in ln or "peel" in ln):
        print(" ".join(ln.split())[:220])
