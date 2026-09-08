# coding: utf-8
"""Unit smoke tests for TrackA QMT sim/live v2.42/v2.38-tpl:
  C TSDOWN next-open half-sell helper (_tsdown_new_down)
  B D8 three-condition release (_d8_three_cond_released / _d8_release_now)
  TrendState engine inline parity vs bt_research/_ts_engine.py
  _ts_last_bars drop-today-partial logic
Pure stdlib (no pandas). Run:  python _ut_tsdown_v242.py
"""
import importlib.util
import math
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

FILES = {
    "sim": os.path.join(HERE, "TrackA_track_a_qmt_full_chain_sim.py"),
    "live": os.path.join(HERE, "TrackA_track_a_qmt_full_chain_live.py"),
}
ENG = os.path.join(ROOT, "bt_research", "_ts_engine.py")

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


ENGM = load(ENG, "ts_engine_ref")

# ---------------------------------------------------------------------------
# 1) deterministic synthetic OHLCV (no randomness)
# ---------------------------------------------------------------------------
def synth(closes, up_vol_ratio=1.0):
    highs = [c * 1.006 for c in closes]
    lows = [c * 0.994 for c in closes]
    vols = [10000.0] * len(closes)
    return closes, highs, lows, vols


def make_series(up=True, n=180, step=0.004, wob=0.004):
    out = []
    x = 10.0
    sign = 1.0 if up else -1.0
    for i in range(n):
        x = x * (1.0 + sign * step) + sign * wob * math.sin(i / 3.0) * 0.5
        out.append(x)
    return out


UP_CLOSES = make_series(up=True)
DOWN_CLOSES = make_series(up=False)

# ---------------------------------------------------------------------------
# 2) engine parity: inline engine in QMT files vs bt_research/_ts_engine.py
# ---------------------------------------------------------------------------
for tag, path in FILES.items():
    M = load(path, "qmt_a_" + tag)
    ucl, uhi, ulo, uvo = synth(UP_CLOSES)
    dcl, dhi, dlo, dvo = synth(DOWN_CLOSES)
    # reference engine needs (closes, highs, lows, vols) + TS_PARAMS
    ref_u = ENGM.ts_compute(ucl, uhi, ulo, uvo, ENGM.TS_PARAMS)
    ref_d = ENGM.ts_compute(dcl, dhi, dlo, dvo, ENGM.TS_PARAMS)
    my_u = M._ts_compute(ucl, uhi, ulo, uvo)
    my_d = M._ts_compute(dcl, dhi, dlo, dvo)
    for data_name, ref, mine in [("UP", ref_u, my_u), ("DOWN", ref_d, my_d)]:
        # compare over the matched settled window
        start = next((i for i, r in enumerate(ref) if r["score"] is not None), None)
        if start is None:
            chk(tag + "_" + data_name + "_parity", False, "no settled ref")
            continue
        bad_state = bad_score = checked = 0
        for i in range(start, min(len(ref), len(mine))):
            checked += 1
            if ref[i]["state"] != mine[i]["state"]:
                bad_state += 1
            if abs((ref[i]["score"] or 0.0) - (mine[i]["score"] or 0.0)) > 0.05:
                bad_score += 1
        chk(tag + "_" + data_name + "_parity_state",
            bad_state == 0, "checked=%d bad=%d" % (checked, bad_state))
        chk(tag + "_" + data_name + "_parity_score",
            bad_score == 0, "checked=%d bad=%d" % (checked, bad_score))

