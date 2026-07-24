#!/usr/bin/env python3
"""Normalize paper-trading crontab comments to VM2.5 + Top2."""
from pathlib import Path
import subprocess

text = subprocess.check_output(["crontab", "-l"], text=True)
lines = []
for line in text.splitlines():
    if "模拟交易开盘买卖" in line or (
        line.strip().startswith("#") and "09:36" in line and "评分" in line
    ):
        lines.append("# 09:36 - 模拟交易开盘买卖（VM2.5评分+资金流 → Top2）")
    elif line.strip().startswith("#") and "05:00" in line and ("V2.3 选股" in line or "VM2.5 选股" in line):
        lines.append("# 05:00 - 美股因子+隔夜情绪 → VM2.5 选股（完整管线）")
    else:
        lines.append(line)

out = Path("/tmp/crontab_new")
out.write_text("\n".join(lines) + "\n", encoding="utf-8")
subprocess.check_call(["crontab", str(out)])
print("OK")
for l in lines:
    if any(x in l for x in ("09:36", "05:00", "模拟交易", "paper_trading", "VM2", "V2.3")):
        print(l)
