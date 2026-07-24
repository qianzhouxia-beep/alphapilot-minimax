#!/bin/bash
# Track B monthly doctor (environment check only)
set -euo pipefail
cd /home/ubuntu/alphapilot
mkdir -p output/logs
export PYTHONPATH=/home/ubuntu/alphapilot
exec python3 -u rd_workshop/track_b_rdagent_self_dev.py --doctor \
  >> output/logs/rd_track_b_doctor.log 2>&1
