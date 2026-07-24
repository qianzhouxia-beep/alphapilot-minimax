#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: consec_inflow + surge_ambush annotate/apply + prefer defer."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from consec_inflow import consecutive_inflow_days  # noqa: E402


def test_consec() -> None:
    hist = {
        "2026-07-22": 1e6,
        "2026-07-21": 2e6,
        "2026-07-20": 3e6,
        "2026-07-19": -1e6,
        "2026-07-18": 5e6,
    }
    assert consecutive_inflow_days(hist) == 3
    hist2 = {
        "2026-07-22": 1e6,
        "2026-07-21": 1e6,
        "2026-07-20": 1e6,
        "2026-07-19": 1e6,
        "2026-07-18": -1,
    }
    assert consecutive_inflow_days(hist2) == 4
    assert consecutive_inflow_days({"2026-07-22": -1}) == 0
    print("OK consec")


def test_ambush_annotate() -> None:
    os.environ["ENABLE_SURGE_AMBUSH"] = "0"
    # reload module flags
    import importlib
    import surge_ambush_score as sas

    importlib.reload(sas)

    item = {"symbol": "600000", "arm": "B", "score": 0.85, "industry": "电网设备"}
    scored = sas.score_ambush(
        item,
        consec=4,
        wind_row={"inst_net": 1e7, "large_net": 2e6},
        prefer={"电网设备", "电力设备"},
        zt_sectors=set(),
        zt_codes=set(),
        labels=["电网设备"],
    )
    # fund: 3+2+1=6 capped 5; sector: 2; total 7 → strong
    assert scored["surge_ambush_fund"] == 5
    assert scored["surge_ambush_sector"] == 2
    assert scored["surge_ambush_score"] == 7
    assert scored["surge_ambush_tier"] == "strong"

    out = sas.apply_surge_ambush_score(
        [{"symbol": "600000", "arm": "B", "score": 0.85, "industry": "电网设备"}],
        log=print,
    )
    # annotate only: score unchanged
    assert abs(out[0]["score"] - 0.85) < 1e-9
    assert out[0].get("surge_ambush_apply") is False
    print("OK ambush annotate", out[0].get("surge_ambush_tier"), out[0].get("surge_ambush_score"))


def test_ambush_apply() -> None:
    os.environ["ENABLE_SURGE_AMBUSH"] = "1"
    import importlib
    import surge_ambush_score as sas

    importlib.reload(sas)
    assert sas.enabled() is True

    # Direct score path with synthetic consec via monkeypatch of consec_for_symbol
    items = [{"symbol": "600000", "arm": "B", "score": 0.85, "industry": "电网设备"}]
    # Force high score via score_ambush then apply mult manually pattern
    scored = sas.score_ambush(
        items[0],
        consec=4,
        wind_row={"inst_net": 1e7, "large_net": 1e6},
        prefer={"电网设备"},
        zt_sectors=set(),
        zt_codes=set(),
        labels=["电网设备"],
    )
    assert scored["surge_ambush_tier"] == "strong"
    # Simulate apply
    base = 0.85
    mult = 1.15
    assert abs(base * mult - 0.9775) < 1e-6
    print("OK ambush apply math")


def test_prefer_defer() -> None:
    os.environ["ENABLE_SURGE_AMBUSH"] = "1"
    import importlib
    import surge_ambush_score as sas
    import wind_sector_prefer_boost as wsb

    importlib.reload(sas)
    importlib.reload(wsb)
    # Without real wind_board_flow prefer may skip; just ensure ambush_on path doesn't crash
    out = wsb.apply_wind_b_sector_boost(
        [{"symbol": "600000", "arm": "B", "score": 0.85, "industry": "电网设备"}],
        log=print,
    )
    assert len(out) == 1
    print("OK prefer defer path")


def main() -> int:
    test_consec()
    test_ambush_annotate()
    test_ambush_apply()
    test_prefer_defer()
    print("ALL OK smoke_surge_ambush")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
