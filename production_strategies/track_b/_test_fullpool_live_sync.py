#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline mock test for Track B fullpool_live sync (v1.2):
QMT LIVE + TDX SIM now behave like QMT SIM after 09:36.

Verifies:
  1. QMT LIVE: CALL_DATA_CUTOFF defined; _live_pool_survivors maps server rows;
     _p2_gate live branch trusts server money_flow_pass; _check_buy decision
     point is LIVE_FULLPOOL_MIN (09:36), not 09:35.
  2. QMT LIVE: _load_fullpool prefers .fullpool_live.json after 09:36, falls
     back to classic before 09:36.
  3. TDX SIM: pure-function pieces (_live_pool_survivors, _p2_gate live
     branch) behave the same. (tqcenter import not available -> load module
     textually and exec only the target functions.)
"""
import importlib.util
import sys
import types
from types import SimpleNamespace
from unittest.mock import patch

LIVE_MOD = r"C:\Users\elvisq\Projects\alphapilot\production_strategies\track_b\TrackB_track_b_qmt_auction_live.py"
TDX_MOD = r"C:\Users\elvisq\Projects\alphapilot\production_strategies\track_b\TrackB_track_b_tdx_auction_sim.py"

# ---------------- load QMT LIVE module ----------------
spec = importlib.util.spec_from_file_location("tb_live", LIVE_MOD)
lm = importlib.util.module_from_spec(spec)
sys.modules["tb_live"] = lm
spec.loader.exec_module(lm)

PASSED = []
FAILED = []

def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} {detail}")


def make_C():
    return SimpleNamespace(
        run_count=0, current_date="20260817", sent_today=set(),
        position_map={}, scores_cache={}, cand_cache={},
        fullpool_cache={}, stop_watch={}, _last_resync=0, _last_univ=0,
        _last_remote_fetch=0, _last_pos_count=-1, _univ_codes=[],
        _univ_dirty=True,
        _gap_cache={}, _sector_gap_mean={}, _sector_stock_cnt={},
        _p1_survivors=[], _top2_fired=False, _auction_done=False,
        _gate_dump_done=False, live_pool_active=False, _live_surv_ready=False,
        _sector_members_cache={}, _snap_day="", score_dir=r"C:\alphapilot\scores",
        trade_log=[], _order_locks_cache={},
    )


def live_rows():
    rows = []
    for i in range(6):
        rows.append({
            "symbol": f"{600000+i:06d}.SH", "name": f"stk{i}",
            "rank": i + 1, "industry_l1": "半导体",
            "score": 1.0 - i * 0.01, "score_0500": 1.0 - i * 0.01,
            "money_flow_pass": i < 3, "research_tier": "s1",
            "main_net_5d": 1e7, "active_buy_ratio": 0.6,
        })
    return rows


def run():
    lm.get_trade_detail_data = lambda *a, **k: []
    lm.passorder = lambda *a, **k: 0
    lm.ORDER_LOCK_FILE = r"C:\alphapilot\_ut_live_order_locks.json"
    lm.TRADE_LOG = r"C:\alphapilot\_ut_live_trades.json"
    lm.GATE_LOG = r"C:\alphapilot\_ut_live_gate.json"
    import json, os
    os.makedirs(r"C:\alphapilot", exist_ok=True)
    with open(lm.ORDER_LOCK_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f)

    # ---- 1. constants ----
    print("\n== 1. LIVE constants ==")
    check("CALL_DATA_CUTOFF defined (=09:30)",
          lm.CALL_DATA_CUTOFF == 9 * 60 + 30, str(getattr(lm, "CALL_DATA_CUTOFF", None)))
    check("LIVE_FULLPOOL_MIN = 09:36", lm.LIVE_FULLPOOL_MIN == 9 * 60 + 36)
    check("USE_SERVER_GATES True", lm.USE_SERVER_GATES is True)

    # ---- 2. _live_pool_survivors mapping ----
    print("\n== 2. LIVE _live_pool_survivors ==")
    pool = live_rows()
    surv = lm._live_pool_survivors(SimpleNamespace(), pool)
    check("6 survivors kept", len(surv) == 6, f"n={len(surv)}")
    check("money_flow_pass carried", [s["money_flow_pass"] for s in surv] ==
          [True, True, True, False, False, False])
    check("score from server score", surv[0]["score"] == 1.0)
    check("rank preserved", surv[2]["rank"] == 3)

    # ---- 3. _p2_gate live branch ----
    print("\n== 3. LIVE _p2_gate live branch ==")
    C = make_C()
    C.live_pool_active = True
    with patch.object(lm, "_get_active_buy_ratio", return_value=0.6):
        gated = lm._p2_gate(C, surv, 9 * 60 + 40)
    check("live gate trusts server pass (3 pass)", 
          sum(1 for g in gated if g.get("money_pass")) == 3)
    check("live gate notes srv_pass/srv_fail",
          "srv_pass" in gated[0]["gate_notes"] and "srv_fail" in gated[3]["gate_notes"])
    check("live gate sort pass-first",
          [g["money_pass"] for g in gated] == [True, True, True, False, False, False])

    # ---- 4. _load_fullpool prefers live after 09:36 ----
    print("\n== 4. LIVE _load_fullpool routing ==")
    # before 09:36 -> classic
    with patch.object(lm, "datetime") as dt:
        dt.now.return_value.hour = 9
        dt.now.return_value.minute = 30
        with patch.object(lm, "_load_fullpool_classic", return_value=["x"]):
            r = lm._load_fullpool(C, "20260817")
            check("09:30 routes to classic", r == ["x"])
    # after 09:36 -> live first
    with patch.object(lm, "datetime") as dt:
        dt.now.return_value.hour = 9
        dt.now.return_value.minute = 40
        with patch.object(lm, "_load_fullpool_classic", return_value=["classic"]), \
             patch.object(lm, "_load_fullpool_file", return_value=pool):
            r = lm._load_fullpool(C, "20260817")
            check("09:40 routes to live pool", r is pool and C.live_pool_active is True)
    # live missing -> classic fallback
    with patch.object(lm, "datetime") as dt:
        dt.now.return_value.hour = 9
        dt.now.return_value.minute = 40
        with patch.object(lm, "_load_fullpool_classic", return_value=["classic"]), \
             patch.object(lm, "_load_fullpool_file", return_value=None):
            r = lm._load_fullpool(C, "20260817")
            check("09:40 live missing -> classic fallback", r == ["classic"])

    # ---- 5. _check_buy decision point = 09:36 ----
    print("\n== 5. LIVE _check_buy decision point ==")
    C = make_C()
    C.live_pool_active = True
    # 09:35 should NOT decide (live mode waits for 09:36)
    with patch.object(lm, "_load_fullpool", return_value=pool), \
         patch.object(lm, "get_trade_detail_data",
                      return_value=[SimpleNamespace(m_dAvailable=1000000,
                                                    m_dBalance=2000000)]):
        lm._check_buy(C, None, 9 * 60 + 35, "20260817", pool)
        check("09:35 no decision (waits for live pool)", len(C.position_map) == 0)
    # 09:36 with live_pool_active -> live override + buy
    C2 = make_C()
    C2.live_pool_active = True
    with patch.object(lm, "_load_fullpool", return_value=pool), \
         patch.object(lm, "_live_pool_survivors", return_value=[
             {"code": "600000.SH", "symbol": "600000.SH", "name": "stk0",
              "rank": 1, "industry_l1": "半导体", "score_0500": 1.0,
              "score": 1.0, "money_flow_pass": True, "research_tier": "s1",
              "active_buy_ratio": 0.6}]), \
         patch.object(lm, "_p2_decide", return_value=(23.0, "dyn_confirm")), \
         patch.object(lm, "_p2_gate", lambda C, s, n: s), \
         patch.object(lm, "get_trade_detail_data",
                      return_value=[SimpleNamespace(m_dAvailable=1000000,
                                                    m_dBalance=2000000)]), \
         patch.object(lm, "passorder", return_value=0), \
         patch.object(lm, "_dump_gate", return_value=None):
        lm._check_buy(C2, None, 9 * 60 + 36, "20260817", pool)
        check("09:36 live override + buy", "600000.SH" in C2.position_map)

    # ---- 6. TDX SIM pure-function parity ----
    print("\n== 6. TDX SIM live pieces ==")
    # Load TDX module textually, exec only needed functions with stub deps.
    with open(TDX_MOD, "r", encoding="utf-8") as f:
        src = f.read()
    tm = types.ModuleType("tb_tdx_stub")
    # minimal stubs so _p2_gate/_live_pool_survivors/_load_fullpool run
    tm.ST = {
        "live_pool_active": True, "live_surv_ready": False,
        "last_remote_fetch": 0, "last_pool_n": None,
    }
    tm.SCORE_DIR = r"C:\alphapilot\scores"
    tm.REMOTE_SCORE_BASE = "http://150.158.100.236/qmt_scores"
    tm.REMOTE_TIMEOUT = 8
    tm.REMOTE_FETCH_SEC = 60
    tm.USE_SERVER_GATES = True
    tm.LIVE_FULLPOOL_MIN = 9 * 60 + 36
    tm.GATE_START_MIN = 9 * 60 + 30
    tm.MIN_ACTIVE_BUY = 0.52
    tm.MIN_TURNOVER = 2.0
    tm.MAX_TURNOVER = 35.0
    tm.MIN_VOL_RATIO = 0.8
    tm.MAX_DROP_PCT = -5.0
    tm.ALLOW_STAR = True
    tm.ALLOW_CHINEXT = True
    tm.ALLOW_BSE = True
    tm.log = lambda *a, **k: None
    tm._board_allowed = lambda code: True
    tm._get_active_buy_ratio = lambda code: 0.6
    tm._get_turnover = lambda code: 5.0
    tm._get_volume_ratio = lambda code: 1.5
    tm._get_daily_change = lambda code: 1.0
    # extract and exec the functions we need
    import re
    for fn_name in ("qmt_code", "_live_pool_survivors", "_p2_gate"):
        mt = re.search(r"def %s\(.*?\n(?=\ndef |\Z)" % fn_name, src, re.S)
        if not mt:
            check(f"TDX {fn_name} found", False)
            continue
        exec(compile(mt.group(0), TDX_MOD, "exec"), tm.__dict__)

    surv_tdx = tm._live_pool_survivors(pool)
    check("TDX _live_pool_survivors n=6", len(surv_tdx) == 6, f"n={len(surv_tdx)}")
    check("TDX survivor money_pass carried",
          [s["money_flow_pass"] for s in surv_tdx][:3] == [True, True, True])
    gated_tdx = tm._p2_gate(surv_tdx, 9 * 60 + 40)
    check("TDX _p2_gate live branch pass=3",
          sum(1 for g in gated_tdx if g.get("money_pass")) == 3)
    check("TDX live sort pass-first",
          [g["money_pass"] for g in gated_tdx] == [True, True, True, False, False, False])

    print(f"\n===== {len(PASSED)} passed, {len(FAILED)} failed =====")
    if FAILED:
        print("FAILED:", FAILED)
        sys.exit(1)


if __name__ == "__main__":
    run()
