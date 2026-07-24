#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")
sys.path.insert(0, "/home/ubuntu/alphapilot")

from vm25_scorer import VM25Scorer, _bare
print("1 VM25Scorer OK", flush=True)
from backtest_v3_pipeline import fund_gate_ok, volume_gc_asof
print("2 pipeline OK", flush=True)
from backtest_v3_tradable_gated import (
    day_chg, limit_pct, max_drawdown, near_limit, settle_tradable,
)
print("3 tradable OK", flush=True)
from soft_universe_gate import apply_universe_gate
print("4 gate OK", flush=True)
from consec_inflow import load_fund_hist, consec_for_symbol
print("5 consec OK", flush=True)
from surge_ambush_score import score_ambush
print("6 ambush OK", flush=True)

print("ALL IMPORTS OK", flush=True)