#!/bin/bash
set -e
cd /home/ubuntu/alphapilot
mkdir -p output/logs
LOG="output/logs/pipeline_v3_rerun_$(date +%Y%m%d_%H%M%S).log"
export ENABLE_WEAK_ROTATION_SLEEVE=1
export WEAK_TRADE_ON_COLLAPSE=0
echo "LOG=$LOG"
echo "START $(date '+%Y-%m-%d %H:%M:%S')"
nohup python3 -u alphapilot_pipeline_v3.py > "$LOG" 2>&1 &
echo "PID=$!"
echo "$LOG" > output/logs/pipeline_v3_rerun_latest.path
sleep 2
head -n 20 "$LOG" || true
