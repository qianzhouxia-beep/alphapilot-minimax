#!/bin/bash
set -euo pipefail
echo "=== nginx configs mentioning alphapilot ==="
grep -Rnl 'alphapilot\|api-tokenmaster' /etc/nginx 2>/dev/null || true
echo
echo "=== server_name blocks ==="
grep -Rn 'server_name\|root \|proxy_pass\|listen ' /etc/nginx/sites-enabled /etc/nginx/conf.d /etc/nginx/nginx.conf 2>/dev/null | head -120
echo
echo "=== curl Host header local ==="
for host in alphapilot.api-tokenmaster.com estate.api-tokenmaster.com 150.158.100.236; do
  echo "-- Host: $host /cn/"
  curl -sS -m 10 -H "Host: $host" http://127.0.0.1/cn/ | grep -oE 'VM2.5|信心分|模型概率|V18|V1\.9' | sort | uniq -c || true
done
echo
echo "-- direct uvicorn /cn/"
curl -sS -m 10 http://127.0.0.1:8000/cn/ | grep -oE 'VM2.5|信心分|模型概率|V18|V1\.9' | sort | uniq -c || true
echo
echo "-- public again"
curl -sS -m 15 https://alphapilot.api-tokenmaster.com/cn/ | grep -oE 'VM2.5|信心分|模型概率|V18|V1\.9' | sort | uniq -c || true
echo
echo "=== response headers public ==="
curl -sSI -m 15 https://alphapilot.api-tokenmaster.com/cn/ | head -30
