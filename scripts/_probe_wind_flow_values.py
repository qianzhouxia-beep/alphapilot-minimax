#!/usr/bin/env python3
"""Print full Wind rows + try more money-flow field names."""
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
INDEX = "https://mcp.wind.com.cn/vserver_index_data/mcp/"
STOCK = "https://mcp.wind.com.cn/vserver_stock_data/mcp/"


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
            "clientInfo": {"name": "probe3", "version": "1"},
        },
    )
    return post("tools/call", {"name": tool, "arguments": args, "_meta": {"clientVersion": "1.0"}})


def extract(res):
    content = ((res.get("result") or {}).get("content") or [])
    if not content:
        return res
    text = content[0].get("text") or ""
    try:
        inner = json.loads(text)
    except Exception:
        return text
    data = (inner or {}).get("data") or inner
    if (inner or {}).get("error"):
        return inner["error"]
    cols = [c.get("name") if isinstance(c, dict) else c for c in (data.get("columns") or [])]
    rows = data.get("rows") or []
    if cols and rows:
        return dict(zip(cols, rows[0]))
    return data


# Known working + try institution tiers
fields = [
    "中文简称,最新成交价,涨跌幅,当日主力净流入额,当日主力净流入占比,近5日主力净流入额,近5日主力净流入占比",
    "中文简称,机构买入净额,机构卖出净额,机构净流入,大户净流入,中户净流入,散户净流入",
    "中文简称,超大单净流入,大单净流入,中单净流入,小单净流入",
    "中文简称,当日超大单净流入额,当日大单净流入额,当日中单净流入额,当日小单净流入额",
    "中文简称,主力净流入天数,连续净流入天数,净流入天数",
]

for code in ("801738.SI", "8841388.WI", "881001.WI"):
    print("\n====", code)
    for f in fields:
        row = extract(call(INDEX, "get_index_price_indicators", {"windcode": code, "indexes": f}))
        print(f[:50], "=>", row)

# list a few SW industries from existing eastmoney sector flow if available
from pathlib import Path as P
for p in [
    P("/home/ubuntu/alphapilot/data/sector_flow_today.json"),
    P("/home/ubuntu/alphapilot/data/stock_industry_map.json"),
]:
    print("exists", p, p.exists())
