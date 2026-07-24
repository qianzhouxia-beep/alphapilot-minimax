#!/bin/bash
set -e
export NVM_DIR=/home/ubuntu/.nvm
. "$NVM_DIR/nvm.sh"
nvm use 20 >/dev/null

PAGE=/home/ubuntu/alphapilot-repo/frontend/app/cn/paper-trading/page.tsx
API=/home/ubuntu/alphapilot-repo/frontend/lib/cn-api.ts
echo "page bytes $(wc -c < "$PAGE")"
echo "page has 今日待确认? $(grep -c '今日待确认' "$PAGE" || true)"
echo "page has pending_orders? $(grep -c 'pending_orders' "$PAGE" || true)"
echo "api has liveOrders? $(grep -c 'liveOrders\|live-orders' "$API" || true)"

echo "--- search built chunks ---"
# Chinese may be escaped in JS; search ASCII API markers
FOUND=$(grep -R 'live-orders\|pending_orders\|approveLive\|broker-connection' -l /home/ubuntu/alphapilot-repo/frontend/out/_next/static 2>/dev/null | head || true)
echo "$FOUND"
if [ -z "$FOUND" ]; then
  echo "NO API markers in build - checking index.html size"
  wc -c /home/ubuntu/alphapilot-repo/frontend/out/cn/paper-trading/index.html
  # extract script refs
  grep -o '_next/static/chunks/[^"]*' /home/ubuntu/alphapilot-repo/frontend/out/cn/paper-trading/index.html | head
fi

# compare mtime source vs build
stat -c '%y %n' "$PAGE" /home/ubuntu/alphapilot-repo/frontend/out/cn/paper-trading/index.html
