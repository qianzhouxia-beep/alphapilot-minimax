#!/usr/bin/env python3
import json
from pathlib import Path
p = Path("/home/ubuntu/alphapilot/output/daily_recommend.json")
d = json.loads(p.read_text(encoding="utf-8"))
print("stats", d.get("stats"))
print("total_candidates", d.get("total_candidates"))
for k in ("stocks_scanned", "universe_n", "launch_pool_n", "scanned", "elapsed_seconds"):
    if k in d:
        print(k, d[k])
print("n_recs", len(d.get("recommendations") or []))
