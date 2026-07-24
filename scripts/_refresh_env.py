#!/usr/bin/env python3
from market_env_gate import load_or_build_env

e = load_or_build_env(force=True)
p = e.get("permission") or {}
print("mode", e.get("exposure_mode"), "expo", e.get("position_exposure"))
print(
    "up3",
    p.get("up3_count"),
    "sus",
    p.get("n_sustained_in"),
    "perm_on",
    p.get("permission_on"),
    "dead",
    p.get("rotation_dead"),
)
print("flags", e.get("flags"))
