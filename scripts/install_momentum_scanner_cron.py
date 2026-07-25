#!/usr/bin/env python3
"""Replace 09:35 live_rerank with live_momentum_scanner + remove pre_market_gate."""
import subprocess
from pathlib import Path

raw = subprocess.check_output(["crontab", "-l"], text=True, stderr=subprocess.DEVNULL)
lines = raw.splitlines()

# Remove old crons
REMOVE_PATTERNS = [
    "live_rerank",           # replaced by live_momentum_scanner
    "pre_market_gate",       # replaced by full scan at 09:35
    "morning_live_fund",     # replaced by chained version inside scanner cron
]

new_lines = []
for line in lines:
    skip = False
    for p in REMOVE_PATTERNS:
        if p in line:
            print(f"  removing: {line.strip()}")
            skip = True
            break
    if not skip:
        new_lines.append(line)

# Insert new 09:35 cron after 09:25 section or at appropriate place
NEW_CRONS = [
    "# 09:35 - 全市场动量扫描（ICIR+实时资金流双轨评分 → 全覆盖5000只）→ 资金选Top2",
    "35 9 * * 1-5 cd /home/ubuntu/alphapilot && python3 -u live_momentum_scanner.py >> output/logs/live_momentum_scanner.log 2>&1 && MORNING_RANK_MODE=fund python3 -u morning_live_fund_select.py >> output/logs/l2_refresh.log 2>&1",
]

insert_before = None
for i, line in enumerate(new_lines):
    if "09:35" in line and "morning_live" in line:
        insert_before = i + 1
        break

if insert_before is None:
    new_lines.append("")
    for c in NEW_CRONS:
        new_lines.append(c)
else:
    for c in reversed(NEW_CRONS):
        new_lines.insert(insert_before, c)

text = "\n".join(new_lines) + "\n"
Path("/tmp/crontab_momentum").write_text(text, encoding="utf-8")
subprocess.check_call(["crontab", "/tmp/crontab_momentum"])
print("\n=== Updated crontab ===")
subprocess.check_call(["bash", "-lc", "crontab -l | grep -E '09:35|live_momentum|live_rerank|pre_market'"])

from pathlib import Path
