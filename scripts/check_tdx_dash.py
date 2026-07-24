#!/usr/bin/env python3
from sector_dashboard import build_dashboard
d = build_dashboard(period="today")
print("provider", d.get("provider"))
print("summary", d["summary"])
print("top", [(x["name"], x["net_yi"]) for x in d["today_top10"][:5]])
print("asof", d["meta"].get("asof"))
print("headline", (d.get("analysis") or {}).get("headline"))
