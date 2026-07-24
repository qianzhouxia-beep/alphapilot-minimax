#!/usr/bin/env python3
"""Compare old hard main_net_5d>0 vs weak_hard+soft fund gate on largest local pool."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from money_flow_gate import apply_money_flow_gate


def load_largest_pool():
    cands = []
    for p in [
        Path("output/daily_recommend_pre_gate.json"),
        Path("output/screener_raw.json"),
        Path("output/recommend_pre_money.json"),
        Path("output/volume_gc_scored.json"),
        Path("output/debate_v2_result.json"),
        Path("output/daily_recommend.json"),
    ]:
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        items = d.get("recommendations") or d.get("items") or d.get("stocks")
        if items is None and isinstance(d, list):
            items = d
        if isinstance(items, list):
            print(f"FILE {p} n={len(items)}")
            if len(items) > len(cands):
                cands = items
    if len(cands) < 20:
        for p in Path("output").glob("*.json"):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            items = d.get("recommendations") or d.get("items")
            if isinstance(items, list) and len(items) > len(cands):
                print(f"alt {p} n={len(items)}")
                cands = items
    return cands


def main():
    cands = load_largest_pool()
    print("using", len(cands))
    if len(cands) < 5:
        raise SystemExit("no large pool")

    for r in cands:
        r.setdefault("score", r.get("lgb_score") or r.get("model_proba") or 0.5)

    out = apply_money_flow_gate(list(cands), top_n=None, hard_main_net_5d=True)
    print("gate in", len(cands), "out", len(out))

    hist = {}
    if Path("data/fund_flow_history.json").exists():
        hist = json.loads(Path("data/fund_flow_history.json").read_text(encoding="utf-8"))

    old_fail = new_fail = 0
    rescued = []
    for r in cands:
        code = str(r.get("symbol", ""))[-6:]
        h = hist.get(code) or {}
        dates = sorted(h.keys(), reverse=True)
        nets5 = [float(h[d]) for d in dates[:5] if d in h]
        nets3 = [float(h[d]) for d in dates[:3] if d in h]
        if len(nets5) < 3:
            continue
        s5 = sum(nets5)
        s3 = sum(nets3)
        pos5 = sum(1 for x in nets5 if x > 0)
        old = s5 <= 0
        new = (s3 <= 0 and s5 <= 0 and pos5 == 0) or (s5 < -1e8)
        if old:
            old_fail += 1
        if new:
            new_fail += 1
        if old and not new:
            rescued.append(
                (
                    code,
                    r.get("name"),
                    round(s3, 1),
                    round(s5, 1),
                    pos5,
                    round(float(r.get("score") or 0), 4),
                )
            )

    rescued.sort(key=lambda x: -x[5])
    print("old_hard_fail", old_fail, "new_weak_hard_fail", new_fail, "rescued", len(rescued))
    print("top rescued:")
    for row in rescued[:15]:
        print(row)
    print("gate out top:")
    for r in sorted(out, key=lambda x: -float(x.get("score") or 0))[:10]:
        print(
            r.get("symbol"),
            r.get("name"),
            r.get("score"),
            r.get("main_net_3d"),
            r.get("main_net_5d"),
            r.get("fund_soft_bonus"),
        )


if __name__ == "__main__":
    main()
