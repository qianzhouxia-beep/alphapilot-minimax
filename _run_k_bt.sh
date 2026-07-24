#!/bin/bash
set -e
cd /home/ubuntu/alphapilot
mkdir -p logs output
pkill -f 'backtest_k_location_gate.py' 2>/dev/null || true
sleep 2
nohup python3 -u backtest_k_location_gate.py --start 2026-04-01 --end 2026-07-17 --top-n 2 --require-pattern 0 --workers 8 > logs/k_location_bt.log 2>&1 &
echo "PID=$!"
sleep 30
grep -E '^  \[|universe|precompute|RESULTS|A0_|K1_|K2_|wrote|Error|Traceback' logs/k_location_bt.log | head -50
ps -p $! >/dev/null && echo STILL_RUNNING || echo FINISHED
