#!/usr/bin/env python3
"""Idempotent: point 09:25 cron at pre_market_gate.py."""
import subprocess
from pathlib import Path

NEW_LINE = (
    "25 9 * * 1-5 cd /home/ubuntu/alphapilot && "
    "python3 -u pre_market_gate.py >> output/logs/pre_market_gate.log 2>&1"
)
COMMENT = "# 09:25 - 集合竞价资金门控（开盘前Top100重排序）"

raw = subprocess.check_output(["crontab", "-l"], text=True, stderr=subprocess.DEVNULL)
lines = raw.splitlines()
out = []
replaced = False
for line in lines:
    # replace existing 09:25 pre_market_gate line
    if "25 9" in line and "pre_market_gate.py" in line:
        if not replaced:
            out.append(COMMENT)
            out.append(NEW_LINE)
            replaced = True
        continue
    out.append(line)

if not replaced:
    # insert before 09:35 line
    final = []
    inserted = False
    for line in out:
        if (not inserted) and "35 9" in line and "morning_live_fund_select" in line:
            final.append(COMMENT)
            final.append(NEW_LINE)
            inserted = True
        final.append(line)
    out = final
    replaced = inserted

text = "\n".join(out) + "\n"
Path("/tmp/crontab_pre_market").write_text(text, encoding="utf-8")
subprocess.check_call(["crontab", "/tmp/crontab_pre_market"])
print("cron updated, replaced=", replaced)
subprocess.check_call(["bash", "-lc", "crontab -l | grep -E '09:25|25 9'"])
