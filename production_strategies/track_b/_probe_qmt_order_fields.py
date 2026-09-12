# coding:utf-8
# AlphaPilot -- Track B QMT SIM order/deal field probe (Fix C step 0)
# =========================================================
# Purpose: dump the REAL attribute names of today's ORDER / DEAL objects so
# the Fix C fill-confirmation helper reads the correct fields (guessing a
# wrong name silently falls back to a default and recreates the ghost ledger).
#
# How to run (QMT, SIM account, pure ASCII):
#   1. Copy this file next to TrackB_track_b_qmt_auction_sim.py in the QMT
#      python dir.
#   2. In QMT strategy editor, import it and call probe(C) once, e.g. paste:
#         import _probe_qmt_order_fields as P
#         P.probe(C)
#      inside handlebar (any bar after 09:36 on a day with orders).
#   3. Paste the [PROBE] lines back to Cursor.
#
# Read-only: only queries get_trade_detail_data; never calls passorder.

ACCOUNT_ID = "98009473"   # Track B SIM account (same as TrackB_..._sim.py)


def _dump(obj, tag):
    keys = []
    for k in dir(obj):
        if k.startswith("_"):
            continue
        try:
            v = getattr(obj, k)
        except BaseException:
            continue
        if callable(v):
            continue
        keys.append((k, v))
    print("[PROBE] --- " + tag + " n_fields=" + str(len(keys)))
    for k, v in sorted(keys):
        print("[PROBE]   " + tag + "." + str(k) + " = " + str(v)[:60])


def probe(C):
    try:
        orders = get_trade_detail_data(ACCOUNT_ID, "STOCK", "ORDER") or []
        print("[PROBE] ORDER n=" + str(len(orders)))
        for o in orders[-3:]:
            _dump(o, "ORDER")
    except BaseException as e:
        print("[PROBE] ORDER query fail: " + str(e)[:120])
    try:
        deals = get_trade_detail_data(ACCOUNT_ID, "STOCK", "DEAL") or []
        print("[PROBE] DEAL n=" + str(len(deals)))
        for d in deals[-3:]:
            _dump(d, "DEAL")
    except BaseException as e:
        print("[PROBE] DEAL query fail: " + str(e)[:120])
    try:
        poss = get_trade_detail_data(ACCOUNT_ID, "STOCK", "POSITION") or []
        print("[PROBE] POSITION n=" + str(len(poss)))
        if poss:
            _dump(poss[-1], "POS")
    except BaseException as e:
        print("[PROBE] POSITION query fail: " + str(e)[:120])
