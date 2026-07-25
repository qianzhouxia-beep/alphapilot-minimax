#!/usr/bin/env python3
"""Idempotent: install intraday sector watch + board flow refresh crons."""
import subprocess
from pathlib import Path

# lines to insert
LINES = [
    ("# 10:00 - 盘中板块资金巡检（akshare免费源）", None),
    ("00 10 * * 1-5 cd /home/ubuntu/alphapilot && python3 -u intraday_sector_watch.py >> output/logs/sector_watch.log 2>&1", "10:00.*sector_watch"),
    ("# 10:00 - 盘中刷新板块资金流（Wind consult视图）", None),
    ("00 10 * * 1-5 cd /home/ubuntu/alphapilot && /usr/bin/python3 -u scripts/fetch_wind_board_flow.py --session open >> output/logs/wind_board_flow.log 2>&1", "10:00.*fetch_wind_board_flow"),
    ("# 11:00 - 盘中板块资金巡检", None),
    ("00 11 * * 1-5 cd /home/ubuntu/alphapilot && python3 -u intraday_sector_watch.py >> output/logs/sector_watch.log 2>&1", "11:00.*sector_watch"),
    ("# 13:30 - 下午盘板块资金巡检", None),
    ("30 13 * * 1-5 cd /home/ubuntu/alphapilot && python3 -u intraday_sector_watch.py >> output/logs/sector_watch.log 2>&1", "13:30.*sector_watch"),
    ("# 14:30 - 尾盘板块资金巡检（供14:45 E2收盘确认用）", None),
    ("30 14 * * 1-5 cd /home/ubuntu/alphapilot && python3 -u intraday_sector_watch.py >> output/logs/sector_watch.log 2>&1", "14:30.*sector_watch"),
]

raw = subprocess.check_output(["crontab", "-l"], text=True, stderr=subprocess.DEVNULL)
existing_lines = raw.splitlines()

# Remove any existing matching lines
cleaned = []
for line in existing_lines:
    skip = False
    for _, pattern in LINES:
        if pattern and pattern in line:
            skip = True
            break
    if not skip:
        cleaned.append(line)

# Insert new lines before first market-hours cron (09:25 or later)
insert_before = None
for i, line in enumerate(cleaned):
    if " 9 " in line or ":09" in line or " 09" in line:
        insert_before = i
        break

final = []
inserted_comment = False
for i, line in enumerate(cleaned):
    if i == insert_before and not inserted_comment:
        final.append("# ═══ 盘中板块资金巡检（akshare免费源）═══")
        for text, _ in LINES:
            final.append(text)
        inserted_comment = True
    final.append(line)

if not inserted_comment:
    final.append("")
    final.append("# ═══ 盘中板块资金巡检（akshare免费源）═══")
    for text, _ in LINES:
        final.append(text)

text = "\n".join(final) + "\n"
Path("/tmp/crontab_sector_watch").write_text(text, encoding="utf-8")
subprocess.check_call(["crontab", "/tmp/crontab_sector_watch"])
print("cron updated, inserted=", inserted_comment)
subprocess.check_call(["bash", "-lc", "crontab -l | grep -E 'sector_watch|board_flow|10:00|11:00|13:30|14:30'"])
