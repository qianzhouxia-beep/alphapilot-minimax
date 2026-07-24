#!/bin/bash
set -euo pipefail
cd /home/ubuntu/alphapilot

# kill only matching uvicorn, not this script
pids=$(pgrep -f '/usr/bin/python3 -m uvicorn api_server:app' || true)
if [ -n "${pids:-}" ]; then
  echo "killing: $pids"
  kill $pids || true
  sleep 2
fi

# ensure import works
python3 -c 'import api_server; print("import ok", api_server.__file__)'

nohup python3 -m uvicorn api_server:app --host 0.0.0.0 --port 8000 >> api_server.log 2>&1 &
echo "started $!"
sleep 3
ss -lntp | grep 8000 || netstat -lntp 2>/dev/null | grep 8000 || true
curl -sS -m 10 "http://127.0.0.1:8000/api/recommend?limit=1" | head -c 800
echo
