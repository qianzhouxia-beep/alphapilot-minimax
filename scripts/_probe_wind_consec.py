#!/usr/bin/env python3
import json, time, urllib.request
from pathlib import Path

key = None
for line in Path.home().joinpath(".wind-aifinmarket/config").read_text().splitlines():
    if line.strip().startswith("WIND_API_KEY="):
        key = line.split("=", 1)[1].strip().strip('"').strip("'")
EP = "https://mcp.wind.com.cn/vserver_index_data/mcp/"
headers = {
    "Authorization": "Bearer " + key,
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


def parse(raw):
    t = raw.strip()
    if t.startswith("{"):
        return json.loads(t)
    last = None
    for line in t.splitlines():
        if line.startswith("data: "):
            last = line[6:]
    return json.loads(last) if last else {}


def call(tool, args):
    def post(method, params):
        body = json.dumps(
            {"jsonrpc": "2.0", "id": int(time.time() * 1000), "method": method, "params": params}
        ).encode()
        req = urllib.request.Request(EP, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            return parse(r.read().decode("utf-8", "replace"))

    post(
        "initialize",
        {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "probe", "version": "1"},
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
    if (inner or {}).get("error"):
        return inner["error"]
    data = (inner or {}).get("data") or inner
    cols = [c.get("name") if isinstance(c, dict) else c for c in (data.get("columns") or [])]
    rows = data.get("rows") or []
    return dict(zip(cols, rows[0])) if cols and rows else data


for fields in [
    "中文简称,当日主力净流入额,近5日主力净流入天数,连续净流入天数,净流入天数,主力净流入天数",
    "中文简称,连续主力净流入天数,主力资金连续净流入天数,连红天数",
]:
    row = extract(call("get_index_price_indicators", {"windcode": "801738.SI", "indexes": fields}))
    print(fields[:50], "=>", row)
