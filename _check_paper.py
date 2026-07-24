#!/usr/bin/env python3
import json
from pathlib import Path

pt = Path("/home/ubuntu/alphapilot/data/paper_trading.json")
d = json.loads(pt.read_text(encoding="utf-8"))
print("keys", list(d.keys())[:30])
sigs = d.get("signals") or []
print("signals_n", len(sigs))
for s in sigs[-8:]:
    print(" ", s.get("symbol"), s.get("name"), s.get("ticket_id"), s.get("action") or s.get("side"), s.get("status"))

tk = Path("/home/ubuntu/alphapilot/data/order_tickets/owner.json")
td = json.loads(tk.read_text(encoding="utf-8"))
for t in td.get("tickets") or []:
    print("ticket", t.get("id"), t.get("symbol"), t.get("status"), t.get("expires_at"))
