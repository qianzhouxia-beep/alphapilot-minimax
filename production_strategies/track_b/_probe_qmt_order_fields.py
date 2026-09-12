# coding:utf-8
# AlphaPilot -- Track B QMT SIM order/deal field probe (Fix C step 0)
# =========================================================
# RUNNABLE STRATEGY VERSION (no manual call needed).
# Purpose: settle the REAL attribute names of the ORDER / DEAL / POSITION /
# ACCOUNT objects returned by get_trade_detail_data, so the Fix C
# fill-confirmation helper reads the correct fields.
#
# WARNING - WHY THIS REVISION (2026-09-12): a first run only dumped
# xtquant.xttype classes (imported by hand). That is the xttrader API and may
# NOT be the type get_trade_detail_data returns -- production code has long
# used classic m_* names (m_strInstrumentID / m_nVolume / m_dOpenPrice) and
# its [SYNC] path works. So we now dump the ACTUAL returned objects and print
# type(obj) for each. type(obj) is the decisive signal.
#
# HOW TO RUN (QMT, pure ASCII):
#   1. In QMT strategy editor, open/create a stock strategy file and REPLACE
#      its whole content with this file's content.
#   2. IMPORTANT - ADD/BIND the account in the strategy config (62128716 SIM or
#      98009473 SIM). If NO account is registered, every query returns 0
#      objects and the probe cannot see any real object. The LIVE account is
#      deliberately NOT queried.
#   3. Start the strategy in trading mode. It prints [PROBE] once.
#   4. It ALSO writes every [PROBE] line to a text file; the path is printed
#      as "[PROBE] OUT FILE = ...". Open that file in Notepad and copy ALL of
#      it back. (Fallback: copy every [PROBE] line from the strategy log.)
#
# Read-only: only queries get_trade_detail_data; NEVER calls passorder.

import os

DEFAULT_ACCOUNTS = ["62128716", "98009473"]  # B SIM, A SIM only (LIVE excluded)

