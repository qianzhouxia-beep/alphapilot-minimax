#!/usr/bin/env python3
import json, urllib.request
raw = urllib.request.urlopen("http://127.0.0.1:8000/api/v1/cn/paper-trading", timeout=15).read()
d = json.loads(raw)
print("expo", d.get("position_exposure"))
print("protocol", d.get("protocol"))
print("next", d.get("next_execution"))
loop = d.get("loop") or {}
print("loop_keys", list(loop.keys()))
print("oos_verdict", (loop.get("oos") or {}).get("verdict"))
print("audit_hit", ((loop.get("audit") or {}).get("kpi") or {}).get("hit_3pct_rate"))
print("strats", [(s.get("id"), s.get("name"), len(s.get("positions") or [])) for s in d.get("strategies", [])])
