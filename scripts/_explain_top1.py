#!/usr/bin/env python3
import json
from pathlib import Path

root = Path("/home/ubuntu/alphapilot")
d = json.loads((root / "output/daily_recommend.json").read_text(encoding="utf-8"))
items = d.get("recommendations") or []
print("n", len(items))
print("expo", d.get("position_exposure"))
print("top_n", d.get("recommend_top_n"))
print("mode", d.get("exposure_mode"))
print("flags", d.get("market_env_flags"))
p = d.get("permission") or {}
print(
    "perm",
    {
        k: p.get(k)
        for k in ("permission_on", "up3_count", "n_sustained_in", "rotation_dead")
    },
)
for it in items[:5]:
    print(
        "-",
        it.get("symbol"),
        it.get("name"),
        "score",
        it.get("score"),
        "soft",
        it.get("soft_demote_reasons"),
    )
