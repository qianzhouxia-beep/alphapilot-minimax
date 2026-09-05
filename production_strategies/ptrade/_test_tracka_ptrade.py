# -*- coding: utf-8 -*-
"""Ptrade Track A migration offline tests (P2 / sell / rotation).
Verifies that the PTRADE-PORTED core logic behaves identically to the QMT
v2.18 original. The strategy module is loaded without a Ptrade VM; all Ptrade
builtins + data helpers are stubbed so the pure logic runs locally.

Scenarios:
  1. _hold_days date format (%Y%m%d + %Y-%m-%d compat)
  2. profitable holding at T+2 14:45 -> t2_extended=True (no sell)
  3. loss holding at T+2 14:45 -> t2_force sell
  4. holdings full + P2 candidate -> rotation sells the WEAKEST position
  5. P2 no-chase guard: cand close > prev*(1+CONF_MAX_GAP) -> reject
  6. buy slip guard: live price > trig*(1+MAX_BUY_SLIP_PCT) -> hold off
  7. _p2_decide turnover gate: turnover > CONF_MAX_TURNOVER -> skip
  8. to_ptrade_code conversion (.SH -> .SS, bare 6-digit, .SZ passthrough)
"""
import importlib.util
import os
import sys
from pathlib import Path

STRAT_PATH = os.environ.get("PTRADE_STRAT",
                            r"C:\Users\elvisq\Projects\alphapilot\production_strategies\ptrade\TrackA_track_a_ptrade_sim.py")
STRAT = Path(STRAT_PATH)

spec = importlib.util.spec_from_file_location("tracka_ptrade", STRAT)
mod = importlib.util.module_from_spec(spec)
sys.modules["tracka_ptrade"] = mod


# ---- Ptrade builtins + helpers stubs (module-level names) ----
class _C:
    pass


def _get_snapshot(code):
    return SNAPS[code] if code in SNAPS else {}


def _get_price(code, count=None, frequency="1d", fields=None, fq="pre"):
    return PRICE.get(code, None)


def _get_positions():
    return POS


def _get_trades():
    return TRADES


def _order(code, amount, limit_price=None):
    ORDER_CALLS.append((code, amount, limit_price))
    return "oid_" + str(len(ORDER_CALLS))


def _get_individual_transaction(codes, data_count=50, is_dict=False):
    return TXN


def _set_universe(*a):
    pass


def _get_research_path():
    return ""


# dict stubs
SNAPS = {}
PRICE = {}
POS = {}
TRADES = []
TXN = {}
ORDER_CALLS = []
P2_RESULT = None          # (fill, reason) for rotation probe
QUOTE_STUB = None         # override get_quote entirely

# module-level injection map (builtins the strategy calls by bare name)
BUILTINS = {
    "get_snapshot": _get_snapshot,
    "get_price": _get_price,
    "get_positions": _get_positions,
    "get_trades": _get_trades,
    "order": _order,
    "get_individual_transaction": _get_individual_transaction,
    "set_universe": _set_universe,
    "get_research_path": _get_research_path,
}
for name, fn in BUILTINS.items():
    setattr(mod, name, fn)

# strategy-internal names that the module defines -- re-stub AFTER exec_module
def _sync_holdings(context, today):
    pass
mod._sync_holdings = _sync_holdings

def _load_candidates(context, date_str):
    return CAND
mod._load_candidates = _load_candidates

spec.loader.exec_module(mod)

# ---- re-stub after exec_module (module overwrites with real defs) ----
def _snap(code):
    return SNAPS.get(code, {})
mod._snap = _snap

def _order_locked(today, code, reason):
    return False
mod.order_locked = _order_locked

def _mark_order_locked(today, code, reason):
    pass
mod.mark_order_locked = _mark_order_locked

def _load_order_locks_ctx(context):
    return {}
mod._load_order_locks_ctx = _load_order_locks_ctx

def _safe_write(path, obj):
    return True
mod._safe_write = _safe_write

def _safe_read(path, dflt):
    return dflt
mod._safe_read = _safe_read

def _lock_path():
    return ""
mod._lock_path = _lock_path

def _trade_log_path():
    return ""
mod._trade_log_path = _trade_log_path

def _log_trade(memo, action, code, price, vol, reason):
    TRADE_CALLS.append((action, code, price, vol, reason))
mod.log_trade = _log_trade

def _get_quote(code):
    if QUOTE_STUB:
        return QUOTE_STUB(code)
    return (SNAPS.get(code, {}).get("last_px"),
            SNAPS.get(code, {}).get("preclose_px"),
            SNAPS.get(code, {}).get("open_px"),
            SNAPS.get(code, {}).get("high_px"))
