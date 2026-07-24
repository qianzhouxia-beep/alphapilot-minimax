#!/usr/bin/env python3
"""Rebuild scored-ish pool from launch∪bypass and dump PE>30-only drops."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path("/home/ubuntu/alphapilot")
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from money_flow_gate import apply_money_flow_gate

OUT = ROOT / "output"
launch = []
gc = OUT / "volume_gc_pool.json"
if gc.exists():
    raw = json.loads(gc.read_text(encoding="utf-8"))
    launch = raw if isinstance(raw, list) else list(raw.get("symbols") or [])
bp = {}
bpf = OUT / "hot_sector_bypass_pool.json"
if bpf.exists():
    bp = json.loads(bpf.read_text(encoding="utf-8"))
bypass_items = bp.get("items") or []
name_map = {str(x.get("symbol")): x.get("name") for x in bypass_items if x.get("symbol")}

syms = set()
for s in launch:
    syms.add(str(s)[-6:])
for s in bp.get("symbols") or []:
    syms.add(str(s)[-6:])

recs = [
    {
        "symbol": s,
        "name": name_map.get(s) or s,
        "score": 0.5,
        "selection_arm": "hot_sector_bypass" if s in set(bp.get("symbols") or []) else "A0_launch",
    }
    for s in sorted(syms)
]
print(f"pool n={len(recs)} PE_TTM_MAX={os.environ.get('PE_TTM_MAX','30')} "
      f"ENABLE={os.environ.get('ENABLE_PE_TTM_HARD','1')}")
# run gate (writes audit)
_ = apply_money_flow_gate(recs, top_n=None)
audit_path = OUT / "money_gate_pe_audit.json"
audit = json.loads(audit_path.read_text(encoding="utf-8"))
print(
    f"pe_gate_on={audit.get('pe_gate_on')} max={audit.get('max_pe_ttm')} "
    f"drop={audit.get('n_pe_dropped')} le0={audit.get('n_pe_le_0')} "
    f"gt={audit.get('n_pe_gt_max')} gt_only={audit.get('n_pe_gt_max_only')}"
)
print("\n=== PE>30 独有（未同时踩资金弱硬底）Top40 ===")
for i, r in enumerate(audit.get("pe_gt_max_only") or [][:40], 1):
    print(
        f"{i:2d}. {r.get('symbol')} {r.get('name')}  PE={r.get('pe_ttm')}  "
        f"arm={r.get('selection_arm')}"
    )
print(f"... total pe_gt_max_only={audit.get('n_pe_gt_max_only')}")
