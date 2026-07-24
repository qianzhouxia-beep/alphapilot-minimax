#!/bin/bash
set -u
HOST=alphapilot.api-tokenmaster.com

echo "=== openssl cert ==="
echo | openssl s_client -connect "$HOST:443" -servername "$HOST" -tls1_2 2>&1 | sed -n '1,40p;/subject=/p;/issuer=/p;/Verify return/p;/Protocol/p;/Cipher/p' | head -60

echo
echo "=== tls1_3 ==="
echo | openssl s_client -connect "$HOST:443" -servername "$HOST" -tls1_3 2>&1 | sed -n '/Protocol/p;/Cipher/p;/Verify return/p;/error/p' | head -20

echo
echo "=== curl verbose GET /cn/ ==="
curl -4 -v -m 25 "https://$HOST/cn/" -o /tmp/ap2.html 2>&1 | tail -50
echo "bytes=$(wc -c </tmp/ap2.html 2>/dev/null || echo 0)"
grep -oE 'V3\.1|AlphaPilot' /tmp/ap2.html 2>/dev/null | head -5

echo
echo "=== cert SANs ==="
echo | openssl s_client -connect "$HOST:443" -servername "$HOST" 2>/dev/null | openssl x509 -noout -dates -subject -issuer -ext subjectAltName 2>/dev/null | head -30
