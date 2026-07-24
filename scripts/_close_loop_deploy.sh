#!/bin/bash
set -e
cd /home/ubuntu/alphapilot
mkdir -p output/logs
python3 scripts/migrate_paper_protocol.py
bash scripts/install_tradable_loop_cron.sh
python3 -u scripts/audit_paper_tradable.py
# restart API if systemd/supervisor present
if systemctl is-active --quiet alphapilot-api 2>/dev/null; then
  sudo systemctl restart alphapilot-api
  echo restarted alphapilot-api
elif pgrep -af 'uvicorn.*api_server' >/dev/null; then
  pkill -f 'uvicorn.*api_server' || true
  sleep 1
  nohup python3 -m uvicorn api_server:app --host 0.0.0.0 --port 8000 >> output/logs/api_server.log 2>&1 &
  echo restarted uvicorn pid=$!
else
  echo 'WARN: api process not found; restart manually'
fi
echo '=== strategies ==='
python3 - <<'PY'
import json
from pathlib import Path
pt=json.loads(Path('data/paper_trading.json').read_text(encoding='utf-8'))
print('expo', pt.get('position_exposure'), 'protocol', pt.get('protocol'))
for s in pt.get('strategies',[]):
    print(s.get('id'), s.get('name'), 'pos', len(s.get('positions') or []))
PY
echo '=== cron loop lines ==='
crontab -l | grep -E 'audit_paper|oos_tradable|09:36|14:45|14:50' || true
