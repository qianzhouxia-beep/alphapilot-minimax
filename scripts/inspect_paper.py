#!/usr/bin/env python3
import json
from pathlib import Path
p = Path("/home/ubuntu/alphapilot/data/paper_trading.json")
d = json.loads(p.read_text(encoding="utf-8"))
print("keys", list(d.keys())[:30])
for s in d.get("strategies") or []:
    print("strategy", s.get("id"), s.get("name"), s.get("desc") or s.get("description"))
print("next", d.get("next_execution"))
print("version", d.get("version"), d.get("engine"), d.get("note"))
