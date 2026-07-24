#!/bin/bash
set -u
HOST=alphapilot.api-tokenmaster.com
echo "=== A / AAAA ==="
dig +short A "$HOST" @1.1.1.1 2>/dev/null || true
dig +short AAAA "$HOST" @1.1.1.1 2>/dev/null || true
getent ahostsv4 "$HOST" 2>/dev/null || true
getent ahostsv6 "$HOST" 2>/dev/null || true

echo "=== GET /cn/ ==="
curl -sS -m 20 -o /tmp/ap_cn.html -w "code=%{http_code} bytes=%{size_download} ip=%{remote_ip}\n" "https://$HOST/cn/"
grep -oE 'V3\.1|资金硬门控|AlphaPilot|ERR_' /tmp/ap_cn.html | sort | uniq -c | head

echo "=== GET / with ipv4 force ==="
curl -4 -sS -m 20 -o /dev/null -w "ipv4 code=%{http_code} ip=%{remote_ip}\n" "https://$HOST/" || echo "ipv4_fail"

echo "=== GET with ipv6 force ==="
curl -6 -sS -m 20 -o /dev/null -w "ipv6 code=%{http_code} ip=%{remote_ip}\n" "https://$HOST/" || echo "ipv6_fail"

echo "=== zeabur raw if known ==="
# try common patterns
curl -sS -m 10 -o /dev/null -w "zeabur=%{http_code}\n" "https://alphapilot.zeabur.app/" 2>/dev/null || true
