#!/usr/bin/env python3
import json
d = json.load(open("/home/ubuntu/alphapilot/data/fund_flow_history.json", encoding="utf-8"))
s = d["000034"]
for dt in ["2026-01-16", "2026-07-17", "2026-06-01"]:
    print(dt, s.get(dt))
print("n", len(s))
