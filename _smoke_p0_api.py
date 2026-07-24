#!/usr/bin/env python3
"""P0 smoke: login as owner, list/approve/reject tickets, check broker API."""
import json
import os
import sys
import urllib.error
import urllib.request

os.chdir("/home/ubuntu/alphapilot")
sys.path.insert(0, "/home/ubuntu/alphapilot")

from auth_users import ensure_owner_user, issue_token, OWNER_EMAIL

user = ensure_owner_user()
token = issue_token(user)
print("owner", user.get("email"), "is_owner", user.get("is_owner"), "id", user.get("id"))


def call(method, path, body=None):
    data = None
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:8000{path}", data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="ignore")
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"raw": raw}
        return e.code, payload


code, lo = call("GET", "/api/v1/cn/live-orders")
print("live-orders", code, "pending_n=", lo.get("pending_n"), "tickets=", len(lo.get("tickets") or []))
for t in (lo.get("pending") or [])[:5]:
    print(" ", t.get("id"), t.get("symbol"), t.get("name"), t.get("status"), t.get("expires_at"))

code, br = call("GET", "/api/v1/cn/broker-connection")
print("broker-get", code, br)

# save paper_only broker config (commercial placeholder)
code, br2 = call(
    "PUT",
    "/api/v1/cn/broker-connection",
    {
        "adapter": "paper_only",
        "enabled": False,
        "config": {
            "account_id": "",
            "userdata_path": "",
            "trade_host": "127.0.0.1",
            "trade_port": 58610,
            "quote_host": "127.0.0.1",
            "quote_port": 58611,
            "agent_token": "demo-agent-token-not-for-prod",
        },
    },
)
print("broker-put", code, {k: br2.get(k) for k in ("adapter", "enabled", "user_id") if isinstance(br2, dict)})

pending = lo.get("pending") or []
if pending:
    tid = pending[0]["id"]
    # reject one if more than 1, else just approve without execute
    if len(pending) > 1:
        code, rj = call("POST", "/api/v1/cn/live-orders/reject", {"ticket_ids": [pending[1]["id"]], "reason": "p0_smoke"})
        print("reject", code, "n=", len(rj.get("rejected") or []))
        tid = pending[0]["id"]
    code, ap = call(
        "POST",
        "/api/v1/cn/live-orders/approve",
        {"ticket_ids": [tid], "execute_now": False},
    )
    print(
        "approve",
        code,
        "approved=",
        len(ap.get("approved") or []),
        "synced=",
        ap.get("signals_synced"),
    )

code, lo2 = call("GET", "/api/v1/cn/live-orders?today_only=true")
print(
    "after",
    "pending_n=",
    lo2.get("pending_n"),
    "statuses=",
    sorted({t.get("status") for t in (lo2.get("tickets") or [])}),
)

code, pt = call("GET", "/api/v1/cn/paper-trading")
print(
    "paper",
    code,
    "pending_orders=",
    len((pt.get("pending_orders") or [])),
    "approval_gate=",
    pt.get("approval_gate"),
    "signals=",
    len((pt.get("signals") or pt.get("data", {}).get("signals") or [])),
)
