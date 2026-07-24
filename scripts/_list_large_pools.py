#!/usr/bin/env python3
import json
from pathlib import Path

root = Path("/home/ubuntu/alphapilot/output")
for p in sorted(root.glob("*.json")):
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        continue
    items = d.get("recommendations") or d.get("items")
    if items is None and isinstance(d, list):
        items = d
    if isinstance(items, list) and len(items) >= 5:
        print(f"{p.name}\t{len(items)}")
