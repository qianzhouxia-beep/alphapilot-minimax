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
#   2. In QMT strategy editor's handlebar, paste:
#         import _probe_qmt_order_fields as P
#         P.probe(C)          # C = the running context; account optional
#      on a day/bar AFTER at least one buy or sell order was placed.
#   3. Paste every [PROBE] line back to Cursor.
#
# Why the client import may look for the query fn in several places:
# get_trade_detail_data is injected by QMT into the *strategy* module, not
# necessarily into an imported helper module -> we resolve it from the
# caller's globals / builtins / the sim module as a fallback.
#
# Read-only: only queries get_trade_detail_data; never calls passorder.

DEFAULT_ACCOUNT_ID = "98009473"   # Track B SIM account (TrackB_..._sim.py)

# Known QMT / xtquant candidate names, so we still get VALUES even if dir()
# cannot enumerate the C++ wrapper's attributes.
ORDER_FIELDS = [
    "m_strOrderSysID", "m_strOrderID", "m_nOrderStatus", "m_nOrderType",
    "m_strInstrumentID", "m_strExchangeID", "m_nDirection",
    "m_nVolumeTotalOriginal", "m_nVolumeTraded", "m_nVolumeTotalTraded",
    "m_nVolumeCanceled", "m_dOrderPrice", "m_dTradedPrice",
    "m_dAveragePrice", "m_strInsertDate", "m_strInsertTime",
    "m_strRemark", "m_strRemark1", "order_id", "order_status",
    "order_volume", "traded_volume", "traded_price", "price", "status",
]
DEAL_FIELDS = [
    "m_strOrderSysID", "m_strOrderID", "m_strTradeID", "m_strInstrumentID",
    "m_strExchangeID", "m_nDirection", "m_nVolume", "m_dPrice",
    "m_dTradedPrice", "m_dAveragePrice", "m_dAmount", "m_dComssion",
    "m_strTradeDate", "m_strTradeTime", "traded_volume", "traded_price",
    "order_id", "trade_id", "price", "volume",
]
POS_FIELDS = [
    "m_strInstrumentID", "m_strExchangeID", "m_nVolume", "m_nCanUseVolume",
    "m_nCanUseVol", "m_dOpenPrice", "m_strOpenDate", "m_strInstrumentName",
    "volume", "can_use_volume", "open_price", "avg_price",
]


def _resolve_query():
    """Find get_trade_detail_data from builtins / caller globals / sim module."""
    import builtins
    fn = getattr(builtins, "get_trade_detail_data", None)
    if fn is not None:
        return fn
    import sys
    for name in ("__main__", "TrackB_track_b_qmt_auction_sim"):
        mod = sys.modules.get(name)
        fn = getattr(mod, "get_trade_detail_data", None) if mod else None
        if fn is not None:
            return fn
    raise RuntimeError("get_trade_detail_data not found in this context")


def _dump(obj, tag, candidates):
    seen = set()
    rows = []
    # 1) whatever dir() exposes
    try:
        for k in dir(obj):
            if k.startswith("_"):
                continue
            if k in seen:
                continue
            seen.add(k)
            try:
                v = getattr(obj, k)
            except BaseException:
                continue
            if callable(v):
                continue
            rows.append((k, v))
    except BaseException:
        pass
    # 2) __dict__ if the wrapper has one
    d = getattr(obj, "__dict__", None)
    if isinstance(d, dict):
        for k, v in d.items():
            if k in seen:
                continue
            seen.add(k)
            rows.append((k, v))
    # 3) explicit candidate names (catches non-enumerable C++ attrs)
    for k in candidates:
        if k in seen:
            continue
        seen.add(k)
        try:
            v = getattr(obj, k)
        except BaseException:
            continue
        seen.add(k)
        rows.append((k + " *", v))   # '*' = found via known-name list
    print("[PROBE] --- " + tag + " n_attrs=" + str(len(rows)) +
          " (name '*' = via known-name list)")
    for k, v in sorted(rows, key=lambda x: x[0]):
        print("[PROBE]   " + tag + "." + str(k) + " = " + str(v)[:70])


def probe(C=None, account_id=None):
    try:
        q = _resolve_query()
    except BaseException as e:
        print("[PROBE] resolve query fail: " + str(e))
        return
    acct = account_id or DEFAULT_ACCOUNT_ID
    print("[PROBE] account=" + str(acct))
    for kind, fields in (("ORDER", ORDER_FIELDS),
                         ("DEAL", DEAL_FIELDS),
                         ("POSITION", POS_FIELDS)):
        try:
            objs = q(acct, "STOCK", kind) or []
            print("[PROBE] " + kind + " n=" + str(len(objs)))
            if not objs and kind != "POSITION":
                print("[PROBE] " + kind + " empty -> run on a day with orders")
            for ob in list(objs)[-3:]:
                _dump(ob, kind, fields)
        except BaseException as e:
            print("[PROBE] " + kind + " query fail: " + str(e)[:120])
