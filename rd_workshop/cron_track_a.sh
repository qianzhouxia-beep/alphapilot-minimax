#!/bin/bash
# Track A weekly: current-model factor uplift → candidate train/OOS (no production writes)
set -euo pipefail
cd /home/ubuntu/alphapilot
mkdir -p output/logs
export PYTHONPATH=/home/ubuntu/alphapilot
export ALPHAPILOT_ROOT=/home/ubuntu/alphapilot
exec python3 -u rd_workshop/track_a_current_model_uplift.py \
  --sample 400 \
  --top-k 10 \
  --promote \
  >> output/logs/rd_track_a.log 2>&1
