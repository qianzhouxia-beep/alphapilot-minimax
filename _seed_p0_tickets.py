#!/usr/bin/env python3
import json
from datetime import datetime
from pathlib import Path
from order_tickets import create_tickets_from_picks, list_tickets, load_tickets, save_tickets

doc = load_tickets(user_id="owner")
today = datetime.now().strftime("%Y-%m-%d")
kept = []
for t in doc.get("tickets") or []:
    if str(t.get("asof_date"))[:10] == today and t.get("source") == "p0_seed":
        continue
    # 把误标 expired 的今日 pending 源也清掉重来
    if str(t.get("asof_date"))[:10] == today and t.get("status") == "expired":
        continue
    kept.append(t)
doc["tickets"] = kept
save_tickets(doc, user_id="owner")

p = Path("output/morning_live_picks.json")
picks = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
top = picks.get("picks") or []
print("picks", len(top))
c = create_tickets_from_picks(
    top,
    user_id="owner",
    source="p0_seed",
    position_exposure=float(picks.get("position_exposure") or 1),
)
print("created", len(c))
pending = list_tickets(user_id="owner", status="pending_review", today_only=True)
print("pending", len(pending))
for t in pending[:5]:
    print(" ", t.get("id"), t.get("symbol"), t.get("name"), "exp", t.get("expire_at"))
