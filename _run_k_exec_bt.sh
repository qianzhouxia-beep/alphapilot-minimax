#!/bin/bash
set -e
cd /home/ubuntu/alphapilot
mkdir -p logs output
pkill -f 'backtest_k_execution.py' 2>/dev/null || true
sleep 1
nohup python3 -u backtest_k_execution.py --start 2026-04-01 --end 2026-07-17 --top-n 2 > logs/k_execution_bt.log 2>&1 &
echo "PID=$!"
sleep 20
tail -30 logs/k_execution_bt.log
