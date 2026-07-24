#!/usr/bin/env python3
from market_env_gate import build_env_asof, fetch_all_index_klines, position_exposure_ladder
from permission_gate import enrich_env_with_permission, position_exposure_permission

ih = fetch_all_index_klines(lmt=200)
for d in ("2026-03-23", "2026-07-17", "2026-07-08", "2025-04-08"):
    env = enrich_env_with_permission(build_env_asof(ih, d), asof=d)
    f = env["flags"]
    p = env["permission"]
    print(
        d,
        "lad",
        position_exposure_ladder(f),
        "perm",
        position_exposure_permission(f, p),
        "crash",
        f.get("market_crash_day"),
        "up3",
        p.get("up3_count"),
        "sus",
        p.get("n_sustained_in"),
        "dead",
        p.get("rotation_dead"),
    )
