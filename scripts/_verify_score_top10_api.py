#!/usr/bin/env python3
import json
import urllib.request

d = json.loads(urllib.request.urlopen("http://127.0.0.1:8000/api/v1/cn/score-top10", timeout=30).read())
print("n", d.get("n"), "asof", d.get("asof"))
for it in d.get("items") or []:
    print(it.get("rank"), it.get("symbol"), it.get("name"), round(float(it.get("score") or 0), 4), it.get("change_pct"))
print("REC")
for it in d.get("recommend_compare") or []:
    print("-", it.get("symbol"), it.get("name"), round(float(it.get("score") or 0), 4), it.get("change_pct"))
