#!/bin/bash
set -e
cd /home/ubuntu/alphapilot
pkill -f 'uvicorn api_server:app' || true
sleep 2
nohup python3 -m uvicorn api_server:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn_ap.log 2>&1 &
sleep 3
python3 <<'PY'
from sector_dashboard import build_dashboard
for p in ['today','5day','10day','20day','60day']:
  d=build_dashboard(period=p)
  top=[(x['name'], x['net_yi']) for x in d['today_top10'][:3]]
  print(p, 'net', d['summary']['net_yi'], 'n', d['summary']['industry_count'], 'top', top, 'asof', d['meta'].get('asof'))
print('provider', build_dashboard()['provider'])
import urllib.request
print(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/cn/sectors?period=5day', timeout=30).read()[:200])
PY
