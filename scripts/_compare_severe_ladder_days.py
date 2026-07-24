#!/usr/bin/env python3
"""List market_severe days: legacy expo vs ladder expo (needs crash_day)."""
from market_env_gate import (
    INDEXES,
    _flags_from_indexes,
    _trend_from_klines,
    fetch_all_index_klines,
    position_exposure,
    position_exposure_legacy,
    recommend_top_n,
)

ih = fetch_all_index_klines(lmt=500)
sh = ih.get("sh_main") or []
dates = [x["date"] for x in sh if x["date"] >= "2024-01-01"]
rows = []
for d in dates:
    idxs = {}
    for k in INDEXES:
        kl = [x for x in (ih.get(k) or []) if x["date"] <= d]
        st = _trend_from_klines(kl)
        st["name"] = INDEXES[k]["name"]
        idxs[k] = st
    flags = _flags_from_indexes(idxs)
    if not flags.get("market_severe"):
        continue
    cur = position_exposure_legacy(flags)
    lad = position_exposure(flags)
    rows.append(
        {
            "date": d,
            "sh_day": idxs["sh_main"].get("day_chg"),
            "sz_day": idxs["sz_main"].get("day_chg"),
            "crash": flags.get("market_crash_day"),
            "expo_cur": cur,
            "expo_ladder": lad,
            "top_n": recommend_top_n(lad),
            "diff": lad != cur,
        }
    )

print(f"severe_days={len(rows)} ladder_differs={sum(1 for r in rows if r['diff'])}")
for r in rows:
    mark = " *" if r["diff"] else ""
    print(
        f"{r['date']} sh_day={r['sh_day']} sz_day={r['sz_day']} crash={r['crash']} "
        f"cur={r['expo_cur']} lad={r['expo_ladder']} top_n={r['top_n']}{mark}"
    )
