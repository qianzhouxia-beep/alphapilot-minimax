#!/bin/bash
set -e
echo "=== unit ==="
systemctl cat alphapilot-api 2>/dev/null | head -50 || true
echo "=== procs ==="
ps aux | grep -E 'uvicorn|api_server' | grep -v grep || true
echo "=== file ==="
ls -la /home/ubuntu/alphapilot/api_server.py
grep -n "next_execution\|data\[\"loop\"\]\|paper-trading/oos" /home/ubuntu/alphapilot/api_server.py | head -20
echo "=== restart ==="
sudo systemctl restart alphapilot-api
sleep 2
systemctl is-active alphapilot-api || true
python3 /tmp/_check_api_loop.py
