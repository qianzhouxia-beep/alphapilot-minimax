#!/usr/bin/env bash
# Install Wind intraday precision crons (board + B′ stocks). Idempotent.
set -euo pipefail
python3 - <<'PY'
import subprocess
from pathlib import Path

try:
    raw = subprocess.check_output(["crontab", "-l"], text=True, stderr=subprocess.DEVNULL)
except Exception:
    raw = ""

keep = []
for ln in raw.splitlines():
    if "fetch_wind_board_flow" in ln:
        continue
    if "refresh_wind_intraday" in ln:
        continue
    # 本脚本管理的个股 B′ 行（日志或 session 标记）
    if "enrich_candidates_wind" in ln and (
        "wind_intraday" in ln
        or "--session premarket" in ln
        or "--session open" in ln
        or "--session midday" in ln
        or "--session pre_eod" in ln
    ):
        continue
    keep.append(ln)

# 04:30 盘前 B′ 预热（供 05:00 主流程）
keep.append(
    "30 4 * * 1-5 cd /home/ubuntu/alphapilot && /usr/bin/python3 -u scripts/enrich_candidates_wind.py --limit 80 --session premarket --sleep 0.3 >> output/logs/wind_intraday.log 2>&1"
)
# 09:35 开盘后 B′（供早盘下单 / trade_precheck）
keep.append(
    "35 9 * * 1-5 cd /home/ubuntu/alphapilot && /usr/bin/python3 -u scripts/enrich_candidates_wind.py --limit 80 --session open --sleep 0.3 >> output/logs/wind_intraday.log 2>&1"
)
# 午盘：板块+个股
keep.append(
    "35 11 * * 1-5 cd /home/ubuntu/alphapilot && /usr/bin/python3 -u scripts/refresh_wind_intraday.py --session midday --stock-limit 80 >> output/logs/wind_intraday.log 2>&1"
)
# 尾盘前：板块+个股（供 14:45 狙击）
keep.append(
    "25 14 * * 1-5 cd /home/ubuntu/alphapilot && /usr/bin/python3 -u scripts/refresh_wind_intraday.py --session pre_eod --stock-limit 80 >> output/logs/wind_intraday.log 2>&1"
)
# 收盘：板块主快照（写 history）
keep.append(
    "10 15 * * 1-5 cd /home/ubuntu/alphapilot && /usr/bin/python3 -u scripts/fetch_wind_board_flow.py --session close >> output/logs/wind_board_flow.log 2>&1"
)

Path("/tmp/cron_wind_intraday").write_text("\n".join(keep) + "\n", encoding="utf-8")
subprocess.check_call(["crontab", "/tmp/cron_wind_intraday"])
print("=== wind intraday cron ===")
out = subprocess.check_output(["crontab", "-l"], text=True)
for ln in out.splitlines():
    if "wind" in ln.lower() or "intraday" in ln or "enrich_candidates_wind" in ln:
        print(ln)
PY
