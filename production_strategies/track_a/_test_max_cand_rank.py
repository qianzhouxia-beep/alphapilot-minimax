# -*- coding: utf-8 -*-
"""Offline test: Track A MAX_CAND_RANK filter (2026-09-01; updated 2026-09-12).

QMT Track A (v2.34, 方案 A) lets rank 1-3 enter P2; TDX/ptrade stay rank 1-2.
Rank > cap, missing rank, and MAX_CAND_RANK<=0 off-switch are covered. Helpers
are exec'd via AST so QMT/TDX/Ptrade builtins are not required.
"""
# --- portable repo root (replaces a hardcoded C:\Users\... path) ---
from pathlib import Path as _AP_Path
_REPO = _AP_Path(globals().get("__file__") or ".").resolve().parents[2]
import ast
import sys
from pathlib import Path

ROOT = Path(str(_REPO / "production_strategies"))

FILES = [
    # label, path, expected version banner, expected MAX_CAND_RANK
    ("QMT live A", ROOT / "track_a" / "TrackA_track_a_qmt_full_chain_live_v2.38-tpl.py", "v2.38-tpl", 3),
    ("QMT sim A",  ROOT / "track_a" / "TrackA_track_a_qmt_full_chain_sim_v2.45.py", "v2.45", 3),
    ("TDX sim A",  ROOT / "track_a" / "TrackA_track_a_tdx_full_chain_sim_v2.31.py", "v2.31", 2),
    ("ptrade sim A", ROOT / "ptrade" / "TrackA_track_a_ptrade_sim.py", "v1.7", 2),
    ("ptrade live A", ROOT / "ptrade" / "TrackA_track_a_ptrade_live.py", "v1.7-tpl", 2),
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


for label, path, expect_ver, expect_rank in FILES:
    raw = path.read_text(encoding="utf-8", errors="replace")
    check(f"{label}: header has {expect_ver}", expect_ver in raw[:800])
    init_ok = any(("[INIT]" in ln and expect_ver in ln) for ln in raw.splitlines())
    check(f"{label}: INIT has {expect_ver}", init_ok)
    ns = _load(raw)
    check(f"{label}: MAX_CAND_RANK=={expect_rank}", ns.get("MAX_CAND_RANK") == expect_rank)
    check(f"{label}: ROTATION_ENABLE==False", ns.get("ROTATION_ENABLE") is False)
    check(f"{label}: helper present", "_filter_cands_by_max_rank" in ns)
    if "_filter_cands_by_max_rank" not in ns:
        continue
    fn = ns["_filter_cands_by_max_rank"]
    kept = fn(SAMPLE)
    syms = [it["symbol"] for it in kept]
    expect_syms = ["A", "B", "C"][:expect_rank]
    check(f"{label}: keep rank 1-{expect_rank} only", syms == expect_syms)
    check(f"{label}: empty in -> empty out", fn([]) == [])
    ns["MAX_CAND_RANK"] = 0
    check(f"{label}: MAX_CAND_RANK=0 is off", [it["symbol"] for it in fn(SAMPLE)] ==
          ["A", "B", "C", "D", "E", "F"])

print("\n===== %d passed, %d failed =====" % (passed, failed))
sys.exit(1 if failed else 0)
