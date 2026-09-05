# -*- coding: utf-8 -*-
"""Offline test: Track A MAX_CAND_RANK=2 filter (2026-09-01).

Only 09:35 candidates.json rank 1-2 may enter P2. Rank 3+, missing rank,
and MAX_CAND_RANK<=0 off-switch are covered. Helpers are exec'd via AST so
QMT/TDX/Ptrade builtins are not required.
"""
import ast
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\elvisq\Projects\alphapilot\production_strategies")

FILES = [
    ("QMT live A", ROOT / "track_a" / "TrackA_track_a_qmt_full_chain_live.py", "v2.30-tpl"),
    ("QMT sim A",  ROOT / "track_a" / "TrackA_track_a_qmt_full_chain_sim.py", "v2.30"),
    ("TDX sim A",  ROOT / "track_a" / "TrackA_track_a_tdx_full_chain_sim.py", "v2.29"),
    ("ptrade sim A", ROOT / "ptrade" / "TrackA_track_a_ptrade_sim.py", "v1.7"),
    ("ptrade live A", ROOT / "ptrade" / "TrackA_track_a_ptrade_live.py", "v1.7-tpl"),
]

SAMPLE = [
    {"symbol": "A", "rank": 1},
    {"symbol": "B", "rank": 2},
    {"symbol": "C", "rank": 3},
    {"symbol": "D", "rank": 10},
    {"symbol": "E"},
    {"symbol": "F", "rank": 0},
]

passed = failed = 0


def check(name, cond):
    global passed, failed
    if cond:
        passed += 1
        print("  PASS " + name)
    else:
        failed += 1
        print("  FAIL " + name)


def _load(raw):
    tree = ast.parse(raw)
    ns = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tg in node.targets:
                if isinstance(tg, ast.Name) and tg.id in ("MAX_CAND_RANK", "ROTATION_ENABLE"):
                    exec(ast.get_source_segment(raw, node), ns)
        elif isinstance(node, ast.FunctionDef) and node.name == "_filter_cands_by_max_rank":
            exec(ast.get_source_segment(raw, node), ns)
    return ns


for label, path, expect_ver in FILES:
    raw = path.read_text(encoding="utf-8", errors="replace")
    check(f"{label}: header has {expect_ver}", expect_ver in raw[:800])
    init_ok = any(("[INIT]" in ln and expect_ver in ln) for ln in raw.splitlines())
    check(f"{label}: INIT has {expect_ver}", init_ok)
    ns = _load(raw)
    check(f"{label}: MAX_CAND_RANK==2", ns.get("MAX_CAND_RANK") == 2)
    check(f"{label}: ROTATION_ENABLE==False", ns.get("ROTATION_ENABLE") is False)
    check(f"{label}: helper present", "_filter_cands_by_max_rank" in ns)
    if "_filter_cands_by_max_rank" not in ns:
        continue
    fn = ns["_filter_cands_by_max_rank"]
    kept = fn(SAMPLE)
    syms = [it["symbol"] for it in kept]
    check(f"{label}: keep rank 1-2 only", syms == ["A", "B"])
    check(f"{label}: empty in -> empty out", fn([]) == [])
    ns["MAX_CAND_RANK"] = 0
    check(f"{label}: MAX_CAND_RANK=0 is off", [it["symbol"] for it in fn(SAMPLE)] ==
          ["A", "B", "C", "D", "E", "F"])

print("\n===== %d passed, %d failed =====" % (passed, failed))
sys.exit(1 if failed else 0)
