#!/bin/bash
# Retune EOD cron 14:50 -> 14:45 (leave ~15min before 15:00 close)
set -euo pipefail
python3 - <<'PY'
from pathlib import Path
import subprocess

text = subprocess.check_output(["crontab", "-l"], text=True)
lines = []
for line in text.splitlines():
    if "eod_s2_strategy" in line and not line.strip().startswith("#"):
        # 50 14 * * 1-5 ... -> 45 14 * * 1-5 ...
        parts = line.split(None, 5)
        if len(parts) >= 6 and parts[0] == "50" and parts[1] == "14":
            parts[0] = "45"
            line = " ".join(parts)
        lines.append(line)
    elif "14:50 - 尾盘" in line or ("尾盘狙击" in line and line.strip().startswith("#") and "14:50" in line):
        lines.append("# 14:45 - 尾盘狙击（S2规则引擎 → Top1 → 模拟交易；距收盘约15分钟）")
    elif "09:30-14:50" in line and line.strip().startswith("#"):
        lines.append("# 09:30-14:50 每10分钟止盈止损巡检（--sell-only；≥14:45 才 T+2 强制）")
    else:
        lines.append(line)

Path("/tmp/crontab_eod1445").write_text("\n".join(lines) + "\n", encoding="utf-8")
subprocess.check_call(["crontab", "/tmp/crontab_eod1445"])
print("OK")
for l in lines:
    if any(x in l for x in ("14:45", "14:50", "eod_s2", "sell-only", "尾盘")):
        print(l)
PY
