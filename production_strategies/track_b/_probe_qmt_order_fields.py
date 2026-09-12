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
#   2. Bind the account in strategy config (either 62128716 SIM or
#      98009473 SIM both work -- this file tries the two SIM accounts only;
#      the LIVE account is deliberately NOT queried).
#   3. Start the strategy in trading mode. It prints [PROBE] once.
#   4. It ALSO writes every [PROBE] line to a text file; the path is printed
#      as "[PROBE] OUT FILE = ...". Open that file in Notepad and copy ALL of
#      it back. (Fallback: copy every [PROBE] line from the strategy log.)
#
# Read-only: only queries get_trade_detail_data; NEVER calls passorder.

import os

DEFAULT_ACCOUNTS = ["62128716", "98009473"]  # B SIM, A SIM only (LIVE excluded)

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
_OUT_LINES = []
_OUT_PATH = None


def _pick_out_paths():
    """Candidate paths for the dumped output (first writable wins)."""
    cands = []
    for base in (os.path.expanduser("~"), os.environ.get("USERPROFILE"),
                 os.environ.get("TEMP"), os.getcwd()):
        if not base:
            continue
        pth = os.path.join(base, "alphapilot_probe_out.txt")
        if pth not in cands:
            cands.append(pth)
    return cands


def _init_out_file():
    """Truncate/create the dump file. Sets _OUT_PATH (None if none writable)."""
    global _OUT_PATH
    for pth in _pick_out_paths():
        try:
            f = open(pth, "w")
            f.write("AlphaPilot probe output (QMT). Copy ALL of this back.\n")
            f.flush()
            f.close()
            _OUT_PATH = pth
            return
        except BaseException:
            continue
    _OUT_PATH = None


def _out(msg):
    """Print AND append to the dump file (best effort, never raises)."""
    line = str(msg)
    try:
        print(line)
    except BaseException:
        pass
    _OUT_LINES.append(line)
    if _OUT_PATH:
        try:
            f = open(_OUT_PATH, "a")
            f.write(line + "\n")
            f.flush()
            f.close()
        except BaseException:
            pass


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
    _out("[PROBE] --- " + tag + " n_attrs=" + str(len(rows)) +
         " ('*' = via known-name list)")
    for k, v in sorted(rows, key=lambda x: x[0]):
        _out("[PROBE]   " + tag + "." + str(k) + " = " + str(v)[:70])


def _probe_account(acct, q):
    _out("[PROBE] ===== account=" + str(acct) + " =====")
    for kind, fields in (("ORDER", ORDER_FIELDS),
                         ("DEAL", DEAL_FIELDS),
                         ("POSITION", POS_FIELDS)):
        try:
            objs = q(acct, "STOCK", kind) or []
            _out("[PROBE] " + kind + " n=" + str(len(objs)))
            if not objs and kind != "POSITION":
                _out("[PROBE] " + kind +
                     " empty -> run on a day with orders")
            for ob in list(objs)[-3:]:
                _dump(ob, kind, fields)
        except BaseException as e:
            _out("[PROBE] " + kind + " query fail: " + str(e)[:120])


def _dump_type_schema():
    """Dump the CLASS schema of the order/trade/position types.

    This does not need any live order: QMT's get_trade_detail_data returns
    xtquant.xttype objects, whose field names can be read off the class
    itself (__slots__ / dir / annotations / an empty instance).
    """
    mods = []
    for mn in ("xtquant.xttype", "xtquant.xttrader", "xtquant"):
        try:
            __import__(mn)
            import sys
            mods.append(sys.modules[mn])
        except BaseException as e:
            _out("[PROBE] import " + mn + " fail: " + str(e)[:100])
    names = ("XtOrder", "XtTrade", "XtPosition", "XtOrderResponse",
             "XtTradeDetail", "XtOrderDetail", "XtAccount")
    for mod in mods:
        for nm in names:
            cls = getattr(mod, nm, None)
            if cls is None:
                continue
            tag = getattr(mod, "__name__", "?") + "." + nm
            _out("[PROBE] CLASS " + tag)
            for attr in ("__slots__", "__annotations__"):
                v = getattr(cls, attr, None)
                if v:
                    _out("[PROBE]   " + tag + "." + attr + " = " + str(v)[:300])
            # enumerate class-level dict (methods excluded)
            try:
                for k in sorted(dir(cls)):
                    if k.startswith("_"):
                        continue
                    try:
                        v = getattr(cls, k)
                    except BaseException:
                        continue
                    if callable(v):
                        continue
                    _out("[PROBE]   " + tag + "." + k + " = " + str(v)[:70])
            except BaseException:
                pass
            # try a no-arg instance -> instance attrs (most reliable)
            try:
                inst = cls()
                _dump(inst, tag + "()", ORDER_FIELDS)
            except BaseException as e:
                _out("[PROBE]   " + tag + "() not instantiable: " + str(e)[:90])


def probe(C=None, account_id=None):
    """Manual entry point (also called automatically by init/handlebar)."""
    global _probed
    _init_out_file()
    try:
        q = _resolve_query()
    except BaseException as e:
        _out("[PROBE] resolve query fail: " + str(e))
        _out("[PROBE] OUT FILE = " + str(_OUT_PATH))
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
    _out("[PROBE] OUT FILE = " + str(_OUT_PATH))
    _out("[PROBE] bound C.acct=" + str(getattr(C, "accountid", None)) +
         " query_accts=" + str(accts))
    _dump_type_schema()
    for a in accts:
        _probe_account(a, q)
    _probed = True
    _out("[PROBE] ===== DONE (open the OUT FILE above and copy ALL of it) =====")
    _out("[PROBE] OUT FILE = " + str(_OUT_PATH))


def init(C):
    global _probed
    _probed = False
    try:
        probe(C)
    except BaseException as e:
        _out("[PROBE] init probe fail: " + str(e)[:120])
        _out("[PROBE] OUT FILE = " + str(_OUT_PATH))


def handlebar(C):
    global _probed
    if _probed:
        return
    try:
        probe(C)
    except BaseException as e:
        _out("[PROBE] handlebar probe fail: " + str(e)[:120])
