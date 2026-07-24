#!/bin/bash
set -e
sudo systemctl stop alphapilot-api || true
sleep 1
# kill anything on :8000
if command -v fuser >/dev/null; then
  sudo fuser -k 8000/tcp || true
fi
PIDS=$(ss -lptn 'sport = :8000' 2>/dev/null | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | sort -u)
for p in $PIDS; do
  echo "kill $p"
  sudo kill -9 "$p" || true
done
# also pkill uvicorn api_server
pkill -9 -f 'uvicorn api_server:app' || true
sleep 2
ss -lptn 'sport = :8000' || echo 'port free'
sudo systemctl start alphapilot-api
sleep 3
systemctl is-active alphapilot-api
pgrep -af 'uvicorn api_server' || true
python3 /tmp/_check_api_loop.py
