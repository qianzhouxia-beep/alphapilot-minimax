#!/bin/bash
tail -8 /home/ubuntu/alphapilot/backtest_v3_top3_t1.log
if [ -f /home/ubuntu/alphapilot/output/v3_top3_t1_backtest.json ]; then
  python3 - <<'PY'
import json
d=json.load(open('/home/ubuntu/alphapilot/output/v3_top3_t1_backtest.json',encoding='utf-8'))
print('DONE')
for k in d.get('kpi',[]):
    print(k)
PY
else
  echo RUNNING
  pgrep -af 'backtest_v3_top3_t1' || true
fi
