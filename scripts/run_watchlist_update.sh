#!/bin/bash
set -e
cd /home/ubuntu/alphapilot
mkdir -p output/logs
python3 -u -c 'from watchlist import recompute_tracking; import json; print(json.dumps(recompute_tracking(force=True), ensure_ascii=False))'
