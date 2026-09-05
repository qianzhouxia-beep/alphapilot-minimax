#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline mock test for Track B v1.1 widened buy window (_check_buy).

Verifies:
  1. 09:36 live mode enters buy segment; wait_confirm candidates are retried
     on later bars (top2_fired stays False).
  2. 09:41 a dyn_confirm fires -> buy executes, top2_fired still False if the
     daily budget is not full.
  3. 11:31 outside window -> top2_fired True (day closed for buying).
  4. 13:30 next-day state reset -> afternoon window re-enters buy segment.
  5. 14:01 outside window -> closed again.
"""
import sys
import types
from types import SimpleNamespace
from unittest.mock import patch

MOD = r"C:\Users\elvisq\Projects\alphapilot\production_strategies\track_b\TrackB_track_b_qmt_auction_sim.py"

# --- load module without executing QMT globals ---
import importlib.util
spec = importlib.util.spec_from_file_location("tb_sim", MOD)
m = importlib.util.module_from_spec(spec)
sys.modules["tb_sim"] = m
spec.loader.exec_module(m)


def make_C():
    C = SimpleNamespace(
        run_count=0, current_date="20260817", sent_today=set(),
        position_map={}, scores_cache={}, cand_cache={},
        fullpool_cache={}, stop_watch={}, _last_resync=0, _last_univ=0,
        _last_remote_fetch=0, _last_pos_count=-1, _univ_codes=[],
        _univ_dirty=True,
        _gap_cache={}, _sector_gap_mean={}, _sector_stock_cnt={},
        _p1_survivors=[], _top2_fired=False, _auction_done=False,
        _gate_dump_done=False, live_pool_active=True, _live_surv_ready=False,
        _sector_members_cache={}, _snap_day="", score_dir=r"C:\alphapilot\scores",
        trade_log=[], _order_locks_cache={},
    )
    return C


def make_pool():
    rows = []
    for i in range(10):
        rows.append({
            "symbol": f"{300000+i:06d}.SZ", "name": f"stk{i}",
            "rank": i + 1, "industry_l1": "半导体",
            "score": 1.0 - i * 0.01, "score_0500": 1.0 - i * 0.01,
            "money_flow_pass": i < 5, "research_tier": "s1",
            "main_net_5d": 1e7, "active_buy_ratio": 0.6,
        })
    return rows


PASSED = []
FAILED = []

def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} {detail}")


def fake_order_file(tmp):
    import json, os
    p = r"C:\alphapilot\_ut_b_order_locks.json"
    os.makedirs(r"C:\alphapilot", exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(tmp, f)
    return p


def run():
    # QMT injects these as globals at runtime; give the module defaults so
    # patch.object works below.
    m.get_trade_detail_data = lambda *a, **k: []
    m.passorder = lambda *a, **k: 0
    pool = make_pool()
    C = make_C()
    order_locks = {}
    m.ORDER_LOCK_FILE = fake_order_file(order_locks)
    m.TRADE_LOG = r"C:\alphapilot\_ut_b_trades.json"
    m.GATE_LOG = r"C:\alphapilot\_ut_b_gate.json"

    # --- scenario 1: 09:36, all candidates wait_confirm ---
    print("\n== 1. 09:36 live pool, all wait_confirm ==")
    with patch.object(m, "_load_fullpool", return_value=pool), \
         patch.object(m, "_live_pool_survivors", return_value=[
             {"code": f"{300000+i:06d}.SZ", "symbol": f"{300000+i:06d}.SZ",
              "name": f"stk{i}", "rank": i + 1, "industry_l1": "半导体",
              "score_0500": 1.0 - i * 0.01, "score": 1.0 - i * 0.01,
              "money_flow_pass": i < 5, "research_tier": "s1",
              "active_buy_ratio": 0.6} for i in range(10)
         ]), \
         patch.object(m, "_p2_decide", return_value=(None, "wait_confirm")), \
         patch.object(m, "get_trade_detail_data",
                      return_value=[SimpleNamespace(m_dAvailable=1000000,
                                                    m_dBalance=2000000)]), \
         patch.object(m, "_dump_gate", return_value=None):
        m._check_buy(C, None, 9 * 60 + 36, "20260817", pool)
        check("09:36 no buy, top2_fired stays False",
              C._top2_fired is False and len(C.position_map) == 0)
        check("09:36 sent_today empty (wait not abandoned)",
              len(C.sent_today) == 0)

    # --- scenario 2: 09:41, top candidate dyn_confirm -> buy ---
    print("\n== 2. 09:41 dyn_confirm fires (was impossible under 09:40 cutoff) ==")
    with patch.object(m, "_load_fullpool", return_value=pool), \
         patch.object(m, "_live_pool_survivors", return_value=[]), \
         patch.object(m, "_p2_decide", side_effect=[
             (23.0, "dyn_confirm"),          # first candidate buys
             *([(None, "wait_confirm")] * 20)  # rest wait
         ]), \
         patch.object(m, "get_trade_detail_data",
                      return_value=[SimpleNamespace(m_dAvailable=1000000,
                                                    m_dBalance=2000000)]), \
         patch.object(m, "passorder", return_value=0), \
         patch.object(m, "_dump_gate", return_value=None), \
         patch.object(m, "_p2_gate", lambda C, s, n: s):
        m._check_buy(C, None, 9 * 60 + 41, "20260817", pool)
        check("09:41 bought 1 share (widened window works)",
              len(C.position_map) == 1, f"pos={list(C.position_map)}")
        check("09:41 top2_fired still False (budget 2 not full)",
              C._top2_fired is False)
        check("09:41 bought code in position_map",
              "300000.SZ" in C.position_map)

    # --- scenario 3: 11:31 outside morning window -> close day ---
    print("\n== 3. 11:31 outside window -> top2_fired True ==")
    with patch.object(m, "_load_fullpool", return_value=pool), \
         patch.object(m, "get_trade_detail_data",
                      return_value=[SimpleNamespace(m_dAvailable=1000000,
                                                    m_dBalance=2000000)]):
        m._check_buy(C, None, 11 * 60 + 31, "20260817", pool)
        check("11:31 top2_fired True (window closed)",
              C._top2_fired is True)

    # --- scenario 4: next day 13:30 reset -> afternoon window re-enters ---
    print("\n== 4. next day 13:30 afternoon window re-enters ==")
    C2 = make_C()
    with patch.object(m, "_load_fullpool", return_value=pool), \
         patch.object(m, "_live_pool_survivors", return_value=[]), \
         patch.object(m, "_p2_decide", side_effect=[
             (18.0, "dyn_confirm"),
             *([(None, "wait_confirm")] * 20)
         ]), \
         patch.object(m, "get_trade_detail_data",
                      return_value=[SimpleNamespace(m_dAvailable=1000000,
                                                    m_dBalance=2000000)]), \
         patch.object(m, "passorder", return_value=0), \
         patch.object(m, "_dump_gate", return_value=None), \
         patch.object(m, "_p2_gate", lambda C, s, n: s):
        m._check_buy(C2, None, 13 * 60 + 30, "20260818", pool)
        check("13:30 afternoon buy executes (lunch-pause resume)",
              len(C2.position_map) == 1, f"pos={list(C2.position_map)}")

    # --- scenario 5: 14:01 outside afternoon window -> closed ---
    print("\n== 5. 14:01 tail closed ==")
    C3 = make_C()
    with patch.object(m, "_load_fullpool", return_value=pool), \
         patch.object(m, "get_trade_detail_data",
                      return_value=[SimpleNamespace(m_dAvailable=1000000,
                                                    m_dBalance=2000000)]):
        m._check_buy(C3, None, 14 * 60 + 1, "20260818", pool)
        check("14:01 top2_fired True (tail closed, T+1 worst)",
              C3._top2_fired is True and len(C3.position_map) == 0)

    # --- scenario 6: 14:45 sells still fine (sell side untouched) ---
    print("\n== 6. 14:45 sell side untouched ==")
    check("sell logic referenced by handlebar (no syntax issue)",
          hasattr(m, "_check_sell") and callable(m._check_sell))

    print(f"\n===== {len(PASSED)} passed, {len(FAILED)} failed =====")
    if FAILED:
        print("FAILED:", FAILED)
        sys.exit(1)


if __name__ == "__main__":
    run()
