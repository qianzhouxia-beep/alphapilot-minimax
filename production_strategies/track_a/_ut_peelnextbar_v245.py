# coding: utf-8
"""Unit tests for TrackA QMT sim v2.45 NEXT-BAR peel confirmation.

Verifies:
  - PEEL_NEXT_BAR_CONFIRM is True; PEEL_PB_MAX==0.02 / DEF_TRAIL_ARM==0.03 /
    PEEL_MAX_STEPS==2 unchanged (v2.44 surface intact)
  - the confirm branch exists in source (peel_pending / peel_touch_bar gate /
    the PEEL_NEXT_BAR_CONFIRM=False fallback to exact v2.44 first-touch)
  - BEHAVIOURAL: drives the REAL _check_sell through the peel block with stubs:
      * bar 1 breach only ARMS (no sell)
      * a LATER bar (index advances) CONFIRMS -> existing half-sell path,
        peel_count / awaiting_new_high / peel_peak_snapshot preserved
      * shares<200 -> clear path on the confirming bar
      * a strictly NEW high invalidates a pending touch
      * PEEL_NEXT_BAR_CONFIRM=False -> immediate first-touch sell (v2.44)
  - live template stays UNCHANGED (no PEEL_NEXT_BAR_CONFIRM, still
    min(0.05, DEF_PEEL_PB ...), still v2.38-tpl)
Pure stdlib. Run:  python _ut_peelnextbar_v245.py
"""
import importlib.util
import os
import types

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


sim = load(SIM, "ta_sim_v245")

# ------------------------------------------------------------------ constants
chk("sim PEEL_NEXT_BAR_CONFIRM is True",
    sim.PEEL_NEXT_BAR_CONFIRM is True, str(sim.PEEL_NEXT_BAR_CONFIRM))
chk("sim PEEL_PB_MAX == 0.02 (v2.44 unchanged)",
    sim.PEEL_PB_MAX == 0.02, str(sim.PEEL_PB_MAX))
chk("sim DEF_PEEL_PB == 0.015 (unchanged)", sim.DEF_PEEL_PB == 0.015,
    str(sim.DEF_PEEL_PB))
chk("sim DEF_TRAIL_ARM == 0.03 (unchanged)", sim.DEF_TRAIL_ARM == 0.03,
    str(sim.DEF_TRAIL_ARM))
chk("sim PEEL_MAX_STEPS == 2 (unchanged)", sim.PEEL_MAX_STEPS == 2,
    str(sim.PEEL_MAX_STEPS))

# ------------------------------------------------------------------ bar clock
chk("_closed_5m_bars visible from module", callable(getattr(sim, "_closed_5m_bars", None)))
chk("_closed_5m_bars(10:00) == 6", sim._closed_5m_bars(10 * 60) == 6,
    str(sim._closed_5m_bars(10 * 60)))
chk("_closed_5m_bars(10:05) == 7", sim._closed_5m_bars(10 * 60 + 5) == 7,
    str(sim._closed_5m_bars(10 * 60 + 5)))
chk("_closed_5m_bars(10:05) > (10:00) (bar index advances)",
    sim._closed_5m_bars(10 * 60 + 5) > sim._closed_5m_bars(10 * 60))

# ------------------------------------------------------------------ source
ssrc = open(SIM, "r", encoding="ascii").read()
chk("source has peel_pending state", "peel_pending" in ssrc)
chk("source has later-bar confirm gate",
    'current_bar_index > pos.get("peel_touch_bar"' in ssrc)
chk("source has toggle branch for PEEL_NEXT_BAR_CONFIRM",
    "if PEEL_NEXT_BAR_CONFIRM:" in ssrc)
chk("source keeps v2.44 first-touch fallback branch",
    "# v2.44 behaviour (immediate sell on first touch)." in ssrc)
chk("source invalidates pending on a strictly new high",
    'peak > pos.get("peel_touch_peak"' in ssrc)
chk("source arms with peel_touch_bar / peel_touch_peak",
    'pos["peel_touch_bar"] = current_bar_index' in ssrc
    and 'pos["peel_touch_peak"] = peak' in ssrc)

# ---------------------------------------------------- behavioural driver (real _check_sell)
_STUBBED = ["_get_quote", "_get_prev_close", "_adaptive_params", "_weak_regime",
            "_tsdown_new_down", "_wyckoff_holding_bc", "_day_vwap",
            "_save_pos_state", "_do_sell", "_do_sell_half", "_observe_entry"]


def make_pos(buy_price=100.0, peak=105.2, shares=1000, peel_count=None):
    pos = {"buy_price": buy_price, "shares": shares, "can_use": shares,
           "buy_date": "20260909", "peak": peak}
    if peel_count is not None:
        pos["peel_count"] = peel_count
    return pos


def drive(pos, price, now_min, confirm=True):
    """Call the REAL _check_sell once for one holding, with all pre-peel guards
    stubbed. Returns (position_map, calls) where calls records sell reasons."""
    sim.PEEL_NEXT_BAR_CONFIRM = confirm
    C = types.SimpleNamespace(position_map={"600000.SH": pos}, stop_watch={})
    calls = {"full": [], "half": []}

    saved = {}
    for n in _STUBBED:
        saved[n] = getattr(sim, n)

    def fake_sell(C_, code, p, px, reason):
        calls["full"].append(reason)
        if "peel_clear" in reason:
            C_.position_map.pop(code, None)

    sim._get_quote = lambda C_, code: (price, price, price, price)
    sim._get_prev_close = lambda C_, code: None
    sim._adaptive_params = lambda C_, code: (-0.10, 0.03, 0.015)
    sim._weak_regime = lambda C_, today_: False
    sim._tsdown_new_down = lambda C_, code, p, today_: False
    sim._wyckoff_holding_bc = lambda C_, code, pk: False
    sim._day_vwap = lambda C_, code: None
    sim._save_pos_state = lambda C_: None
    sim._do_sell = fake_sell
    sim._do_sell_half = lambda C_, code, p, px, reason: calls["half"].append(reason)
    sim._observe_entry = lambda code: None
    try:
        sim._check_sell(C, None, now_min, "20260910")
    finally:
        for n in _STUBBED:
            setattr(sim, n, saved[n])
    return C.position_map, calls


