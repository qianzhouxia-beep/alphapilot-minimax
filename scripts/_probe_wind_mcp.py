#!/usr/bin/env python3
# Probe Wind MCP endpoints for board/sector money-flow tools.
import json
import time
import urllib.request
from pathlib import Path

key = None
for line in Path("/home/ubuntu/.wind-aifinmarket/config").read_text().splitlines():
    line = line.strip()
    if line.startswith("WIND_API_KEY="):
        key = line.split("=", 1)[1].strip().strip('"').strip("'")
print("key_ok", bool(key))

EPS = [
    "https://mcp.wind.com.cn/vserver_stock_data/mcp/",
    "https://mcp.wind.com.cn/vserver_sector_data/mcp/",
    "https://mcp.wind.com.cn/vserver_index_data/mcp/",
    "https://mcp.wind.com.cn/vserver_fund_data/mcp/",
    "https://mcp.wind.com.cn/vserver_market_data/mcp/",
    "https://mcp.wind.com.cn/mcp/",
]
headers = {
    "Authorization": "Bearer " + key,
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


def parse(raw: str):
    t = raw.strip()
    if t.startswith("{"):
        return json.loads(t)
    last = None
    for line in t.splitlines():
        if line.startswith("data: "):
            last = line[6:]
    return json.loads(last) if last else {"raw": t[:500]}


def post(ep, method, params):
    body = json.dumps(
        {"jsonrpc": "2.0", "id": int(time.time() * 1000), "method": method, "params": params}
    ).encode()
    req = urllib.request.Request(ep, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            raw = r.read().decode("utf-8", "replace")
        return parse(raw)
    except Exception as e:
        return {"error": str(e)}


for ep in EPS:
    print("\n===", ep)
    init = post(
        ep,
        "initialize",
        {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "probe", "version": "1"},
        },
    )
    if init.get("error"):
        print("init", init["error"][:200])
        continue
    print("init_ok", list((init.get("result") or {}).keys())[:8])
    tools = post(ep, "tools/list", {})
    result = tools.get("result") or tools
    items = result.get("tools") if isinstance(result, dict) else None
    if not items and isinstance(result, dict):
        print("tools_keys", list(result.keys())[:20])
        print(str(result)[:500])
        continue
    names = [t.get("name") for t in (items or [])]
    print("n_tools", len(names))
    for n in names:
        if any(k in (n or "").lower() for k in ("sector", "indust", "concept", "fund", "flow", "money", "board", "index", "market")):
            print(" *", n)
    if not any(k in str(names).lower() for k in ("sector", "fund", "flow", "money", "board")):
        print(" sample:", names[:15])
