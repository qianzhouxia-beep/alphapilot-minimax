#!/usr/bin/env python3
"""Idempotent: point 09:35 cron at morning_live_fund_select.py."""
import subprocess
from pathlib import Path

OLD = "live_fund_flow.py"
NEW_LINE = (
    "35 9 * * 1-5 cd /home/ubuntu/alphapilot && "
    "python3 -u morning_live_fund_select.py >> output/logs/l2_refresh.log 2>&1"
)
COMMENT = "# 09:35 - 盘中实时资金对池子重跑资金门 → 流入 Top2"

raw = subprocess.check_output(["crontab", "-l"], text=True, stderr=subprocess.DEVNULL)
lines = raw.splitlines()
out = []
replaced = False
skip_next_old = False
for i, line in enumerate(lines):
    if "09:35" in line and "L2" in line and line.strip().startswith("#"):
        out.append(COMMENT)
        continue
    if "35 9" in line and OLD in line:
        out.append(NEW_LINE)
        replaced = True
        continue
    if "35 9" in line and "morning_live_fund_select.py" in line:
        out.append(NEW_LINE)
        replaced = True
        continue
    out.append(line)

if not replaced:
    # insert before 09:36 line
    final = []
    inserted = False
    for line in out:
        if (not inserted) and "36 9" in line and "paper_trading_signals" in line:
            final.append(COMMENT)
            final.append(NEW_LINE)
            inserted = True
        final.append(line)
    out = final
    replaced = inserted

text = "\n".join(out) + "\n"
Path("/tmp/crontab_morning_live").write_text(text, encoding="utf-8")
subprocess.check_call(["crontab", "/tmp/crontab_morning_live"])
print("cron updated, replaced=", replaced)
subprocess.check_call(["bash", "-lc", "crontab -l | grep -E '09:35|09:36|35 9|36 9'"])
