#!/usr/bin/env bash
# Install Wind board-flow fetch cron (consult track). Idempotent.
set -euo pipefail
ROOT="${ALPHAPILOT_ROOT:-/home/ubuntu/alphapilot}"
mkdir -p "$ROOT/output/logs"
chmod +x "$ROOT/scripts/fetch_wind_board_flow.py" 2>/dev/null || true

python3 - <<'PY'
import subprocess
from pathlib import Path
root = Path("/home/ubuntu/alphapilot")
try:
    raw = subprocess.check_output(["crontab", "-l"], text=True, stderr=subprocess.DEVNULL)
except Exception:
    raw = ""
lines = [ln for ln in raw.splitlines() if "fetch_wind_board_flow" not in ln]
lines.append(
    "35 11 * * 1-5 cd /home/ubuntu/alphapilot && /usr/bin/python3 -u scripts/fetch_wind_board_flow.py --session midday >> output/logs/wind_board_flow.log 2>&1"
)
lines.append(
    "10 15 * * 1-5 cd /home/ubuntu/alphapilot && /usr/bin/python3 -u scripts/fetch_wind_board_flow.py --session close >> output/logs/wind_board_flow.log 2>&1"
)
Path("/tmp/cron_wind_board").write_text("\n".join(lines) + "\n", encoding="utf-8")
subprocess.check_call(["crontab", "/tmp/cron_wind_board"])
print("=== wind board flow cron ===")
out = subprocess.check_output(["crontab", "-l"], text=True)
for ln in out.splitlines():
    if "fetch_wind_board_flow" in ln:
        print(ln)
PY

echo "Note: afternoon sector_research_report should run after 15:10 so Wind section is fresh."
