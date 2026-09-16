#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for scripts/pull_lhb_history.py v1.2 (2026-09-17).

Reproduces the lhb_stale recurrence: trading-day empty responses (not yet
published) used to be marked fetched_ok => skipped forever. v1.2 must NOT
confirm a kline trading day on an empty response, and must self-heal poisoned
entries.
"""
import os
import sys
import tempfile

# module does os.chdir(ALPHAPILOT_ROOT) at import; point it at a scratch dir
os.environ.setdefault("ALPHAPILOT_ROOT", tempfile.mkdtemp(prefix="lhb_ut_"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import pull_lhb_history as P  # noqa: E402

FAIL = []
KD = {"2026-09-10", "2026-09-11", "2026-09-14", "2026-09-15", "2026-09-16"}
KMAX = "2026-09-16"
TODAY = "2026-09-17"


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else " :: " + str(detail)))
    if not cond:
        FAIL.append(name)


def conf(d, kd=KD, km=KMAX, td=TODAY):
    return P.is_confirmed_non_trading(d, kd, km, td)


def main():
    # trading days must NEVER be confirmed on empty (the poisoning)
    check("09-15 trading day not confirmed", not conf("2026-09-15"))
    check("09-16 trading day not confirmed", not conf("2026-09-16"))
    # today (newer than kline max) not confirmed -> retried, fixes 09-17 pre-mark
    check("today 09-17 not confirmed", not conf("2026-09-17"))
    # weekend / holiday older than kline max -> confirmed
    check("Sat 09-12 confirmed non-trading", conf("2026-09-12"))
    check("Sun 09-13 confirmed non-trading", conf("2026-09-13"))
    # old non-trading day
    check("older gap day 09-07 confirmed", conf("2026-09-07"))

    # fallback (no kline calendar): weekday not confirmed, weekend confirmed
    check("no-cal weekday 09-16 not confirmed", not conf("2026-09-16", set(), None, TODAY))
    check("no-cal Sat 09-12 confirmed", conf("2026-09-12", set(), None, TODAY))
    check("no-cal old 09-01 confirmed", conf("2026-09-01", set(), None, TODAY))

    # empty-response classification
    check("NoneType is empty_ok", P._is_empty_response_err("'NoneType' object is not subscriptable"))
    check("network err not empty_ok", not P._is_empty_response_err("HTTPSConnectionPool timeout"))

    # calendar loads from a real-ish parquet if present; otherwise soft-fails
    ds, mx = P.load_kline_calendar()
    check("calendar soft-fails to (set,None) or loads", isinstance(ds, set), (type(ds), mx))
    if ds:
        check("calendar max is ISO", len(str(mx)) == 10, mx)
        check("calendar contains 09-16-ish", mx >= "2026-09-16", mx)

    print("\n" + ("ALL PASS" if not FAIL else f"{len(FAIL)} FAILED: {FAIL}"))
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
