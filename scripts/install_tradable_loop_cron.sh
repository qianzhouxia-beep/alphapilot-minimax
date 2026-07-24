#!/bin/bash
# Install daily paper audit + weekly OOS into crontab (idempotent).
set -euo pipefail
ROOT=/home/ubuntu/alphapilot
TMP=$(mktemp)
crontab -l 2>/dev/null | grep -v 'audit_paper_tradable' | grep -v 'run_oos_tradable_top2' > "$TMP" || true

cat >> "$TMP" <<'EOF'
# 16:10 - 模拟盘可交易协议日复盘（信号→成交→T+2）
10 16 * * 1-5 cd /home/ubuntu/alphapilot && python3 -u scripts/audit_paper_tradable.py >> output/logs/paper_audit.log 2>&1
# 周六 10:00 - Top2 样本外验收（trained_at 之后；不足 40 日标 INSUFFICIENT）
0 10 * * 6 cd /home/ubuntu/alphapilot && python3 -u scripts/run_oos_tradable_top2.py >> output/logs/oos_tradable_top2.log 2>&1
EOF

crontab "$TMP"
rm -f "$TMP"
echo "=== tradable loop cron ==="
crontab -l | grep -E 'audit_paper|oos_tradable|09:36|14:45|14:50|VM2|模拟'
