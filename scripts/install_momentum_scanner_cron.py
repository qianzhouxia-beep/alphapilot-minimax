#!/usr/bin/env python3
"""Replace 09:35 live_rerank with live_momentum_scanner.

保留 pre_market_gate（09:25:55）：竞价快照由 09:35 扫描一并纳入。
"""
import subprocess
from pathlib import Path

raw = subprocess.check_output(["crontab", "-l"], text=True, stderr=subprocess.DEVNULL)
lines = raw.splitlines()

# Remove old crons（勿删 pre_market_gate）
REMOVE_PATTERNS = [
    "live_rerank",           # replaced by live_momentum_scanner
    "morning_live_fund",    # replaced by chained version inside scanner cron
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
    "# 09:35 - 全市场终选（ICIR+资金动量+竞价+隔夜轻确认）→ Top2",
    (
        "35 9 * * 1-5 cd /home/ubuntu/alphapilot && "
        "set -a; [ -f /home/ubuntu/alphapilot/config/opening_scheme.env ] && "
        ". /home/ubuntu/alphapilot/config/opening_scheme.env; set +a; "
        "python3 -u live_momentum_scanner.py >> output/logs/live_momentum_scanner.log 2>&1 && "
        "MORNING_RANK_MODE=model python3 -u morning_live_fund_select.py >> output/logs/l2_refresh.log 2>&1"
    ),
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
