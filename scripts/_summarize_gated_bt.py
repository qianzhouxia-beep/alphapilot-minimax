#!/usr/bin/env python3
import json
from pathlib import Path
import numpy as np

p = Path("/home/ubuntu/alphapilot/output/v3_tradable_gated_sleeve_backtest.json")
if not p.exists():
    p = Path("/home/ubuntu/alphapilot/output/v3_tradable_gated_backtest.json")
o = json.loads(p.read_text(encoding="utf-8"))
print("kpi:", json.dumps(o["kpi"], ensure_ascii=False, indent=2))
for arm in ("A0_baseline", "A1_cur", "A1_ladder"):
    tr = o["trades"][arm]
    filled = [t for t in tr if not t.get("skipped")]
    july = [t for t in filled if t["date"] >= "2026-07-01"]
    half = [t for t in filled if float(t.get("exposure", 1)) < 1]
    print(
        arm,
        "july_n",
        len(july),
        "july_avg_scaled",
        round(100 * float(np.mean([t["ret"] for t in july])), 2) if july else None,
        "july_avg_raw",
        round(100 * float(np.mean([t.get("ret_raw", t["ret"]) for t in july])), 2) if july else None,
    )
    print(
        "  half_n",
        len(half),
        "half_avg_scaled",
        round(100 * float(np.mean([t["ret"] for t in half])), 2) if half else None,
        "half_avg_raw",
        round(100 * float(np.mean([t.get("ret_raw", t["ret"]) for t in half])), 2) if half else None,
    )
    if arm == "A1_ladder":
        raws = np.array([t.get("ret_raw", t["ret"]) for t in filled], float)
        print(
            "  raw_win",
            round(100 * float((raws > 0).mean()), 1),
            "raw_hit3",
            round(100 * float((raws >= 0.03).mean()), 1),
            "raw_avg",
            round(100 * float(raws.mean()), 2),
        )
