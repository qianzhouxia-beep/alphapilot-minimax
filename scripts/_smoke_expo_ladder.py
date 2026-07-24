#!/usr/bin/env python3
from market_env_gate import position_exposure, position_exposure_legacy, recommend_top_n

f = {"market_severe": True, "market_crash_day": False, "market_weak": True}
print("lad", position_exposure(f), "cur", position_exposure_legacy(f), "top", recommend_top_n(0.25))
f2 = {"market_severe": True, "market_crash_day": True}
print("nuclear", position_exposure(f2), "top", recommend_top_n(0.0))
f3 = {"market_weak": True}
print("half", position_exposure(f3), "top", recommend_top_n(0.5))
