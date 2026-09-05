# -*- coding: utf-8 -*-
"""Offline test: vwap_weak_early requires a second still-below minute.

Guards 300475 09-02: first 09:36 tick below vwap_ref must NOT sell; a later
minute still below sells; recover cancels; same-minute re-poll stays wait.
Helpers are exec'd via AST so QMT/TDX builtins are not required.
"""
import ast
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\elvisq\Projects\alphapilot\production_strategies")

FILES = [
    ("QMT live A", ROOT / "track_a" / "TrackA_track_a_qmt_full_chain_live.py"),
    ("QMT sim A", ROOT / "track_a" / "TrackA_track_a_qmt_full_chain_sim.py"),
    ("TDX sim A", ROOT / "track_a" / "TrackA_track_a_tdx_full_chain_sim.py"),
    ("QMT live B", ROOT / "track_b" / "TrackB_track_b_qmt_auction_live.py"),
    ("QMT sim B", ROOT / "track_b" / "TrackB_track_b_qmt_auction_sim.py"),
    ("QMT sim B v2.6 filename", ROOT / "track_b" / "TrackB_track_b_qmt_auction_sim_v2.6.py"),
    ("TDX sim B", ROOT / "track_b" / "TrackB_track_b_tdx_auction_sim.py"),
    ("ptrade live A", ROOT / "ptrade" / "TrackA_track_a_ptrade_live.py"),
    ("ptrade sim A", ROOT / "ptrade" / "TrackA_track_a_ptrade_sim.py"),
]


def load_helpers(path):
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    keep = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in (
            "_vwap_clear_early",
            "_vwap_morning_decide",
        ):
            keep.append(node)
    names = {n.name for n in keep}
    if names != {"_vwap_clear_early", "_vwap_morning_decide"}:
        raise AssertionError("%s helpers=%s" % (path.name, names))
    ns = {}
    exec(compile(ast.Module(body=keep, type_ignores=[]), str(path), "exec"), ns)
    return ns


def run_cases(decide):
    # 300475-like: first 09:36 tick below 171.3
    pos = {"vwap_broken": True, "vwap_ref": 171.3}
    assert decide(pos, 165.62, 9 * 60 + 36) == "wait1"
    assert pos["vwap_early_hits"] == 1
    assert pos["vwap_early_min"] == 9 * 60 + 36
    # same minute re-poll (QMT ticks every few sec) must not sell
    assert decide(pos, 165.50, 9 * 60 + 36) == "wait"
    # next minute still below -> sell
    assert decide(pos, 167.25, 9 * 60 + 37) == "sell"
    # recover cancels
    pos2 = {"vwap_broken": True, "vwap_ref": 171.3}
    assert decide(pos2, 165.62, 9 * 60 + 36) == "wait1"
    assert decide(pos2, 172.00, 9 * 60 + 37) == "recover"
    assert pos2.get("vwap_broken") is False
    assert int(pos2.get("vwap_early_hits") or 0) == 0
    # recover on first tick (already above ref)
    pos3 = {"vwap_broken": True, "vwap_ref": 171.3}
    assert decide(pos3, 172.00, 9 * 60 + 36) == "recover"


def main():
    n = 0
    for label, path in FILES:
        src = path.read_text(encoding="utf-8")
        assert "first confirm wait 2nd" in src, label
        assert '"vwap_early_hits"' in src, label
        ns = load_helpers(path)
        run_cases(ns["_vwap_morning_decide"])
        n += 1
        print("OK", label)
    print("PASS", n, "/", len(FILES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
