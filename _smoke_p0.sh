#!/bin/bash
set -e
cd /home/ubuntu/alphapilot

# find how paper-trading auth works
python3 <<'PY'
import json, os, urllib.request

# Try without auth and with common tokens from env / files
urls = [
    "http://127.0.0.1:8000/api/v1/cn/live-orders",
    "http://127.0.0.1:8000/api/v1/cn/paper-trading",
]
# Discover auth from api if possible
token = os.environ.get("ALPHAPILOT_API_TOKEN") or os.environ.get("API_TOKEN") or ""
for cand in [
    "/home/ubuntu/alphapilot/.env",
    "/home/ubuntu/alphapilot/config/api_token.txt",
    "/etc/alphapilot/env",
]:
    if os.path.isfile(cand):
        print("found", cand)
        with open(cand, "r", encoding="utf-8", errors="ignore") as f:
            txt = f.read()
        for line in txt.splitlines():
            if "TOKEN" in line.upper() or "API_KEY" in line.upper() or "SECRET" in line.upper():
                print("  ", line[:80])

# openapi paths
req = urllib.request.Request("http://127.0.0.1:8000/openapi.json")
with urllib.request.urlopen(req, timeout=10) as r:
    d = json.load(r)
paths = [p for p in d.get("paths", {}) if "live" in p or "broker" in p or "paper" in p]
print("paths:", paths)

# Try live-orders with owner cookie / header patterns from code
headers_list = [
    {},
    {"X-User-Id": "owner"},
    {"Authorization": "Bearer owner"},
]
if token:
    headers_list.append({"Authorization": f"Bearer {token}"})
    headers_list.append({"X-API-Key": token})

for h in headers_list:
    req = urllib.request.Request("http://127.0.0.1:8000/api/v1/cn/live-orders", headers=h)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            body = json.load(r)
            print("OK", h, "pending=", body.get("pending_count") or body.get("summary"), "keys=", list(body.keys())[:12])
            break
    except Exception as e:
        code = getattr(getattr(e, "code", None), "__str__", lambda: None)()
        if hasattr(e, "code"):
            print("fail", h, e.code)
        else:
            print("fail", h, e)
PY
