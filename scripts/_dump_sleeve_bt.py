#!/usr/bin/env python3
import json
from pathlib import Path

for name in ("weak_sleeve_vs_empty_backtest.json", "weak_fund_sleeve_picks.json"):
    p = Path("output") / name
    print("=" * 60, name)
    if not p.exists():
        print("missing")
        continue
    d = json.loads(p.read_text(encoding="utf-8"))
    if "kpi" in d:
        print(json.dumps({k: d[k] for k in ["kpi", "delta_sleeve_minus_empty", "severe_days", "trades", "day_meta"]}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(d, ensure_ascii=False, indent=2)[:3000])
