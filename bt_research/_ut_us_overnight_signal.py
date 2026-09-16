#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for scripts/ingest_us_daily.py signal alignment (v1.1, 2026-09-16).

Reproduces the 2026-09-16 incident: cn 09-16's expected US session is 09-15, but
the cache only had through 09-14 (Sina lag). v1.1 must mark the row stale and
NEVER forward-roll to us 09-14.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import ingest_us_daily as I  # noqa: E402

FAIL = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else " :: " + str(detail)))
    if not cond:
        FAIL.append(name)


def write(d, sym, rows):
    with open(os.path.join(d, f"{sym}.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f)


def row(sym, date, close):
    return {"symbol": sym.upper(), "date": date, "open": close, "high": close,
            "low": close, "close": close, "volume": 1.0}


def main():
    # expected-session calendar checks
    check("expected 09-16 -> 09-15 (Wed->Tue)", I.expected_us_session("2026-09-16") == "2026-09-15",
          I.expected_us_session("2026-09-16"))
    check("expected 09-15 -> 09-14", I.expected_us_session("2026-09-15") == "2026-09-14",
          I.expected_us_session("2026-09-15"))
    check("weekend cn 09-13 -> Fri 09-11", I.expected_us_session("2026-09-13") == "2026-09-11",
          I.expected_us_session("2026-09-13"))
    check("post-Labor cn 09-08 -> 09-04 (09-07 holiday)", I.expected_us_session("2026-09-08") == "2026-09-04",
          I.expected_us_session("2026-09-08"))
    check("07-03 is a US holiday", not I.is_us_session(__import__("datetime").date(2026, 7, 3)))

    dates = ["2026-09-04", "2026-09-08", "2026-09-09", "2026-09-10", "2026-09-11", "2026-09-14"]
    closes = {"2026-09-11": 218.29, "2026-09-14": 210.96, "2026-09-15": 212.17}
    with tempfile.TemporaryDirectory() as d:
        write(d, "nvda", [row("nvda", x, closes.get(x, 100.0)) for x in dates])
        write(d, "qqq", [row("qqq", x, closes.get(x, 100.0)) for x in dates])

        cn = ["2026-09-11", "2026-09-13", "2026-09-14", "2026-09-15", "2026-09-16"]
        out = {r["cn_date"]: r for r in I.signal_for_cn_dates(cn, d)}

        # incident: 09-16 expected 09-15 not in cache -> stale, NOT us 09-14
        r16 = out["2026-09-16"]
        check("09-16 stale flag", r16["g1_flag"] == "stale", r16)
        check("09-16 us_date=09-15 (expected, not rolled)", r16["us_date"] == "2026-09-15", r16)
        check("09-16 rets null", r16["nvda_ret"] is None and r16["qqq_ret"] is None, r16)
        check("09-16 not polluted with 09-14 value",
              r16["nvda_ret"] is None and r16["g1_flag"] != "ai_rebound_watch", r16)

        # 09-15 still correct (09-14 present; real 09-14 = -3.36% -> rebound watch)
        r15 = out["2026-09-15"]
        check("09-15 -> us 09-14", r15["us_date"] == "2026-09-14"
              and r15["g1_flag"] == "ai_rebound_watch", r15)

        # weekend row maps to Friday, not stale
        r13 = out["2026-09-13"]
        check("09-13 weekend -> us 09-11 usable", r13["us_date"] == "2026-09-11"
              and r13["g1_flag"] != "stale", r13)

        # now add 09-15 -> normal + backfilled annotation
        write(d, "nvda", [row("nvda", x, closes.get(x, 100.0)) for x in dates + ["2026-09-15"]])
        write(d, "qqq", [row("qqq", x, closes.get(x, 100.0)) for x in dates + ["2026-09-15"]])
        notes = {"2026-09-16": "Sina lag at 05:30; re-ingested 2026-09-16"}
        out2 = {r["cn_date"]: r for r in I.signal_for_cn_dates(cn, d, notes)}
        r16b = out2["2026-09-16"]
        check("09-16 after reingest -> us 09-15", r16b["us_date"] == "2026-09-15", r16b)
        check("09-16 ret ~ +0.5734%", abs(r16b["nvda_ret"] - (212.17 / 210.96 - 1)) < 1e-6, r16b)
        check("09-16 flag none (correct caliber)", r16b["g1_flag"] == "none", r16b)
        check("09-16 backfilled=true", r16b.get("backfilled") is True and "backfill_note" in r16b, r16b)

    print("\n" + ("ALL PASS" if not FAIL else f"{len(FAIL)} FAILED: {FAIL}"))
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
