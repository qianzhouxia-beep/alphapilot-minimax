#!/usr/bin/env python3
import json, time, urllib.request
from pathlib import Path
key = None
for line in Path("/home/ubuntu/.wind-aifinmarket/config").read_text().splitlines():
    if line.startswith("WIND_API_KEY="):
        key = line.split("=", 1)[1].strip().strip('"').strip("'")
headers = {"Authorization": "Bearer "+key, "Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
INDEX = "https://mcp.wind.com.cn/vserver_index_data/mcp/"

def parse(raw):
    t=raw.strip()
    if t.startswith("{"): return json.loads(t)
    last=None
    for line in t.splitlines():
        if line.startswith("data: "): last=line[6:]
    return json.loads(last) if last else {}

def post(method, params):
    body=json.dumps({"jsonrpc":"2.0","id":int(time.time()*1000),"method":method,"params":params}).encode()
    req=urllib.request.Request(INDEX,data=body,headers=headers,method="POST")
    with urllib.request.urlopen(req,timeout=40) as r:
        return parse(r.read().decode())

post("initialize",{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"x","version":"1"}})
tools=post("tools/list",{})
for t in (tools.get("result") or {}).get("tools") or []:
    print("\n##", t.get("name"))
    print((t.get("description") or "")[:400])
    schema=(t.get("inputSchema") or t.get("input_schema") or {})
    print("schema", json.dumps(schema, ensure_ascii=False)[:500])
