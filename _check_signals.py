#!/usr/bin/env python3
import json
from pathlib import Path

pt = json.loads(Path("/home/ubuntu/alphapilot/data/paper_trading.json").read_text(encoding="utf-8"))
for s in pt.get("strategies") or []:
    sigs = s.get("signals") or []
    print(s.get("id"), "signals", len(sigs), "allocated", s.get("allocated"))
    for x in sigs:
        print(" ", x.get("symbol"), x.get("ticket_id"), x.get("protocol"), x.get("action"))
print("approval_gate", pt.get("approval_gate"))
