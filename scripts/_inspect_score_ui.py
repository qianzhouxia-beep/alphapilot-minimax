#!/usr/bin/env python3
from pathlib import Path

p = Path("/home/ubuntu/alphapilot/frontend_out/_next/static/chunks/app/cn/page-2b0d1a18fc1b768a.js")
t = p.read_text(encoding="utf-8", errors="ignore")
for s in ["score_pct", "displayScore", "45+75", "V18", "VM2", "V3", "信心", "模型概率"]:
    print(s, t.find(s))
i = t.find("score_pct")
print("ctx", repr(t[max(0, i - 60) : i + 100]) if i >= 0 else None)
i2 = t.find("45+")
print("map", repr(t[max(0, i2 - 30) : i2 + 50]) if i2 >= 0 else None)