mod._get_quote = _get_quote

def _do_sell(context, code, pos, price, reason):
    SELL_CALLS.append((code, reason))
    context.position_map.pop(code, None)
mod._do_sell = _do_sell

def _do_sell_half(context, code, pos, price, reason):
    SELL_HALF_CALLS.append((code, reason))
mod._do_sell_half = _do_sell_half

def _p2_decide(code, now_min):
    if P2_RESULT:
        return P2_RESULT
    return (None, "wait_confirm")
REAL_P2_DECIDE = mod._p2_decide    # capture the REAL P2 logic before stubbing
mod._p2_decide = _p2_decide

def _volume_ratio_of(code):
    return None
mod._volume_ratio_of = _volume_ratio_of

def _get_prev_close(code):
    return SNAPS.get(code, {}).get("preclose_px")
mod._get_prev_close = _get_prev_close

def _adaptive_params(code):
    return (-0.10, 0.03, 0.015)
mod._adaptive_params = _adaptive_params

def _day_vwap(code):
    return None
mod._day_vwap = _day_vwap

def _wyckoff_holding_bc(code, peak):
    return False
mod._wyckoff_holding_bc = _wyckoff_holding_bc

def _t2_force_floor(code):
    # QMT test scenario: day-amplitude data unavailable (0.0) + annual vol =
    # baseline (0.30) -> tol=0 -> floor=0.0. A -5% loss thus force-sells.
    return 0.0
mod._t2_force_floor = _t2_force_floor

SELL_CALLS = []
SELL_HALF_CALLS = []
TRADE_CALLS = []
CAND = None

passed = 0
failed = 0


def check(name, cond):
    global passed, failed
    if cond:
        passed += 1
        print("  PASS " + name)
    else:
        failed += 1
        print("  FAIL " + name)


# ============ TEST 1: code conversion ============
print("\n[1] to_ptrade_code / to_6")
check("600519.SH -> 600519.SS", mod.to_ptrade_code("600519.SH") == "600519.SS")
check("000001.SZ passthrough", mod.to_ptrade_code("000001.SZ") == "000001.SZ")
check("bare 600519 -> 600519.SS", mod.to_ptrade_code("600519") == "600519.SS")
check("sh600519 -> 600519.SS", mod.to_ptrade_code("sh600519") == "600519.SS")
check("830799.BJ passthrough", mod.to_ptrade_code("830799.BJ") == "830799.BJ")
check("to_6 600519.SS -> 600519", mod.to_6("600519.SS") == "600519")

# ============ TEST 2: _hold_days ============
print("\n[2] _hold_days")
pos = {"buy_date": "20260817"}
check("buy 08-17, today 08-18 -> 1 day", mod._hold_days(pos, "20260818") == 1)
pos2 = {"buy_date": "2026-08-16"}
check("compat 'YYYY-MM-DD' -> 2 days", mod._hold_days(pos2, "20260818") == 2)
check("missing buy_date -> 999", mod._hold_days({}, "20260818") == 999)

# ============ TEST 3: T+2 profit -> extend ============
print("\n[3] T+2 conditional: profit -> extend")
C = _C()
C.position_map = {
    "600519.SS": {
        "shares": 1000, "can_use": 1000, "buy_price": 100.0,
        "buy_date": "20260816", "peak": 105.0, "trail_armed": False,
        "awaiting_new_high": False, "peel_peak_snapshot": 100.0,
        "peel_count": 0, "t2_extended": False, "vwap_broken": False,
        "wy_bc_armed": False, "pending": False, "today_high": 103.0,
    },
}
SNAPS["600519.SS"] = {"last_px": 102.0, "preclose_px": 100.0,
                      "open_px": 101.0, "high_px": 103.0}
SELL_CALLS.clear(); SELL_HALF_CALLS.clear()
mod._check_sell(C, None, mod.T2_FORCE_HHMM, "20260818")
check("profit holding NOT sold at T+2", len(SELL_CALLS) == 0 and len(SELL_HALF_CALLS) == 0)
check("t2_extended set True", C.position_map["600519.SS"].get("t2_extended") is True)

# ============ TEST 4: T+2 loss -> force sell ============
print("\n[4] T+2 conditional: loss -> t2_force")
C2 = _C()
C2.position_map = {
    "000001.SZ": {
        "shares": 1000, "can_use": 1000, "buy_price": 100.0,
        "buy_date": "20260816", "peak": 100.0, "trail_armed": False,
        "awaiting_new_high": False, "peel_peak_snapshot": 100.0,
        "peel_count": 0, "t2_extended": False, "vwap_broken": False,
        "wy_bc_armed": False, "pending": False, "today_high": 96.0,
    },
}
SNAPS["000001.SZ"] = {"last_px": 95.0, "preclose_px": 100.0,
                      "open_px": 95.0, "high_px": 96.0}
