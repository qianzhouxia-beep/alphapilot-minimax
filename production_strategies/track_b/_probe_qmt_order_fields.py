# coding:utf-8
# AlphaPilot -- Track B QMT SIM order/deal field probe (Fix C step 0)
# =========================================================
# RUNNABLE STRATEGY VERSION (no manual call needed).
# Purpose: dump the REAL attribute names/values of today's ORDER / DEAL /
# POSITION objects so the Fix C fill-confirmation helper reads the correct
# fields. Guessing a wrong field name silently falls back to a default and
# would recreate the ghost ledger.
#
# HOW TO RUN (QMT, pure ASCII):
#   1. In QMT strategy editor, open/create a stock strategy file and REPLACE
#      its whole content with this file's content.
#   2. Bind the account in strategy config (either 98009473 SIM or
#      8886269286 LIVE both work -- this file tries both).
#   3. Start the strategy in trading mode. It prints [PROBE] once.
#   4. Copy every [PROBE] line from the strategy log and send to Cursor.
#
# Read-only: only queries get_trade_detail_data; NEVER calls passorder.

DEFAULT_ACCOUNTS = ["98009473", "8886269286"]  # Track A/B SIM, then LIVE

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
    "m_dTradedPrice", "m_dAveragePrice", "m_dAmount",
    "m_strTradeDate", "m_strTradeTime", "traded_volume", "traded_price",
    "order_id", "trade_id", "price", "volume",
]
POS_FIELDS = [
    "m_strInstrumentID", "m_strExchangeID", "m_nVolume", "m_nCanUseVolume",
    "m_nCanUseVol", "m_dOpenPrice", "m_strOpenDate", "m_strInstrumentName",
    "volume", "can_use_volume", "open_price", "avg_price",
]

_probed = False


def _resolve_query():
    """Find get_trade_detail_data from the strategy module / builtins."""
    import builtins
    fn = getattr(builtins, "get_trade_detail_data", None)
    if fn is not None:
        return fn
    import sys
    for name in ("__main__",):
        mod = sys.modules.get(name)
        fn = getattr(mod, "get_trade_detail_data", None) if mod else None
        if fn is not None:
            return fn
    raise RuntimeError("get_trade_detail_data not found in this context")


def _dump(obj, tag, candidates):
    seen = set()
    rows = []
    try:
        for k in dir(obj):
            if k.startswith("_") or k in seen:
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
    d = getattr(obj, "__dict__", None)
    if isinstance(d, dict):
        for k, v in d.items():
            if k in seen:
                continue
            seen.add(k)
            rows.append((k, v))
    for k in candidates:
        if k in seen:
            continue
        seen.add(k)
        try:
            v = getattr(obj, k)
        except BaseException:
            continue
        rows.append((k + " *", v))   # '*' = found via known-name list
    print("[PROBE] --- " + tag + " n_attrs=" + str(len(rows)) +
          " ('*' = via known-name list)")
    for k, v in sorted(rows, key=lambda x: x[0]):
        print("[PROBE]   " + tag + "." + str(k) + " = " + str(v)[:70])


def _probe_account(acct, q):
    print("[PROBE] ===== account=" + str(acct) + " =====")
    for kind, fields in (("ORDER", ORDER_FIELDS),
                         ("DEAL", DEAL_FIELDS),
                         ("POSITION", POS_FIELDS)):
        try:
            objs = q(acct, "STOCK", kind) or []
            print("[PROBE] " + kind + " n=" + str(len(objs)))
            if not objs and kind != "POSITION":
                print("[PROBE] " + kind +
                      " empty -> run on a day with orders")
            for ob in list(objs)[-3:]:
                _dump(ob, kind, fields)
        except BaseException as e:
            print("[PROBE] " + kind + " query fail: " + str(e)[:120])


def probe(C=None, account_id=None):
    """Manual entry point (also called automatically by init/handlebar)."""
    global _probed
    try:
        q = _resolve_query()
    except BaseException as e:
        print("[PROBE] resolve query fail: " + str(e))
        return
    accts = []
    if account_id:
        accts.append(account_id)
    if C is not None:
        cid = getattr(C, "accountid", None) or getattr(C, "account_id", None)
        if cid:
            cid = str(cid)
            cid = cid.split(".")[0].strip()
            if cid and cid not in accts:
                accts.append(cid)
    for a in DEFAULT_ACCOUNTS:
        if a not in accts:
            accts.append(a)
    for a in accts:
        _probe_account(a, q)
    _probed = True
    print("[PROBE] ===== DONE (send all [PROBE] lines to Cursor) =====")


def init(C):
    global _probed
    _probed = False
    try:
        probe(C)
    except BaseException as e:
        print("[PROBE] init probe fail: " + str(e)[:120])


def handlebar(C):
    global _probed
    if _probed:
        return
    try:
        probe(C)
    except BaseException as e:
        print("[PROBE] handlebar probe fail: " + str(e)[:120])
