#!/usr/bin/env python3
from pathlib import Path
import subprocess

raw = subprocess.check_output(["crontab", "-l"], text=True)
new = raw.replace(
    "data_readiness_gate.py --fail",
    "data_readiness_gate.py --repair",
)
if new != raw:
    Path("/tmp/cron_ready2").write_text(new, encoding="utf-8")
    subprocess.check_call(["crontab", "/tmp/cron_ready2"])
    print("updated cron to --repair")
else:
    print("cron already --repair or no match")
print([l for l in new.splitlines() if "data_readiness" in l])
