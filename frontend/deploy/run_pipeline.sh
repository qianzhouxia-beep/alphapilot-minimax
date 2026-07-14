#!/bin/bash
echo "=== 启动全量管线 ==="
cd ~/alphapilot

# Kill any leftover pipeline run
pkill -f "pipeline_run\|run_daily_recommend" 2>/dev/null || true
sleep 1

# Clean old cache
rm -f recommend_cache.json output/daily_recommend.json

# Full pipeline scan (5527 stocks, ~0.3s each ≈ 30 min)
nohup python3 -c "
from recommend import run_daily_recommend
import json
r = run_daily_recommend(top_n=20)
print('✅ DONE:', len(r.get('recommendations',[])), 'recommendations')
with open('recommend_cache.json','w') as f:
    json.dump(r, f, ensure_ascii=False, default=str)
print('✅ CACHE saved: recommend_cache.json')
" > pipeline_run.log 2>&1 &

echo "PID=$!"
echo "Log: tail -f pipeline_run.log"
