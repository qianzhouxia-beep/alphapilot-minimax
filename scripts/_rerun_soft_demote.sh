#!/bin/bash
set -e
cd /home/ubuntu/alphapilot
export PYTHONPATH=.
echo "=== files ==="
ls -la market_env_gate.py permission_gate.py output/volume_gc_pool.json output/daily_recommend.json 2>&1 | head -20
python3 - <<'PY'
import json
from pathlib import Path
p=Path('output/daily_recommend.json')
d=json.loads(p.read_text(encoding='utf-8'))
print('recommend_n', len(d.get('recommendations') or []), 'expo', d.get('position_exposure'), 'mode', d.get('exposure_mode'))
gc=Path('output/volume_gc_pool.json')
if gc.exists():
    print('gc_pool', len(json.loads(gc.read_text(encoding='utf-8'))))
PY
echo "=== re-run recommend + finish funnel (soft_demote + soft_dual) ==="
python3 -u recommend.py
python3 -u scripts/finish_pipeline_from_recommend.py
python3 - <<'PY'
import json
d=json.load(open('output/daily_recommend.json',encoding='utf-8'))
recs=d.get('recommendations') or []
print('FINAL expo', d.get('position_exposure'), 'mode', d.get('exposure_mode'), 'n', len(recs), 'top_n', d.get('recommend_top_n'))
for r in recs[:5]:
    print(
        ' ', r.get('symbol'), r.get('name'), r.get('score'),
        'ind', r.get('industry_l1'),
        'mkt_d', r.get('market_env_delta'),
        'sec', r.get('sector_gate'), r.get('sector_gate_delta'),
        str(r.get('sector_gate_reason') or r.get('market_env_reason') or '')[:50],
    )
PY
