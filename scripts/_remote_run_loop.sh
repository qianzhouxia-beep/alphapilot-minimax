#!/bin/bash
set -e
cd /home/ubuntu/alphapilot
mkdir -p output/logs
python3 -u scripts/audit_paper_tradable.py
echo "==== OOS+REF starting ===="
nohup python3 -u scripts/run_oos_tradable_top2.py > output/logs/oos_tradable_top2.log 2>&1 &
echo "OOS_PID=$!"
sleep 3
tail -n 30 output/logs/oos_tradable_top2.log || true
