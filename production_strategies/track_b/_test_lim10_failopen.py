#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fix D regression test: Track B LIM10 guard must fail-SAFE (v2.13).

P0 (2026-09-11, WB-Mac, issue #6): when the server live pool rejects every
row (money_items == []), the old LIM10 else-branch fell through to the FCFS
fallback and bought server-rejected names (fail-open). Spec (v2.8 CHANGELOG):
while LIM10_ENABLE and the live pool is active, only money_pass names may be
bought; no fallback fill.

Assertions (all must hold after v2.13):
  A. live_pool_active + money_flow_pass all False  -> 0 buys   (RED before fix)
  B. classic pool (live_pool_active False)         -> fallback still buys
  C. live pool, money_pass rows but limit_cnt_10d all missing -> old FCFS

Pure ASCII (QMT-safe). Run: python _test_lim10_failopen.py
"""
import importlib.util
import json
import os
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
# Fix D must guard BOTH the main file and the fixed-name deployment copy
# (QMT loads the deployment copy). Point either via TB_SIM_FILE.
SIM = os.environ.get("TB_SIM_FILE") or os.path.join(
    HERE, "TrackB_track_b_qmt_auction_sim.py")

spec = importlib.util.spec_from_file_location("tb_sim_fixd", SIM)
m = importlib.util.module_from_spec(spec)
sys.modules["tb_sim_fixd"] = m
spec.loader.exec_module(m)

PASSED = []
FAILED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


TMP = tempfile.mkdtemp(prefix="tb_lim10_")
m.ORDER_LOCK_FILE = os.path.join(TMP, "order_locks.json")
m.TRADE_LOG = os.path.join(TMP, "trades.json")
m.GATE_LOG = os.path.join(TMP, "gate.json")
m.POS_STATE_FILE = os.path.join(TMP, "pos.json")
with open(m.ORDER_LOCK_FILE, "w", encoding="utf-8") as f:
    json.dump({}, f)


def make_C(live):
    return SimpleNamespace(
        run_count=1, sent_today=set(), position_map={},
        _top2_fired=False, _auction_done=True, _gate_dump_done=False,
        _p1_survivors=[], live_pool_active=live, _live_surv_ready=False,
        _gap_cache={}, _sector_gap_mean={}, _sector_stock_cnt={},
        _sector_members_cache={}, _snap_day="", scores_cache={},
        cand_cache={}, fullpool_cache={}, stop_watch={},
        _univ_codes=[], _last_resync=0, _last_univ=0, _last_remote_fetch=0,
        _last_pos_count=-1, _univ_dirty=True, current_date="20260911",
        _lim10_logged=False, _lim10_fb_logged=False, _lim10_flat_logged=False,
        _path_logged=False, trade_log=[], _order_locks_cache={},
    )


def rows(n, money, limit_val):
    out = []
    for i in range(n):
        code = "%06d.SZ" % (300001 + i)
        out.append({
            "code": code, "symbol": code, "name": "stk%d" % i,
            "rank": i + 1, "score": 1.0 - i * 0.01,
            "score_0500": 1.0 - i * 0.01, "money_pass": money,
            "money_flow_pass": money, "limit_cnt_10d": limit_val,
        })
    return out


def drive(C, p2rows):
    buys = []

    # fresh day: no prior BUY locks, else today_bought >= MAX_DAILY_BUY
    with open(m.ORDER_LOCK_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f)

    def fake_passorder(*a, **k):
        buys.append(a[3] if len(a) > 3 else k.get("code"))
        return 0

    qmt_globals = {
        "get_trade_detail_data": lambda *a, **k: [
            SimpleNamespace(m_dAvailable=1e7, m_dBalance=2e7)],
        "passorder": fake_passorder,
    }
    with patch.dict(m.__dict__, qmt_globals), \
         patch.object(m, "_update_auction_state", return_value=None), \
         patch.object(m, "_p1_gate", return_value=None), \
         patch.object(m, "_live_pool_survivors", return_value=p2rows), \
         patch.object(m, "_p2_gate", lambda C, s, n: p2rows), \
         patch.object(m, "_p2_decide", return_value=(10.0, "dyn_confirm")), \
         patch.object(m, "_dump_gate", return_value=None), \
         patch.object(m, "_is_limit_up", return_value=False), \
         patch.object(m, "_wyckoff_distribution", return_value=False), \
         patch.object(m, "_board_allowed", return_value=True), \
         patch.object(m, "_is_st_name", return_value=False), \
         patch.object(m, "_order_locked", return_value=False), \
         patch.object(m, "_is_sweet_zone", return_value=False), \
         patch.object(m, "_get_last", return_value=None), \
         patch.object(m, "_save_pos_state", return_value=None), \
         patch.object(m, "_log_trade", return_value=None):
        m._check_buy(C, None, 9 * 60 + 36, "20260911", p2rows)
    return buys


def main():
    print("\n== A. P0 repro: live pool, money gate rejects ALL -> 0 buys ==")
    Ca = make_C(live=True)
    pa = rows(3, money=False, limit_val=0.0)
    ba = drive(Ca, pa)
    check("A money_pass all False -> no buy (fail-safe)", len(ba) == 0,
          "buys=%s" % ba)

    print("\n== B. classic pool -> fallback still allowed ==")
    Cb = make_C(live=False)
    pb = rows(2, money=False, limit_val=0.0)
    bb = drive(Cb, pb)
    check("B classic fallback still buys", len(bb) >= 1, "buys=%s" % bb)

    print("\n== C. live pool, money_pass present but limit_cnt_10d missing -> "
          "old FCFS ==")
    Cc = make_C(live=True)
    pc = rows(2, money=True, limit_val=None)
    bc = drive(Cc, pc)
    check("C limit_cnt_10d missing -> FCFS still buys", len(bc) >= 1,
          "buys=%s" % bc)

    print("\n===== %d passed, %d failed =====" % (len(PASSED), len(FAILED)))
    if FAILED:
        print("FAILED:", FAILED)
        sys.exit(1)


if __name__ == "__main__":
    main()
