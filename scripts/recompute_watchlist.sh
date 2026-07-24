#!/bin/bash
set -e
cd /home/ubuntu/alphapilot
python3 -u -c 'from watchlist import recompute_tracking; import json; print(json.dumps(recompute_tracking(force=True), ensure_ascii=False, indent=2))'
