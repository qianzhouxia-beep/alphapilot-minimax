#!/usr/bin/env python3
"""Idempotent: point 09:35 cron at scripts/live_rerank.py."""
import subprocess
from pathlib import Path

NEW_LINE = (
    "35 9 * * 1-5 cd /home/ubuntu/alphapilot && "
    "python3 -u scripts/live_rerank.py >> output/logs/live_rerank.log 2>&1"
)
COMMENT = "# 09:35 - 开盘重排门（实时4档资金重排序候选池）"

raw = subprocess.check_output(["crontab", "-l"], text=True, stderr=subprocess.DEVNULL)
lines = raw.splitlines()

# Remove old rerank lines that point to non-existent scripts
out = []
for line in lines:
    if "live_rerank.py" in line:
        continue  # will be re-added
    out.append(line)

# Insert before 09:36 paper_trading_signals
final = []
inserted = False
for line in out:
    if (not inserted) and "36 9" in line and "paper_trading_signals" in line:
        final.append(COMMENT)
        final.append(NEW_LINE)
        inserted = True
    final.append(line)

text = "\n".join(final) + "\n"
Path("/tmp/crontab_live_rerank").write_text(text, encoding="utf-8")
subprocess.check_call(["crontab", "/tmp/crontab_live_rerank"])
print("cron updated, inserted=", inserted)
subprocess.check_call(["bash", "-lc", "crontab -l | grep -E 'live_rerank|25 9|35 9|36 9'"])
