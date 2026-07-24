#!/bin/bash
set -e
cd /home/ubuntu/alphapilot
LOG=output/logs/recommend_finish_$(date +%Y%m%d_%H%M%S).log
exec > >(tee -a "$LOG") 2>&1
echo "LOG=$LOG"
python3 scripts/restore_screener_recommend_remote.py || true
python3 scripts/_smoke_v25.py
python3 -c "import json; print('GC pool', len(json.load(open('output/volume_gc_pool.json'))))"
echo "==== recommend.py ===="
python3 -u recommend.py
echo "==== finish gates ===="
python3 -u scripts/finish_pipeline_from_recommend.py
echo "==== api check ===="
python3 scripts/_check_web_deploy.py
echo "ALL_DONE"
