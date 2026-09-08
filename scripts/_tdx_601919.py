# -*- coding: utf-8 -*-
"""查 TDX A 08-26 09:50 601919 卖出原因 + 08-25 extend 后状态 (一次性)"""
import re

LOG = r"C:\alphapilot\tdx_full_chain.log"
pat = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
out = []
for ln in open(LOG, encoding="utf-8", errors="replace"):
    if "601919" not in ln:
        continue
    m = pat.match(ln)
    if not m:
        continue
    d = m.group(1)
    if "2026-08-25 14:45" <= d <= "2026-08-26 10:00":
        out.append(" ".join(ln.split())[:220])
for o in out[:50]:
    print(o)