# ---------------------------------------------------------------------------
# 3) helper logic with injected _ts_state_info (pure branch coverage)
# ---------------------------------------------------------------------------
def run_helper_checks(M, tag):
    inject = {}

    def fake_state_info(C, code):
        return inject["info"]

    M._ts_state_info = fake_state_info

    # -- B release: all three conditions true
    inject["info"] = {"state": "UP", "score": 72.0, "score_prev": 71.0,
                      "t3": 1.0, "t3_prev": 1.0, "state_prev": "UP",
                      "close": 12.0, "ma10": 11.5}
    chk(tag + "_rel_all_true", M._d8_three_cond_released(object(), "600000") is True)

    # score below min -> False
    inject["info"] = {"score": 54.9, "score_prev": 71.0, "t3": 1.0,
                      "state_prev": "UP", "close": 12.0, "ma10": 11.5}
    chk(tag + "_rel_score_lo", M._d8_three_cond_released(object(), "600000") is False)

    # prev score below min -> False
    inject["info"] = {"score": 72.0, "score_prev": 54.9, "t3": 1.0,
                      "state_prev": "UP", "close": 12.0, "ma10": 11.5}
    chk(tag + "_rel_scoreprev_lo", M._d8_three_cond_released(object(), "600000") is False)

    # t3 != 1.0 -> False
    inject["info"] = {"score": 72.0, "score_prev": 71.0, "t3": 0.5,
                      "state_prev": "UP", "close": 12.0, "ma10": 11.5}
    chk(tag + "_rel_t3_lo", M._d8_three_cond_released(object(), "600000") is False)

    # close <= MA10 -> False
    inject["info"] = {"score": 72.0, "score_prev": 71.0, "t3": 1.0,
                      "state_prev": "UP", "close": 11.4, "ma10": 11.5}
    chk(tag + "_rel_close_lo", M._d8_three_cond_released(object(), "600000") is False)

    # missing info -> False (stay exempt)
    inject["info"] = None
    chk(tag + "_rel_noinfo", M._d8_three_cond_released(object(), "600000") is False)

    # -- _d8_release_now one-way latch
    pos = {}
    inject["info"] = {"state": "UP", "score": 80.0, "score_prev": 79.0,
                      "t3": 1.0, "state_prev": "UP", "close": 12.0, "ma10": 11.0}
    r1 = M._d8_release_now(object(), "600000", pos, "20260908")
    chk(tag + "_release_latch_on", r1 is True and pos.get("d8_released") == "20260908",
        str(pos))
    # after latch, even a weak print must NOT re-exempt
    inject["info"] = {"state": "DOWN", "score": 30.0, "score_prev": 29.0,
                      "t3": 0.0, "state_prev": "RANGE", "close": 10.0, "ma10": 12.0}
    r2 = M._d8_release_now(object(), "600000", pos, "20260909")
    chk(tag + "_release_latched_keeps", r2 is True and pos.get("d8_released") == "20260908",
        str(pos))

    # -- _tsdown_new_down
    pos2 = {}
    inject["info"] = {"state": "DOWN", "state_prev": "RANGE", "score": 35.0,
                      "score_prev": 60.0, "t3": 0.0, "t3_prev": 0.5,
                      "close": 10.0, "ma10": 11.0}
    chk(tag + "_tsdown_fresh", M._tsdown_new_down(object(), "600000", pos2, "20260908") is True)
    chk(tag + "_tsdown_sameday_block", M._tsdown_new_down(object(), "600000", pos2, "20260908") is False,
        str(pos2))
    chk(tag + "_tsdown_latch_date", pos2.get("tsdown_fired") == "20260908", str(pos2))

    # not DOWN -> False
    pos3 = {}
    inject["info"] = {"state": "UP", "state_prev": "RANGE"}
    chk(tag + "_tsdown_up_none", M._tsdown_new_down(object(), "600000", pos3, "20260908") is False,
        str(pos3))

    # prev already DOWN (continued episode) -> False (no second fire)
    pos4 = {}
    inject["info"] = {"state": "DOWN", "state_prev": "DOWN"}
    chk(tag + "_tsdown_continuing_none", M._tsdown_new_down(object(), "600000", pos4, "20260908") is False,
        str(pos4))

    # next trading day a fresh DOWN episode may fire again
    pos5 = {"tsdown_fired": "20260908"}
    inject["info"] = {"state": "DOWN", "state_prev": "RANGE"}
    chk(tag + "_tsdown_newday_fire", M._tsdown_new_down(object(), "600000", pos5, "20260909") is True,
        str(pos5))


for tag, path in FILES.items():
    M = load(path, "qmt_a_" + tag)
    run_helper_checks(M, tag)

# ---------------------------------------------------------------------------
# 4) _ts_last_bars drops today's partial bar (sim file as proxy for both)
# ---------------------------------------------------------------------------
M = load(FILES["sim"], "qmt_a_sim_bars")
calls = {"n": 0}
call_data = {}


def fake_mde(fields, codes, period="1d", count=120, subscribe=True):
    calls["n"] += 1
    n = 66
    closes = list(UP_CLOSES[-n:])
    return {codes[0]: {"open": closes, "high": [c * 1.01 for c in closes],
                       "low": [c * 0.99 for c in closes], "close": closes,
                       "volume": [10000.0] * n}}


class FakeC:
    _ts_daily_cache = {}


def fake_mde_bound(self, fields, codes, period="1d", count=120, subscribe=True):
    calls["n"] += 1
    n = 66
    closes = list(UP_CLOSES[-n:])
    return {codes[0]: {"open": closes, "high": [c * 1.01 for c in closes],
                       "low": [c * 0.99 for c in closes], "close": closes,
                       "volume": [10000.0] * n}}


FakeC.get_market_data_ex = fake_mde_bound
res = M._ts_last_bars(FakeC(), "600000.SH")
ok = res is not None and len(res[0]) == 65
chk("sim_lastbars_drop_partial", ok, "bars=%s" % (len(res[0]) if res else None))
# cache second call no refetch
calls["n"] = 0
res2 = M._ts_last_bars(FakeC(), "600000.SH")
chk("sim_lastbars_cache", calls["n"] == 0 and res2 is res,
    "refetch=%d" % calls["n"])

# TSDOWN window / config sanity
chk("sim_tsdown_cfg", M.TSDOWN_ENABLE is True and
    M.TSDOWN_WIN_START == 9 * 60 + 31 and M.TSDOWN_WIN_END == 9 * 60 + 45)
chk("sim_d8rel_cfg", M.D8REL_SCORE_MIN == 55.0 and M.D8REL_DAYS == 2 and
    M.D8REL_T3 == 1.0)

M = load(FILES["live"], "qmt_a_live_bars")
chk("live_tsdown_cfg", M.TSDOWN_ENABLE is True and
    M.TSDOWN_WIN_START == 9 * 60 + 31 and M.TSDOWN_WIN_END == 9 * 60 + 45)
chk("live_d8rel_cfg", M.D8REL_SCORE_MIN == 55.0 and M.D8REL_DAYS == 2 and
    M.D8REL_T3 == 1.0)

print()
print("FAILED: " + str(fail) if fail else "ALL PASS")
sys.exit(1 if fail else 0)
