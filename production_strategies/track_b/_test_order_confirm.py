#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fix C regression test: Track B passorder fill confirmation (v2.14).

Ghost ledger (2026-09-12, WB-Mac, issue #6): passorder ret==0 only means
"order submitted". v2.13 booked BUY/SELL immediately at the signal price, so a
rejected/canceled order still created a position + trade-log entry that the
broker never had. v2.14 confirms via ORDER/DEAL before booking.

Scenarios (A/B RED before v2.14, GREEN after; C/D/E regression):
  A. BUY never acknowledged  -> no position, no lock, no BUY log
  B. BUY filled at px != signal -> book real traded vol + avg price
  C. SELL never acknowledged -> position kept, no SELL log, lock released
  D. SELL filled             -> position popped, SELL logged
  E. VERIFY_FILL=False       -> legacy immediate booking (userOrderId "")
Also: _fval reads classic m_* AND xttrader snake_case names.

Pure ASCII. Run: python _test_order_confirm.py
"""
import importlib.util
import json
import os
import sys
import tempfile
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
SIM = os.environ.get("TB_SIM_FILE") or os.path.join(
    HERE, "TrackB_track_b_qmt_auction_sim_v2.14.py")

spec = importlib.util.spec_from_file_location("tb_sim_fixc", SIM)
m = importlib.util.module_from_spec(spec)
sys.modules["tb_sim_fixc"] = m
spec.loader.exec_module(m)

PASSED = []
FAILED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


TMP = tempfile.mkdtemp(prefix="tb_fixc_")
m.ORDER_LOCK_FILE = os.path.join(TMP, "order_locks.json")
m.TRADE_LOG = os.path.join(TMP, "trades.json")
m.POS_STATE_FILE = os.path.join(TMP, "pos.json")
m.GATE_LOG = os.path.join(TMP, "gate.json")
m.VERIFY_FILL = True
m.VERIFY_GRACE_CHECKS = 3
m.VERIFY_MAX_CHECKS = 30

TODAY = datetime.now().strftime("%Y%m%d")
CODE = "600000.SH"


def reset_files():
    for p in (m.ORDER_LOCK_FILE, m.TRADE_LOG):
        with open(p, "w", encoding="utf-8") as f:
            json.dump([] if p == m.TRADE_LOG else {}, f)


def make_C():
    with open(m.TRADE_LOG, "w", encoding="utf-8") as f:
        json.dump([], f)
    return SimpleNamespace(
        position_map={}, stop_watch={}, sent_today=set(), trade_log=[],
        pending_orders={}, _oref_seq=0, run_count=1, pos_state={},
        _ledger_sig_ts={}, current_date=TODAY, _snap_day="",
    )


def buy_pos():
    return {"shares": 1000, "can_use": 1000, "buy_price": 10.0, "name": "X",
            "buy_date": TODAY, "peak": 10.0, "peel_count": 0, "pending": True}


def fake_q(orders, deals):
    def _q(acct, kind_type, kind):
        if kind == "ORDER":
            return list(orders)
        if kind == "DEAL":
            return list(deals)
        return []
    return _q


def order_row(remark, ovol=1000, tvol=0, tpx=0.0):
    return SimpleNamespace(
        m_strInstrumentID=CODE, m_strRemark=remark,
        m_nVolumeTotalOriginal=ovol, m_nVolumeTraded=tvol,
        m_dTradedPrice=tpx, m_strOrderSysID="SYS1")


def deal_row(remark, vol, px):
    return SimpleNamespace(
        m_strInstrumentID=CODE, m_strRemark=remark,
        m_nVolume=vol, m_dPrice=px)


def confirm_times(C, orders, deals, n):
    with patch.dict(m.__dict__, {"get_trade_detail_data": fake_q(orders, deals)}):
        for _ in range(n):
            m._confirm_pending(C)


def buy_logs(C):
    return [t for t in C.trade_log if t.get("action") == "BUY"]


def sell_logs(C):
    return [t for t in C.trade_log if t.get("action") in ("SELL", "SELL_HALF")]


# ---------------- A. BUY never acknowledged -> rollback -------------------
def test_a():
    print("\n== A. BUY not acknowledged -> no position / no lock / no BUY ==")
    reset_files()
    C = make_C()
    oref = m._next_oref(C, CODE, TODAY)
    C.position_map[CODE] = buy_pos()
    m._register_pending(C, "BUY", CODE, oref, 1000, 10.0,
                        "track_b_auction", TODAY, "BUY")
    m._mark_order_locked(TODAY, CODE, "BUY")
    confirm_times(C, [], [], 6)          # broker has no order at all
    check("A position rolled back", CODE not in C.position_map,
          "pos=%s" % list(C.position_map))
    check("A BUY lock cleared",
          not m._order_locked(TODAY, CODE, "BUY"))
    check("A no BUY in trade log", len(buy_logs(C)) == 0,
          "logs=%s" % buy_logs(C))


# ---------------- B. BUY filled at a price != signal ---------------------
def test_b():
    print("\n== B. BUY filled -> book real vol + avg px (not signal) ==")
    reset_files()
    C = make_C()
    oref = m._next_oref(C, CODE, TODAY)
    C.position_map[CODE] = buy_pos()
    m._register_pending(C, "BUY", CODE, oref, 1000, 10.0,
                        "track_b_auction", TODAY, "BUY")
    m._mark_order_locked(TODAY, CODE, "BUY")
    confirm_times(C, [order_row(oref, tvol=1000, tpx=10.5)],
                  [deal_row(oref, 1000, 10.5)], 2)
    pos = C.position_map.get(CODE)
    check("B position kept", pos is not None)
    check("B shares = traded vol", pos and pos.get("shares") == 1000,
          "shares=%s" % (pos or {}).get("shares"))
    check("B buy_price = DEAL avg (10.5)", pos and abs(pos.get("buy_price") - 10.5) < 1e-9,
          "px=%s" % (pos or {}).get("buy_price"))
    check("B pending cleared", pos and pos.get("pending") is False)
    bl = buy_logs(C)
    check("B one BUY logged at 10.5", len(bl) == 1 and abs(bl[0]["price"] - 10.5) < 1e-9,
          "logs=%s" % bl)


# ---------------- C. SELL never acknowledged -> keep position ------------
def test_c():
    print("\n== C. SELL not acknowledged -> keep position / no SELL log ==")
    reset_files()
    C = make_C()
    pos = {"shares": 1000, "can_use": 1000, "buy_price": 10.0}
    C.position_map[CODE] = pos
    with patch.dict(m.__dict__, {"passorder": lambda *a, **k: 0}):
        m._do_sell(C, CODE, pos, 10.2, "hard_stop")
    check("C position kept at send", CODE in C.position_map)
    check("C SELL lock written", m._order_locked(TODAY, CODE, "hard_stop"))
    check("C pending registered", len(C.pending_orders) == 1)
    confirm_times(C, [], [], 6)          # never appears at the broker
    check("C position still present", CODE in C.position_map)
    check("C lock released for retry",
          not m._order_locked(TODAY, CODE, "hard_stop"))
    check("C no SELL in trade log", len(sell_logs(C)) == 0,
          "logs=%s" % sell_logs(C))


# ---------------- D. SELL filled -> pop + log ----------------------------
def test_d():
    print("\n== D. SELL filled -> pop position + log SELL ==")
    reset_files()
    C = make_C()
    pos = {"shares": 1000, "can_use": 1000, "buy_price": 10.0}
    C.position_map[CODE] = pos
    with patch.dict(m.__dict__, {"passorder": lambda *a, **k: 0}):
        m._do_sell(C, CODE, pos, 10.2, "hard_stop")
    rec = list(C.pending_orders.values())[0]
    confirm_times(C, [order_row(rec["remark"], tvol=1000, tpx=10.2)],
                  [deal_row(rec["remark"], 1000, 10.2)], 1)
    check("D position popped", CODE not in C.position_map)
    sl = sell_logs(C)
    check("D one SELL logged", len(sl) == 1, "logs=%s" % sl)
    check("D SELL px = deal", sl and abs(sl[0]["price"] - 10.2) < 1e-9)


# ---------------- E. VERIFY_FILL=False -> legacy -------------------------
def test_e():
    print("\n== E. VERIFY_FILL=False -> legacy immediate booking ==")
    reset_files()
    C = make_C()
    pos = {"shares": 1000, "can_use": 1000, "buy_price": 10.0}
    C.position_map[CODE] = pos
    seen = []

    def fake_passorder(*a, **k):
        seen.append(a)
        return 0

    m.VERIFY_FILL = False
    try:
        with patch.dict(m.__dict__, {"passorder": fake_passorder}):
            m._do_sell(C, CODE, pos, 10.2, "hard_stop")
    finally:
        m.VERIFY_FILL = True
    check("E position popped immediately", CODE not in C.position_map)
    check("E SELL logged immediately", len(sell_logs(C)) == 1,
          "logs=%s" % sell_logs(C))
    check("E legacy userOrderId is empty", seen and seen[0][9] == "",
          "args9=%s" % (seen[0][9] if seen else None))
    check("E no pending registered", len(C.pending_orders) == 0)


# ---------------- F. dual-API field resolver ----------------------------
def test_f():
    print("\n== F. _fval reads both m_* and snake_case ==")
    classic = SimpleNamespace(m_strInstrumentID="600000.SH", m_nVolume=700)
    modern = SimpleNamespace(stock_code="600000.SH", traded_volume=700)
    check("F classic code", m._fval(classic, m._FC_CODE) == "600000.SH")
    check("F modern code", m._fval(modern, m._FC_CODE) == "600000.SH")
    check("F classic traded_vol",
          m._fval(classic, m._FC_DVOL) == 700)
    check("F modern traded_vol",
          m._fval(modern, m._FC_DVOL) == 700)
    snap = m._order_snapshot(CODE, "", 1000)
    check("F empty broker -> not found", snap["found"] is False)


def main():
    test_a()
    test_b()
    test_c()
    test_d()
    test_e()
    test_f()
    print("\n===== %d passed, %d failed =====" % (len(PASSED), len(FAILED)))
    if FAILED:
        print("FAILED:", FAILED)
        sys.exit(1)


if __name__ == "__main__":
    main()