# --- A) first breach only arms; a LATER bar confirms the half-sell ---
pos = make_pos()                      # cost 100, peak 105.2, ret 3.5%, pbk 1.62%
pm, c1 = drive(pos, 103.5, 10 * 60)
chk("A bar1: no sell on first breach", c1["full"] == [] and c1["half"] == [],
    str(c1))
chk("A bar1: peel_pending set", pos.get("peel_pending") is True)
chk("A bar1: peel_touch_bar == 6", pos.get("peel_touch_bar") == 6,
    str(pos.get("peel_touch_bar")))
chk("A bar1: peel_touch_peak captured", abs(pos.get("peel_touch_peak", 0) - 105.2) < 1e-9,
    str(pos.get("peel_touch_peak")))
chk("A bar1: peel_count still 0", (pos.get("peel_count") or 0) == 0)

pm, c2 = drive(pos, 103.5, 10 * 60 + 5)   # bar index 7 > 6 -> confirm
chk("A bar2: confirmed -> exactly one half-sell",
    len(c2["half"]) == 1 and c2["full"] == [], str(c2))
chk("A bar2: half-sell reason is peel_half1",
    c2["half"] and c2["half"][0].startswith("peel_half1"), str(c2["half"]))
chk("A bar2: peel_count -> 1", pos.get("peel_count") == 1)
chk("A bar2: awaiting_new_high set (re-arm gate preserved)",
    pos.get("awaiting_new_high") is True)
chk("A bar2: peel_peak_snapshot == armed peak",
    abs(pos.get("peel_peak_snapshot", 0) - 105.2) < 1e-9,
    str(pos.get("peel_peak_snapshot")))
chk("A bar2: peel_pending cleared after confirm", pos.get("peel_pending") is False)

# --- B) shares < 200 -> clear path on the confirming bar ---
posB = make_pos(shares=100)
pmB, cB1 = drive(posB, 103.5, 10 * 60)
chk("B bar1: still only arms (shares<200 not sold yet)",
    cB1["full"] == [] and posB.get("peel_pending") is True, str(cB1))
pmB, cB2 = drive(posB, 103.5, 10 * 60 + 5)
chk("B bar2: clear path fires peel_clear",
    len(cB2["full"]) == 1 and cB2["full"][0].startswith("peel_clear"), str(cB2))
chk("B bar2: position popped out of position_map", "600000.SH" not in pmB,
    str(list(pmB)))

# --- C) a strictly new high invalidates a pending touch ---
posC = make_pos()
drive(posC, 103.5, 10 * 60)                 # arm at bar 6
chk("C pre: pending armed", posC.get("peel_pending") is True
    and posC.get("peel_touch_bar") == 6)
pmC, cC = drive(posC, 106.0, 10 * 60 + 5)   # new high 106 > 105.2
chk("C new high: no sell", cC["full"] == [] and cC["half"] == [], str(cC))
chk("C new high: pending invalidated", posC.get("peel_pending") is False,
    str(posC.get("peel_pending")))
chk("C new high: peak advanced", abs(posC.get("peak", 0) - 106.0) < 1e-9,
    str(posC.get("peak")))

# --- D) toggle OFF restores exact v2.44 first-touch behaviour ---
posD = make_pos()
pmD, cD = drive(posD, 103.5, 10 * 60, confirm=False)
chk("D toggle off: sells half on the FIRST touch",
    len(cD["half"]) == 1 and cD["full"] == [], str(cD))
chk("D toggle off: reason peel_half1", cD["half"] and cD["half"][0].startswith("peel_half1"))
chk("D toggle off: no pending state armed", not posD.get("peel_pending"))

# --- E) same-bar double breach must NOT confirm (index not advancing) ---
posE = make_pos()
drive(posE, 103.5, 10 * 60)                 # bar 6
pmE, cE = drive(posE, 103.5, 10 * 60)       # bar 6 again
chk("E same bar: still no sell (needs a LATER bar)",
    cE["full"] == [] and cE["half"] == [], str(cE))
chk("E same bar: still pending", posE.get("peel_pending") is True)
chk("E same bar: touch bar unchanged", posE.get("peel_touch_bar") == 6)

sim.PEEL_NEXT_BAR_CONFIRM = True  # restore default

# --- live template untouched ---
lsrc = open(LIVE, "r", encoding="ascii").read()
chk("live has NO PEEL_NEXT_BAR_CONFIRM", "PEEL_NEXT_BAR_CONFIRM" not in lsrc)
chk("live still min(0.05, DEF_PEEL_PB ...)", "min(0.05, DEF_PEEL_PB" in lsrc)
chk("live still v2.38-tpl banner", "v2.38-tpl" in lsrc)
chk("live has NO peel_pending", "peel_pending" not in lsrc)

print()
if fail:
    print("FAILED %d: %s" % (len(fail), fail))
    raise SystemExit(1)
print("ALL PASS")
