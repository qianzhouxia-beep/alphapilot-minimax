# coding: utf-8
"""Unit tests for TrackA QMT sim v2.44 adaptive peel pullback cap.

Verifies:
  - PEEL_PB_MAX == 0.02 and the adaptive pb never exceeds it
  - low-vol default (DEF_PEEL_PB 0.015) unchanged
  - vol==None fallback unchanged
  - PEEL_MAX_STEPS / DEF_TRAIL_ARM untouched (structure unchanged)
  - live template stays UNCHANGED (still min(0.05, ...), no PEEL_PB_MAX)
  - peel is FIRST-TOUCH (no second confirmation): half-sell on the first
    bar whose pullback >= pb, then require a new high.
Pure stdlib. Run:  python _ut_peelcap_v244.py
"""
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SIM = os.path.join(HERE, "TrackA_track_a_qmt_full_chain_sim_v2.45.py")
LIVE = os.path.join(HERE, "TrackA_track_a_qmt_full_chain_live_v2.38-tpl.py")

fail = []


def chk(tag, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + tag + (" | " + extra if extra else ""))
    if not cond:
        fail.append(tag)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


sim = load(SIM, "ta_sim_v244")

chk("sim PEEL_PB_MAX == 0.02", sim.PEEL_PB_MAX == 0.02, str(sim.PEEL_PB_MAX))
chk("sim DEF_PEEL_PB == 0.015 (unchanged)", sim.DEF_PEEL_PB == 0.015, str(sim.DEF_PEEL_PB))
chk("sim DEF_TRAIL_ARM == 0.03 (unchanged)", sim.DEF_TRAIL_ARM == 0.03, str(sim.DEF_TRAIL_ARM))
chk("sim PEEL_MAX_STEPS == 2 (unchanged)", sim.PEEL_MAX_STEPS == 2, str(sim.PEEL_MAX_STEPS))


def pb_for(vol):
    """Run _adaptive_params with _annual_vol stubbed to a fixed vol."""
    orig = sim._annual_vol
    try:
        sim._annual_vol = lambda C, code: vol
        return sim._adaptive_params(None, "X.SZ")[2]
    finally:
        sim._annual_vol = orig


chk("vol=None -> default pb 0.015", pb_for(None) == 0.015, str(pb_for(None)))
chk("vol=baseline 0.30 -> 0.015", pb_for(0.30) == 0.015, str(pb_for(0.30)))
chk("vol=0.45 -> <= 0.02", pb_for(0.45) <= 0.02, str(pb_for(0.45)))
chk("vol=0.60 -> capped 0.02 (was 0.024)", pb_for(0.60) == 0.02, str(pb_for(0.60)))
chk("vol=0.80 (max) -> capped 0.02 (was 0.03)", pb_for(0.80) == 0.02, str(pb_for(0.80)))

sweep = [pb_for(v / 100.0) for v in range(10, 81)]
chk("sweep vol 0.10..0.80 -> max pb never > 0.02", max(sweep) <= 0.02,
    "max=%.4f" % max(sweep))


def old_pb(vol):
    dev = vol - sim.VOL_BASELINE
    return round(min(0.05, sim.DEF_PEEL_PB + dev * 0.03), 3)


unchanged = all(abs(pb_for(v / 100.0) - old_pb(v / 100.0)) < 1e-9
                for v in range(10, 81) if old_pb(v / 100.0) <= 0.02)
only_lowered = all(pb_for(v / 100.0) <= old_pb(v / 100.0) + 1e-9
                   for v in range(10, 81))
chk("v2.44 only changes pb when the old value exceeded 2%", unchanged)
chk("v2.44 never raises pb above the old value", only_lowered)
chk("vol=0.45 old==new (0.019, below cap)", pb_for(0.45) == old_pb(0.45),
    "new=%.4f old=%.4f" % (pb_for(0.45), old_pb(0.45)))

# --- live template untouched ---
src = open(LIVE, "r", encoding="ascii").read()
chk("live has NO PEEL_PB_MAX", "PEEL_PB_MAX" not in src)
chk("live still min(0.05, DEF_PEEL_PB ...)", "min(0.05, DEF_PEEL_PB" in src)


# --- structural: peel sells on FIRST touch, then demands a new high ---
# Mirror the shipped condition on the sim source to lock the semantics.
ssrc = open(SIM, "r", encoding="ascii").read()
chk("peel requires not awaiting_new_high (new-high gate present)",
    'not pos.get("awaiting_new_high")' in ssrc)
chk("peel trigger is pbk >= pb (first touch, no 2nd bar confirm)",
    "if pbk >= pb * 100:" in ssrc)
chk("peel re-arms only on a strictly new high",
    'pos.get("peak", 0) > pos.get("peel_peak_snapshot", 0) + 1e-9' in ssrc)
chk("peel half then clear at PEEL_MAX_STEPS",
    "n >= PEEL_MAX_STEPS or" in ssrc)

print()
if fail:
    print("FAILED %d: %s" % (len(fail), fail))
    raise SystemExit(1)
print("ALL PASS")
