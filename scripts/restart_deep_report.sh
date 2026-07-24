#!/bin/bash
set -e
cd /home/ubuntu/alphapilot
pkill -f 'uvicorn api_server:app' || true
sleep 2
nohup python3 -m uvicorn api_server:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn_ap.log 2>&1 &
sleep 3
pgrep -af 'uvicorn api_server' || { echo "FAIL start"; tail -40 /tmp/uvicorn_ap.log; exit 1; }
echo "=== smoke ==="
curl -s -X POST http://127.0.0.1:8000/api/v1/cn/deep-report \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"000524","engine":"deepseek"}'
echo
