#!/bin/bash
set -u
HOST=alphapilot.api-tokenmaster.com
echo "=== DNS ==="
getent hosts "$HOST" 2>/dev/null || host "$HOST" 2>/dev/null || nslookup "$HOST" 2>/dev/null | head -20
echo
echo "=== curl -vI https ==="
curl -vI -m 20 "https://$HOST/" 2>&1 | tail -40
echo
echo "=== curl http ==="
curl -sS -m 15 -o /dev/null -w "http=%{http_code} err=%{errormsg}\n" "http://$HOST/" || true
echo
echo "=== local uvicorn health ==="
curl -sS -m 5 "http://127.0.0.1:8000/health" || echo "local8000_fail"
pgrep -af 'uvicorn api_server' || echo "no_uvicorn"
echo
echo "=== nginx ==="
sudo nginx -t 2>&1 | tail -5
ss -lntp | grep -E ':80|:443|:8000' || true