ORDER_FIELDS = [
    # classic QMT strategy API (get_trade_detail_data) -- m_* style
    "m_strOrderSysID", "m_strOrderID", "m_nOrderStatus", "m_nOrderType",
    "m_strInstrumentID", "m_strExchangeID", "m_nDirection",
    "m_nVolumeTotalOriginal", "m_nVolumeTraded", "m_nVolumeTotalTraded",
    "m_nVolumeCanceled", "m_dOrderPrice", "m_dTradedPrice",
    "m_dAveragePrice", "m_strInsertDate", "m_strInsertTime",
    "m_strRemark", "m_strRemark1", "m_strStrategyName",
    # xtquant.xttrader API -- snake_case style
    "account_id", "account_type", "stock_code", "order_id", "order_sysid",
    "order_time", "order_type", "order_volume", "price_type", "price",
    "traded_volume", "traded_price", "order_status", "status_msg",
    "strategy_name", "order_remark",
]
DEAL_FIELDS = [
    # classic
    "m_strOrderSysID", "m_strOrderID", "m_strTradeID", "m_strInstrumentID",
    "m_strExchangeID", "m_nDirection", "m_nVolume", "m_dPrice",
    "m_dTradedPrice", "m_dAveragePrice", "m_dAmount",
    "m_strTradeDate", "m_strTradeTime",
    # xttrader
    "account_id", "account_type", "stock_code", "order_type", "traded_id",
    "traded_time", "traded_price", "traded_volume", "traded_amount",
    "order_id", "order_sysid", "strategy_name", "order_remark",
    "volume", "price",
]
POS_FIELDS = [
    # classic
    "m_strInstrumentID", "m_strExchangeID", "m_nVolume", "m_nCanUseVolume",
    "m_nCanUseVol", "m_dOpenPrice", "m_strOpenDate", "m_strInstrumentName",
    # xttrader
    "account_id", "account_type", "stock_code", "volume", "can_use_volume",
    "open_price", "market_value", "frozen_volume", "on_road_volume",
    "yesterday_volume",
]
ACCOUNT_FIELDS = [
    # classic
    "m_dAvailable", "m_dBalance", "m_dInstrumentValue", "m_dPositionProfit",
    "m_strAccountID", "m_strAccountType",
    # xttrader
    "account_id", "account_type", "cash", "total_asset", "market_value",
    "available", "frozen_cash",
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
    _out("[PROBE] --- " + tag + " type=" +
         type(obj).__module__ + "." + type(obj).__name__ +
         " n_attrs=" + str(len(rows)) + " ('*' = via known-name list)")
    for k, v in sorted(rows, key=lambda x: x[0]):
        _out("[PROBE]   " + tag + "." + str(k) + " = " + str(v)[:70])


def _probe_account(acct, q):
    _out("[PROBE] ===== account=" + str(acct) + " =====")
    for kind, fields in (("ACCOUNT", ACCOUNT_FIELDS),
                         ("ORDER", ORDER_FIELDS),
                         ("DEAL", DEAL_FIELDS),
                         ("POSITION", POS_FIELDS)):
        try:
            objs = q(acct, "STOCK", kind) or []
            objs = list(objs)
            _out("[PROBE] " + kind + " n=" + str(len(objs)))
            if not objs:
                _out("[PROBE] " + kind + " EMPTY -> if EVERY kind is 0, the "
                     "account is probably NOT bound in the strategy config "
                     "(QMT classic API needs it registered); "
                     "ACCOUNT should normally return 1 object.")
            for ob in objs[-3:]:
                _dump(ob, kind, fields)
        except BaseException as e:
            _out("[PROBE] " + kind + " query fail: " + str(e)[:120])


def _ctor_param_names(cls):
    """Full, untruncated __init__ parameter names (excluding self).

    The xttype classes carry no __slots__/__annotations__; their field names
    live in the constructor signature (e.g. account_id, stock_code, order_id).
    """
    names = []
    try:
        import inspect
        sig = inspect.signature(cls.__init__)
        for p in list(sig.parameters.values())[1:]:
            names.append(p.name)
        return names
    except BaseException:
        pass
    try:
        code = cls.__init__.__code__
        return list(code.co_varnames[1:code.co_argcount])
    except BaseException:
        return []


def _placeholder(name):
    """A harmless placeholder value for a constructor parameter."""
    n = name.lower()
    for kw in ("code", "id", "name", "msg", "remark", "date", "time", "str"):
        if kw in n:
            return ""
    if "price" in n or "amount" in n or "balance" in n:
        return 0.0
    return 0


def _dump_type_schema():
    """Dump the CLASS schema of the order/trade/position types.

    Does not need a live order: QMT's get_trade_detail_data returns
    xtquant.xttype objects, whose field names are the __init__ parameter
    names. This prints the FULL signature (no truncation) and then tries to
    build a real instance with placeholder values and dump its attributes.
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
            params = _ctor_param_names(cls)
            _out("[PROBE]   " + tag + " CTOR_PARAMS n=" + str(len(params)) +
                 " -> " + ",".join(params))
            try:
                import inspect
                _out("[PROBE]   " + tag + " SIGNATURE = " +
                     str(inspect.signature(cls.__init__)))
            except BaseException as e:
                _out("[PROBE]   " + tag + " signature fail: " + str(e)[:90])
            doc = getattr(cls.__init__, "__doc__", None)
            if doc:
                _out("[PROBE]   " + tag + " __init__.__doc__ = " +
                     str(doc)[:200])
            # instance attrs: try the real constructor with placeholders,
            # then fall back to __new__ (no args) which still has the layout.
            inst = None
            try:
                inst = cls(**dict((p, _placeholder(p)) for p in params))
                _out("[PROBE]   " + tag + " constructed via ctor OK")
            except BaseException as e:
                _out("[PROBE]   " + tag + " ctor(*placeholders) fail: " +
                     str(e)[:110])
            if inst is None:
                try:
                    inst = cls.__new__(cls)
                    _out("[PROBE]   " + tag + " constructed via __new__ OK "
                         "(attrs may be unset)")
                except BaseException as e:
                    _out("[PROBE]   " + tag + " __new__ fail: " + str(e)[:90])
            if inst is not None:
                _dump(inst, tag + " <inst>", params)


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
    # PART 1 (DECISIVE): the REAL objects get_trade_detail_data returns.
    # type(obj) settles which API/naming the runtime uses.
    for a in accts:
        _probe_account(a, q)
    # PART 2 (REFERENCE ONLY): xtquant.xttrader class schema -- may NOT be
    # the type get_trade_detail_data returns.
    _out("[PROBE] ---- xtquant.xttype class schema (xttrader API; "
         "MAY NOT be what get_trade_detail_data returns) ----")
    _dump_type_schema()
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
