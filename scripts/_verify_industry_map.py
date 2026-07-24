#!/usr/bin/env python3
import json
import sys
from pathlib import Path

ROOT = Path("/home/ubuntu/alphapilot")
sys.path.insert(0, str(ROOT))
import os

os.chdir(ROOT)

from sector_rotation_gate import (
    apply_sector_rotation_gate,
    build_snapshot,
    load_stock_industry_map,
)

# ensure import path for fetch_one
sys.path.insert(0, str(ROOT / "scripts"))
from build_stock_industry_map_tdx import fetch_one  # noqa

m = load_stock_industry_map()
print("map_n", len(m))
ff = json.load(open("data/fund_flow_history.json", encoding="utf-8"))
full = json.load(open("data/stock_industry_map.json", encoding="utf-8"))
for c in ff:
    if c not in full:
        info = fetch_one(c)
        print("retry", c, info)
        if info:
            full[c] = info
json.dump(full, open("data/stock_industry_map.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("final_n", len(full), "still_miss", sum(1 for c in ff if c not in full))

snap = build_snapshot()
demo = [
    {"symbol": "688981", "score": 0.99},
    {"symbol": "601988", "score": 0.55},
    {"symbol": "600900", "score": 0.6},
]
out = apply_sector_rotation_gate(demo, snap=snap, mode="deny_cold")
print(
    "kept",
    [
        (
            x["symbol"],
            x.get("sector_name_resolved"),
            x.get("industry_l1"),
            x.get("sector_rotation"),
        )
        for x in out
    ],
)
assert not any(x["symbol"] == "688981" for x in out), "688981 should be hard-dropped via TDX map→半导体"
print("OK")
