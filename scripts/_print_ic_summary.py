#!/usr/bin/env python3
import json
from pathlib import Path

o = json.loads(Path("/home/ubuntu/alphapilot/output/factor_ic_by_regime.json").read_text(encoding="utf-8"))
focus = [
    "pb", "roe", "eps", "revenue", "profit_margin",
    "z_chip_concentration", "chip_penetration_3d", "chip_profit_trend",
    "chip_distribution_width", "main_net_5d", "main_net_10d",
    "ret_range", "atr_pct", "buy_inst_count", "has_lhb", "ma_cross_20_60",
]
for lab in ["ic_t1open_t2close", "ic_fwd1d"]:
    print("LAB", lab)
    for reg, rows in (o.get(lab) or {}).items():
        m = {r["factor"]: r for r in rows}
        print(" ", reg, "listed", len(rows))
        for f in focus:
            r = m.get(f)
            if r:
                print(f"    {f}: IC={r['mean_ic']} ICIR={r['icir']}")
        # also print top3 absolute
        print("    TOP3 |IC|:", ", ".join(f"{r['factor']}={r['mean_ic']}" for r in rows[:3]))
