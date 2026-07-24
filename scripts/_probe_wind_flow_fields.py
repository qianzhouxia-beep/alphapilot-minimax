#!/usr/bin/env python3
"""Probe Wind index/stock indicators for board money-flow fields."""
import json
import time
import urllib.request
from pathlib import Path

key = None
for line in Path("/home/ubuntu/.wind-aifinmarket/config").read_text().splitlines():
    if line.startswith("WIND_API_KEY="):
        key = line.split("=", 1)[1].strip().strip('"').strip("'")

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
    return json.loads(last) if last else {}


def call(ep, tool, args):
    def post(method, params):
        body = json.dumps(
            {"jsonrpc": "2.0", "id": int(time.time() * 1000), "method": method, "params": params}
        ).encode()
        req = urllib.request.Request(ep, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            return parse(r.read().decode("utf-8", "replace"))

    post(
        "initialize",
        {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "probe2", "version": "1"},
        },
    )
    return post("tools/call", {"name": tool, "arguments": args, "_meta": {"clientVersion": "1.0"}})


STOCK = "https://mcp.wind.com.cn/vserver_stock_data/mcp/"
INDEX = "https://mcp.wind.com.cn/vserver_index_data/mcp/"

# list all stock tools
init = call  # noqa
# tools/list via stock
body = json.dumps(
    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "x", "version": "1"}}}
).encode()
req = urllib.request.Request(STOCK, data=body, headers=headers, method="POST")
with urllib.request.urlopen(req, timeout=30) as r:
    parse(r.read().decode())
body = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}).encode()
req = urllib.request.Request(STOCK, data=body, headers=headers, method="POST")
with urllib.request.urlopen(req, timeout=30) as r:
    tools = parse(r.read().decode())
print("STOCK TOOLS:")
for t in (tools.get("result") or {}).get("tools") or []:
    print("-", t.get("name"))
    desc = (t.get("description") or "")[:120]
    print(" ", desc)

INDEXES_CANDIDATES = [
    "中文简称,当日主力净流入额,当日主力净流入占比,近5日主力净流入额,近5日主力净流入占比",
    "中文简称,主力净流入,主力净流入占比,机构净流入,大户净流入,散户净流入",
    "中文简称,净流入额,净流入率,净流入天数",
    "名称,净流入额,净流入率,净流入天数",
]

codes = [
    ("801738.SI", "电网设备行业"),
    ("8841723.WI", "全A负动量概念"),
    ("881001.WI", "万得全A?"),
    ("8841388.WI", "万得全A等权"),
]

for code, label in codes:
    print("\n====", code, label)
    for idx in INDEXES_CANDIDATES:
        try:
            # try index endpoint first
            res = call(INDEX, "get_index_price_indicators", {"windcode": code, "indexes": idx})
            text = ""
            content = ((res.get("result") or {}).get("content") or [])
            if content:
                text = content[0].get("text") or ""
            elif res.get("error"):
                text = str(res["error"])[:200]
            else:
                text = str(res)[:300]
            print(" INDEX", idx[:40], "->", text[:220].replace("\n", " "))
        except Exception as e:
            print(" INDEX err", e)
        try:
            res = call(STOCK, "get_stock_price_indicators", {"windcode": code, "indexes": idx})
            content = ((res.get("result") or {}).get("content") or [])
            text = content[0].get("text") if content else str(res)[:300]
            print(" STOCK", idx[:40], "->", str(text)[:220].replace("\n", " "))
        except Exception as e:
            print(" STOCK err", e)
