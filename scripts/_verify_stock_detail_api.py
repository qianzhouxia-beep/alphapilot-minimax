#!/usr/bin/env python3
import json
import urllib.request

base = "http://127.0.0.1:8000"


def get(path):
    with urllib.request.urlopen(base + path, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


d = get("/api/v1/cn/stock/603228")
keys = [
    "name",
    "score",
    "sector",
    "industry",
    "industry_l1",
    "main_net_3d",
    "main_net_5d",
    "fund_pos_days_5",
    "money_phase_label",
]
print("DETAIL", {k: d.get(k) for k in keys})
print("series_n", len(d.get("fund_series_5d") or []))
p = get("/api/v1/cn/stock/603228/peers")
print("PEERS sector=", p.get("sector"), "n=", len(p.get("peers") or []))
print("sample", (p.get("peers") or [])[:3])
try:
    n = get("/api/v1/cn/stock/603228/news")
    print("NEWS n=", len(n) if isinstance(n, list) else type(n))
    if isinstance(n, list) and n:
        print("first", n[0].get("title", "")[:60])
except Exception as e:
    print("NEWS err", e)
