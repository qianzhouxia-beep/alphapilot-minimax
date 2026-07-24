#!/usr/bin/env python3
import json
from pathlib import Path
d = json.loads(Path("/home/ubuntu/alphapilot/data/paper_trading.json").read_text(encoding="utf-8"))
for s in d.get("strategies") or []:
    print("---", s.get("id"))
    for k,v in s.items():
        if k in ("positions","signals","trade_log"):
            print(f"  {k}: len={len(v) if isinstance(v,list) else v}")
        else:
            print(f"  {k}: {v}")
