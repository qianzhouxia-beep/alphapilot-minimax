#!/bin/bash
set -euo pipefail
cd /home/ubuntu/alphapilot

echo "=== uvicorn ==="
pgrep -af 'uvicorn api_server' || true

echo "=== API health ==="
curl -sS -m 10 "http://127.0.0.1:8000/api/health" || curl -sS -m 10 "http://127.0.0.1:8000/" || true
echo

echo "=== recommend sample ==="
curl -sS -m 20 "http://127.0.0.1:8000/api/recommend?limit=2" -o /tmp/rec.json || true
python3 - <<'PY'
import json
from pathlib import Path
p = Path("/tmp/rec.json")
if not p.exists() or not p.read_text().strip():
    print("EMPTY recommend response")
    raise SystemExit(1)
d = json.loads(p.read_text())
print("top_keys", sorted(d.keys())[:30])
for k in ("pipeline_version","model_version","position_exposure","score_scale"):
    if k in d:
        print(k, d.get(k))
stocks = d.get("stocks") or d.get("recommendations") or d.get("items") or []
print("n_stocks", len(stocks))
if stocks:
    s = stocks[0]
    print("stock0_keys_sample", [k for k in ("symbol","name","score","score_pct","model_proba","confidence_score","score_note") if k in s])
    print({k:s.get(k) for k in ("symbol","name","score","score_pct","model_proba","confidence_score")})
else:
    # empty book weekend — still verify meta fields
    print("empty book ok; meta present:", {k:d.get(k) for k in ("pipeline_version","model_version","position_exposure")})
PY

echo "=== frontend strings ==="
# page chunk may be hashed
if grep -R -l 'VM2.5' /home/ubuntu/alphapilot/frontend_out/cn/_next/static/chunks/ 2>/dev/null | head -3; then
  :
fi
grep -R -o '信心分 75–99\|VM2.5\|模型概率\|非百分制' /home/ubuntu/alphapilot/frontend_out/cn/_next/static/chunks/*.js 2>/dev/null | head -20 || true
grep -o 'VM2.5\|信心分\|模型概率\|非百分制' /home/ubuntu/alphapilot/frontend_out/cn/index.html | sort | uniq -c || true

echo "=== nginx root hint ==="
grep -n 'frontend_out\|root ' /etc/nginx/sites-enabled/* 2>/dev/null | head -20 || true
grep -n 'frontend_out\|root ' /etc/nginx/conf.d/* 2>/dev/null | head -20 || true