SELL_CALLS.clear(); SELL_HALF_CALLS.clear()
mod._check_sell(C2, None, mod.T2_FORCE_HHMM, "20260818")
check("loss holding force-sold", len(SELL_CALLS) == 1 and SELL_CALLS[0][0] == "000001.SZ")
check("reason contains t2_force", "t2_force" in SELL_CALLS[0][1])
check("position popped", "000001.SZ" not in C2.position_map)

# ============ TEST 5: rotation sells weakest ============
print("\n[5] Rotation: full holdings + P2 pass -> sell weakest")
C3 = _C()
C3.sent_today = set()
C3.memo = {"trade_log": []}
pos_map = {}
pos_map["600001.SS"] = {
    "shares": 1000, "can_use": 1000, "buy_price": 100.0, "buy_date": "20260816",
    "peak": 103.0, "trail_armed": True, "awaiting_new_high": False,
    "peel_peak_snapshot": 100.0, "peel_count": 0, "t2_extended": False,
    "vwap_broken": False, "wy_bc_armed": False, "pending": False, "today_high": 104.0,
}
pos_map["600002.SS"] = {
    "shares": 1000, "can_use": 1000, "buy_price": 100.0, "buy_date": "20260816",
    "peak": 100.0, "trail_armed": False, "awaiting_new_high": False,
    "peel_peak_snapshot": 100.0, "peel_count": 0, "t2_extended": False,
    "vwap_broken": False, "wy_bc_armed": False, "pending": False, "today_high": 97.0,
}
pos_map["600003.SS"] = {"shares": 500, "can_use": 500, "buy_price": 50.0,
    "buy_date": "20260816", "peak": 51.0, "trail_armed": False,
    "awaiting_new_high": False, "peel_peak_snapshot": 50.0, "peel_count": 0,
    "t2_extended": False, "vwap_broken": False, "wy_bc_armed": False, "pending": False, "today_high": 51.0}
pos_map["600004.SS"] = {"shares": 500, "can_use": 500, "buy_price": 50.0,
    "buy_date": "20260816", "peak": 51.0, "trail_armed": False,
    "awaiting_new_high": False, "peel_peak_snapshot": 50.0, "peel_count": 0,
    "t2_extended": False, "vwap_broken": False, "wy_bc_armed": False, "pending": False, "today_high": 51.0}
C3.position_map = pos_map
SNAPS["600001.SS"] = {"last_px": 103.0, "preclose_px": 100.0, "open_px": 102.0, "high_px": 104.0}
SNAPS["600002.SS"] = {"last_px": 96.0, "preclose_px": 100.0, "open_px": 96.0, "high_px": 97.0}
SNAPS["600003.SS"] = {"last_px": 50.5, "preclose_px": 50.0, "open_px": 50.5, "high_px": 51.0}
SNAPS["600004.SS"] = {"last_px": 50.5, "preclose_px": 50.0, "open_px": 50.5, "high_px": 51.0}
P2_RESULT = (10.0, "dyn_confirm")
SELL_CALLS.clear(); SELL_HALF_CALLS.clear(); TRADE_CALLS.clear()

class _PF:
    cash = 1000000.0
    portfolio_value = 2000000.0
C3.portfolio = _PF()

# stub portfolio_cash_total to use context.portfolio
def _pct(context):
    return float(context.portfolio.cash), float(context.portfolio.portfolio_value)
mod.portfolio_cash_total = _pct

mod._check_buy(C3, None, 10 * 60 + 20, "20260818",
               [{"symbol": "300999.SZ", "rank": 1}])
check("rotation sold exactly 1", len(SELL_CALLS) == 1)
check("weakest sold is 600002 (-4%)",
      SELL_CALLS[0][0] == "600002.SS" if SELL_CALLS else False)
check("rotation reason tagged", bool(SELL_CALLS) and "rotation" in SELL_CALLS[0][1])

# ============ TEST 6: P2 no-chase guard ============
print("\n[6] P2 no-chase guard")
# build 5m bars: first bar close = p935, second bar close above prev*(1+CONF_MAX_GAP)
# prev close = 10.0 -> CONF_MAX_GAP=0.08 -> reject when c > 10.8
bars = [(575, 10.0, 10.2, 10.3, 9.9, 200000),      # 09:35
        (580, 10.2, 11.0, 11.1, 10.1, 400000)]     # 09:40 c=11.0 > 10.8 -> no-chase
