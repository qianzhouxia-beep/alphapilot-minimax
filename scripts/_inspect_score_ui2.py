#!/usr/bin/env python3
from pathlib import Path
import re

p = Path("/home/ubuntu/alphapilot/frontend_out/_next/static/chunks/app/cn/page-2b0d1a18fc1b768a.js")
t = p.read_text(encoding="utf-8", errors="ignore")
for m in re.finditer(r".{0,40}score_pct.{0,60}", t):
    print("PCT:", m.group(0)[:120])
    print("---")
for m in re.finditer(r".{0,30}\.score\).{0,50}", t):
    s = m.group(0)
    if "toFixed" in s or "*100" in s or "信心" in s:
        print("SCORE:", s[:140])
        print("---")
# find 评分 header nearby
i = t.find("评分")
print("评分 ctx", repr(t[i - 20 : i + 80]) if i >= 0 else None)
