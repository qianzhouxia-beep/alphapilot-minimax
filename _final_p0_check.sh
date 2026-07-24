#!/bin/bash
set -e
# confirm deployed chunk has live-orders
CHUNK=$(ls /home/ubuntu/alphapilot/frontend_out/_next/static/chunks/app/cn/paper-trading/page-*.js | head -1)
echo "deployed chunk: $CHUNK"
grep -o 'live-orders' "$CHUNK" | head -3
systemctl is-active alphapilot-api
# quick authenticated pending check
cd /home/ubuntu/alphapilot
python3 <<'PY'
from auth_users import ensure_owner_user, issue_token
import json, urllib.request
u = ensure_owner_user()
t = issue_token(u)
req = urllib.request.Request(
    "http://127.0.0.1:8000/api/v1/cn/live-orders",
    headers={"Authorization": f"Bearer {t}"},
)
with urllib.request.urlopen(req, timeout=20) as r:
    d = json.load(r)
print("pending_n", d.get("pending_n"))
for x in d.get("pending") or []:
    print(" ", x["symbol"], x["name"], x["id"][:24], "exp", x.get("expires_at"))
PY
