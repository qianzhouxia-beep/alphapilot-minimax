#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查看 RD 影子并行试运行历史：每天生产 Top2 vs 候选 Top2。

用法: python3 scripts/shadow_top2_history.py [--json]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HIST = ROOT / "output" / "shadow_top2_history.jsonl"


def main() -> int:
    if not HIST.exists():
        print(f"no shadow history yet: {HIST}")
        return 0
    rows = []
    for line in HIST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if "--json" in sys.argv:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    print(f"shadow history: {len(rows)} day(s)  → {HIST}\n")
    for r in rows:
        prod = " / ".join(f"{p.get('name') or p.get('symbol')}({p.get('score')})" for p in r.get("prod_picks") or [])
        shadow = " / ".join(f"{p.get('name') or p.get('symbol')}({p.get('score')})" for p in r.get("shadow_picks") or [])
        print(f"[{r.get('date')}] n_gated={r.get('n_gated')} expo={r.get('position_exposure')}")
        print(f"  生产  Top2: {prod}")
        print(f"  候选  Top2: {shadow}")
        print(f"  model_dir: {r.get('model_dir')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
