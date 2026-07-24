#!/usr/bin/env python3
import json
from pathlib import Path

p = Path("/home/ubuntu/alphapilot/data/fund_flow_history.json")
t = Path("/home/ubuntu/alphapilot/data/fund_flow_history.tdx.json")
b = Path("/home/ubuntu/alphapilot/data/fund_flow_history.prev_backup.json")
d = json.loads(p.read_text(encoding="utf-8"))
td = json.loads(t.read_text(encoding="utf-8"))
bk = json.loads(b.read_text(encoding="utf-8")) if b.exists() else {}
for code in ("600519", "000858", "000034"):
    s, ts, bs = d.get(code, {}), td.get(code, {}), bk.get(code, {})
    last = max(s) if s else None
    print(
        code,
        "days",
        len(s),
        "first",
        min(s) if s else None,
        "last",
        last,
        "prod_last",
        s.get(last),
        "tdx_last",
        ts.get(last),
        "old_last",
        bs.get(last),
        "tdx_overwrote",
        abs((s.get(last) or 0) - (ts.get(last) or 0)) < 1,
    )
depths = [len(v) for v in d.values() if isinstance(v, dict)]
print("prod_stocks", len(d), "mean_depth", round(sum(depths) / len(depths), 1), "tdx_file", len(td))
