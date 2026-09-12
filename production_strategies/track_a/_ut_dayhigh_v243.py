# coding: utf-8
"""Unit tests for TrackA QMT sim v2.43 conditional P2 day-high gate.

Verifies:
  - _p2_day_high_max_for: low-base relaxed, elevated unchanged, missing-safe
  - _p2_day_high_ok: cap honoured
  - 002636 09-10 motivating case now passes under low-base cap 1.00
  - DEFAULT (DAYHIGH_CONDITIONAL off) restores the flat 0.85 behaviour
  - live template stays UNCHANGED (no conditional gate)
Pure stdlib. Run:  python _ut_dayhigh_v243.py
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


sim = load(SIM, "ta_sim_v243")

# --- 1) cap selection by multi-day position ---
LOWBASE = {"ma60_pos": -0.113, "up_low": 0.482, "rank": 3}      # 002636 09-10
ELEVATED = {"ma60_pos": 0.326, "up_low": 0.495, "rank": 1}      # 002059
MID_UP_LOW = {"ma60_pos": -0.05, "up_low": 0.60, "rank": 4}     # below MA60 but late in rebound
chk("sim default CONF_DAY_HIGH_MAX==0.85", sim.CONF_DAY_HIGH_MAX == 0.85,
    str(sim.CONF_DAY_HIGH_MAX))
chk("sim lowbase cap == 1.00", sim.CONF_DAY_HIGH_MAX_LOWBASE == 1.00,
    str(getattr(sim, "CONF_DAY_HIGH_MAX_LOWBASE", None)))
chk("lowbase item -> relaxed cap",
    sim._p2_day_high_max_for(LOWBASE) == sim.CONF_DAY_HIGH_MAX_LOWBASE,
    str(sim._p2_day_high_max_for(LOWBASE)))
chk("elevated item -> default cap",
    sim._p2_day_high_max_for(ELEVATED) == sim.CONF_DAY_HIGH_MAX,
    str(sim._p2_day_high_max_for(ELEVATED)))
chk("below-MA60 but late rebound -> default cap (up_low>=0.5)",
    sim._p2_day_high_max_for(MID_UP_LOW) == sim.CONF_DAY_HIGH_MAX,
    str(sim._p2_day_high_max_for(MID_UP_LOW)))
chk("missing fields -> default cap", sim._p2_day_high_max_for({}) == sim.CONF_DAY_HIGH_MAX)
chk("None item -> default cap", sim._p2_day_high_max_for(None) == sim.CONF_DAY_HIGH_MAX)
chk("boundary ma60_pos==0.0 -> default",
    sim._p2_day_high_max_for({"ma60_pos": 0.0, "up_low": 0.1}) == sim.CONF_DAY_HIGH_MAX)
chk("boundary up_low==0.5 -> default",
    sim._p2_day_high_max_for({"ma60_pos": -0.1, "up_low": 0.5}) == sim.CONF_DAY_HIGH_MAX)

# --- 2) cap honoured by _p2_day_high_ok ---
chk("rng<=0 always ok", sim._p2_day_high_ok(10.0, 10.0, 10.0, 0.85) is True)
chk("pos 0.5 <= 0.85 ok", sim._p2_day_high_ok(10.5, 11.0, 10.0, 0.85) is True)
chk("pos 0.9 > 0.85 veto", sim._p2_day_high_ok(10.9, 11.0, 10.0, 0.85) is False)
chk("pos 0.9 <= 1.00 ok", sim._p2_day_high_ok(10.9, 11.0, 10.0, 1.00) is True)

# --- 3) 002636 motivating 10:00 bar: day_low=68.47 high=71.75 close=71.69 ---
pos = (71.69 - 68.47) / (71.75 - 68.47)
chk("002636 pos ~0.982", abs(pos - 0.982) < 0.002, "pos=%.3f" % pos)
chk("002636 old flat cap 0.85 -> REJECTED", sim._p2_day_high_ok(71.69, 71.75, 68.47, 0.85) is False)
chk("002636 low-base cap -> NOW PASSES",
    sim._p2_day_high_ok(71.69, 71.75, 68.47, sim._p2_day_high_max_for(LOWBASE)) is True)

# --- 4) DEFAULT off restores flat behaviour ---
sim.DAYHIGH_CONDITIONAL = False
chk("conditional off -> lowbase item falls back to 0.85",
    sim._p2_day_high_max_for(LOWBASE) == 0.85)
sim.DAYHIGH_CONDITIONAL = True

# --- 5) live template untouched (still flat, no conditional symbols) ---
src = open(LIVE, "r", encoding="ascii").read()
chk("live has NO DAYHIGH_CONDITIONAL", "DAYHIGH_CONDITIONAL" not in src)
chk("live CONF_DAY_HIGH_MAX still 0.85",
    "CONF_DAY_HIGH_MAX = 0.85" in src)
live = load(LIVE, "ta_live_v238")
chk("live _p2_day_high_ok takes no cap (3 args)",
    live._p2_day_high_ok(71.69, 71.75, 68.47) is False)

print()
if fail:
    print("FAILED %d: %s" % (len(fail), fail))
    raise SystemExit(1)
print("ALL PASS")
