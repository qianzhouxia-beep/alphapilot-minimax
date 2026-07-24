#!/usr/bin/env python3
import json, urllib.request
raw = urllib.request.urlopen("http://127.0.0.1:8000/api/v1/cn/sectors", timeout=60).read()
d = json.loads(raw)
print("ts", d.get("ts"))
print("summary", d.get("summary"))
print("flow_bars", len(d.get("flow_bars") or []))
print("scatter", len(d.get("scatter") or []))
print("top", (d.get("today_top10") or [])[:3])
