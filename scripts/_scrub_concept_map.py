#!/usr/bin/env python3
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_stock_concept_map_tdx import is_noise

p = Path("/home/ubuntu/alphapilot/data/stock_concept_map.json")
d = json.loads(p.read_text(encoding="utf-8"))
n0 = sum(len(v.get("concepts") or []) for v in d.values())
for k, v in d.items():
    cons = [c for c in (v.get("concepts") or []) if not is_noise(c)]
    v["concepts"] = cons
n1 = sum(len(v.get("concepts") or []) for v in d.values())
p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
print("concepts", n0, "->", n1, "stocks", len(d))
