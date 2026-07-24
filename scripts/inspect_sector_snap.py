#!/usr/bin/env python3
import json, os
from pathlib import Path
p = Path("/home/ubuntu/alphapilot/output/sector_rotation_snapshot.json")
print("exists", p.exists())
if p.exists():
    d = json.loads(p.read_text(encoding="utf-8"))
    print("keys", list(d.keys()))
    print("ts", d.get("ts"))
    print("top10", d.get("today_top10"))
    print("bottom10", d.get("today_bottom10"))
    c = d.get("classes") or {}
    print("allow", len(c.get("allow") or []), "deny", len(c.get("deny") or []), "neutral", len(c.get("neutral") or []))
    if c.get("allow"):
        print("allow0", c["allow"][0])
for f in Path("/home/ubuntu/alphapilot/data").glob("sector_flow*.json"):
    print("flow_file", f.name, f.stat().st_size)
