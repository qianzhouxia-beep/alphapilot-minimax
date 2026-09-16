"""Unit tests: Track A v2.49 abr caliber guard (2026-09-16).

Run: /Users/AlphaPilot/.venv/bin/python _ut_abr_caliber_v249.py
"""
import importlib.util
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.join(HERE, "TrackA_track_a_qmt_full_chain_sim_v2.49.py")

spec = importlib.util.spec_from_file_location("a249", MOD)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

fails = []


def chk(name, got, want):
    ok = got == want
    print(("  [PASS] " if ok else "  [FAIL] ") + name + " got=" + repr(got)
          + " want=" + repr(want))
    if not ok:
        fails.append(name)


print("== _abr_in_range ==")
chk("0.5 in range", m._abr_in_range(0.5), True)
chk("0 in range", m._abr_in_range(0.0), True)
chk("1 in range", m._abr_in_range(1.0), True)
chk("1.5 out", m._abr_in_range(1.5), False)
chk("-0.1 out", m._abr_in_range(-0.1), False)
chk("nan out", m._abr_in_range(float("nan")), False)
chk("None out", m._abr_in_range(None), False)

print("== _abr_verdict (ABR_CALIBRATED_SRC_ONLY=True) ==")
m.ABR_CALIBRATED_SRC_ONLY = True
chk("None -> pass", m._abr_verdict(None, "none"), "pass")
chk("feed low -> skip", m._abr_verdict(0.40, "feed"), "skip")
chk("feed 0.52 -> pass", m._abr_verdict(0.52, "feed"), "pass")
chk("feed 0.60 -> pass", m._abr_verdict(0.60, "feed"), "pass")
chk("l1 low -> open_uncal", m._abr_verdict(0.40, "l1"), "open_uncal")
chk("l1 0.60 -> pass", m._abr_verdict(0.60, "l1"), "pass")
chk("feed oob -> open_oob", m._abr_verdict(1.5, "feed"), "open_oob")
chk("feed neg -> open_oob", m._abr_verdict(-0.2, "feed"), "open_oob")
chk("nan -> open_oob", m._abr_verdict(float("nan"), "feed"), "open_oob")

print("== _abr_verdict (ABR_CALIBRATED_SRC_ONLY=False: old behavior) ==")
m.ABR_CALIBRATED_SRC_ONLY = False
chk("l1 low -> skip", m._abr_verdict(0.40, "l1"), "skip")
chk("oob still open", m._abr_verdict(1.5, "l1"), "open_oob")

print("===== failed=%d =====" % len(fails))
raise SystemExit(1 if fails else 0)