def _get_m5_bars(code, today_str=None):
    return bars
mod.get_m5_bars = _get_m5_bars
SNAPS["000002.SZ"] = {"last_px": 11.0, "preclose_px": 10.0,
                      "open_px": 10.2, "high_px": 11.1,
                      "turnover_ratio": 1.0}
fill, reason = REAL_P2_DECIDE("000002.SZ", 9 * 60 + 41)
check("no-chase rejects gap-up close", fill is None and reason == "wait_confirm")

# ============ TEST 7: P2 turnover gate ============
print("\n[7] P2 turnover gate")
SNAPS["000002.SZ"]["turnover_ratio"] = 6.0   # > CONF_MAX_TURNOVER=5.0
fill, reason = REAL_P2_DECIDE("000002.SZ", 9 * 60 + 41)
check("high turnover -> skip_high_turnover", reason == "skip_high_turnover")

# ============ TEST 8: buy slip guard ============
print("\n[8] buy slip guard")
C4 = _C()
C4.sent_today = set()
C4.memo = {"trade_log": []}
C4.position_map = {}
C4.portfolio = _PF()
P2_RESULT = (10.0, "dyn_confirm")   # trig 10.0
SNAPS["300999.SZ"] = {"last_px": 10.5, "preclose_px": 10.0, "open_px": 10.2, "high_px": 10.5,
                      "turnover_ratio": 1.0, "up_px": 11.0}
QUOTE_STUB = None
# live = last_px = 10.5 > 10.0*(1+0.02)=10.2 -> slip guard holds off
ORDER_CALLS.clear()
# _get_last uses _snap's last_px
def _get_last(code):
    return SNAPS.get(code, {}).get("last_px")
mod._get_last = _get_last
mod._check_buy(C4, None, 10 * 60 + 20, "20260818",
               [{"symbol": "300999.SZ", "rank": 1}])
check("slip guard held off buy (no order)", len(ORDER_CALLS) == 0)

# ============ TEST 9: _recover_buy_date ============
print("\n[9] _recover_buy_date")
memo = {"trade_log": [
    {"time": "2026-08-10 10:00:00", "action": "BUY", "symbol": "600519.SH",
     "price": 100.0, "volume": 100},
    {"time": "2026-08-15 14:45:00", "action": "SELL", "symbol": "600519.SH",
     "price": 105.0, "volume": 100},
    {"time": "2026-08-19 09:49:36", "action": "BUY", "symbol": "600519.SH",
     "price": 108.0, "volume": 200},
]}
check("latest BUY recovered", mod._recover_buy_date(memo, "600519.SH") == "20260819")
check("bare code matches suffixed log", mod._recover_buy_date(memo, "600519") == "20260819")
check(".SS form matches .SH log", mod._recover_buy_date(memo, "600519.SS") == "20260819")
check("unknown symbol -> ''", mod._recover_buy_date(memo, "000001.SZ") == "")
memo2 = {"trade_log": []}
check("empty log -> ''", mod._recover_buy_date(memo2, "600519.SH") == "")
memo3 = {}
check("missing trade_log key -> ''", mod._recover_buy_date(memo3, "600519.SH") == "")

# ============ TEST 10: T+2 999 guard (unknown buy_date) ============
print("\n[10] T+2 999 guard: unknown buy_date never force-sells a winner")
C9 = _C()
C9.position_map = {
    "600519.SS": {
        "shares": 1000, "can_use": 1000, "buy_price": 100.0,
        "buy_date": "", "peak": 105.0, "trail_armed": False,
        "awaiting_new_high": False, "peel_peak_snapshot": 100.0,
        "peel_count": 0, "t2_extended": False, "vwap_broken": False,
        "wy_bc_armed": False, "pending": False, "today_high": 103.0,
    },
}
SNAPS["600519.SS"] = {"last_px": 102.0, "preclose_px": 100.0,
                      "open_px": 101.0, "high_px": 103.0}
SELL_CALLS.clear(); SELL_HALF_CALLS.clear()
mod._check_sell(C9, None, mod.T2_FORCE_HHMM, "20260818")
check("T+1 winner with unknown bd NOT force-sold", len(SELL_CALLS) == 0 and len(SELL_HALF_CALLS) == 0)
check("still extended (t2_extended True)", C9.position_map["600519.SS"].get("t2_extended") is True)

print("\n===== %d passed, %d failed =====" % (passed, failed))
sys.exit(1 if failed else 0)
