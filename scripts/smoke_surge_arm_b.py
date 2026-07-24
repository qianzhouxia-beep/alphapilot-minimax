#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: ENABLE_SURGE_ARM_B soft reflux tagging."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ["ENABLE_SURGE_ARM_B"] = "1"
os.environ["SURGE_ARM_B_MULT"] = "0.85"

from soft_universe_gate import apply_universe_gate  # noqa: E402


def main() -> int:
    items = [
        {"symbol": "600000", "name": "launch", "score": 0.9},
        {"symbol": "600001", "name": "bypass", "score": 0.8},
        {"symbol": "600002", "name": "orphan", "score": 1.0},
    ]
    out, meta = apply_universe_gate(
        items,
        gc_bare={"600000"},
        gc_set=set(),
        bypass_bare={"600001"},
        log=print,
    )
    by = {x["symbol"]: x for x in out}
    assert by["600000"]["arm"] == "A"
    assert by["600001"]["arm"] == "A"
    assert by["600002"]["arm"] == "B"
    assert abs(by["600002"]["score"] - 0.85) < 1e-6
    assert meta.get("surge_arm_b") is True
    assert meta.get("n_arm_b") == 1
    print("OK smoke_surge_arm_b", meta)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
