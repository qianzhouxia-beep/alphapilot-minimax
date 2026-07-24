#!/usr/bin/env python3
import json
from hot_sector_prefer_boost import apply_hot_sector_prefer_boost
from sector_rotation_gate import build_snapshot

items = json.load(open("output/daily_recommend.json", encoding="utf-8"))["recommendations"]
snap = build_snapshot()
out = apply_hot_sector_prefer_boost(list(items), snap=snap)
for x in out[:8]:
    print(
        x.get("symbol"),
        x.get("name"),
        round(float(x.get("score") or 0), 4),
        x.get("hot_sector_prefer"),
        x.get("hot_sector_boost"),
    )
