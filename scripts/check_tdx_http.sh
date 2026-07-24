#!/bin/bash
cd /home/ubuntu/alphapilot
python3 <<'PY'
from sector_dashboard import build_dashboard
d = build_dashboard(period="today")
print("provider", d.get("provider"))
print("summary", d["summary"])
print("top", [(x["name"], x["net_yi"]) for x in d["today_top10"][:5]])
print("asof", d["meta"].get("asof"))
print("headline", (d.get("analysis") or {}).get("headline"))
# also via HTTP
import urllib.request, json
raw = urllib.request.urlopen("http://127.0.0.1:8000/api/v1/cn/sectors?period=today&refresh=true", timeout=60).read()
j = json.loads(raw)
print("http_provider", j.get("provider"), "generated", j.get("generated_at"), "periods", j.get("periods"))
PY
