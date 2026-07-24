#!/usr/bin/env python3
import subprocess
from pathlib import Path

line = (
    "50 4 * * 1-5 cd /home/ubuntu/alphapilot && "
    "python3 -u scripts/data_readiness_gate.py --fail >> output/logs/data_readiness.log 2>&1"
)
raw = subprocess.check_output(["crontab", "-l"], text=True)
if "data_readiness_gate.py" in raw:
    print("cron already present")
else:
    text = raw.rstrip() + "\n# 04:50 - 落盘数据新鲜度闸门\n" + line + "\n"
    Path("/tmp/crontab_ready").write_text(text, encoding="utf-8")
    subprocess.check_call(["crontab", "/tmp/crontab_ready"])
    print("cron installed")
print(subprocess.check_output(["crontab", "-l"], text=True))
