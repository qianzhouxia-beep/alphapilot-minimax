# -*- coding: utf-8 -*-
"""v2.15 sell-side rework offline tests: T+2 conditional + weakness rotation.
Scenarios (DHS patch F section):
  1. profitable holding at T+2 14:45 -> t2_extended=True (extend to T+3)
  2. loss holding at T+2 14:45 -> t2_force sell
  3. holdings full (MAX_HOLDINGS) + candidate passed P2 -> rotation sells weakest
Also verifies _hold_days date-format fix (%Y%m%d).
"""
import importlib.util
import sys
from pathlib import Path

STRAT = Path(r"C:\Users\elvisq\Projects\alphapilot\production_strategies\track_a\TrackA_track_a_qmt_full_chain_sim.py")

# load strategy as a module without executing QMT init/handlebar
spec = importlib.util.spec_from_file_location("tracka_v215", STRAT)
mod = importlib.util.module_from_spec(spec)
sys.modules["tracka_v215"] = mod
# stub QMT builtins so top-level defs survive import
class _C:
    pass
def _qmt_code(s): return s
def _is_limit_up(*a): return False
def _wyckoff_distribution(*a): return False
def _board_allowed(*a): return True
def _order_locked(*a): return False
def _mark_order_locked(*a): pass
def _load_order_locks(): return {}
def _load_candidates(*a): return None
def _load_scores(*a): return None
def _sync_holdings(*a): pass
def _snap_daily(*a): pass
def _log_trade(*a): pass
def _get_prev_close(*a): return 10.0
def _adaptive_params(*a): return (-0.10, 0.03, 0.015)
def _day_vwap(*a): return None
def _is_trading_time(*a): return True
def passorder(*a): return 0
def get_trade_detail_data(*a): return []
def _annual_vol(*a): return 0.3
def _get_prev_day_vwap(*a): return None
def _wyckoff_holding_bc(*a): return False

for name, fn in [
    ("_qmt_code", _qmt_code), ("_is_limit_up", _is_limit_up),
    ("_wyckoff_distribution", _wyckoff_distribution), ("_board_allowed", _board_allowed),
    ("_order_locked", _order_locked), ("_mark_order_locked", _mark_order_locked),
    ("_load_order_locks", _load_order_locks), ("_load_candidates", _load_candidates),
    ("_load_scores", _load_scores), ("_sync_holdings", _sync_holdings),
    ("_snap_daily", _snap_daily), ("_log_trade", _log_trade),
    ("_get_prev_close", _get_prev_close), ("_adaptive_params", _adaptive_params),
    ("_day_vwap", _day_vwap), ("_is_trading_time", _is_trading_time),
    ("passorder", passorder), ("get_trade_detail_data", get_trade_detail_data),
    ("_annual_vol", _annual_vol), ("_get_prev_day_vwap", _get_prev_day_vwap),
    ("_wyckoff_holding_bc", _wyckoff_holding_bc),
]:
    setattr(mod, name, fn)
spec.loader.exec_module(mod)

# ---- stubs that the MODULE overrides on import, so re-stub AFTER exec_module ----
QUOTES = {}          # code -> (price, prev, open, high)
SELL_CALLS = []      # (fn, code, reason)
SELL_HALF_CALLS = []
P2_RESULT = None     # (fill, reason) returned by _p2_decide during rotation probe

def _get_quote(C, code):
    q = QUOTES.get(code)
    return q if q else (None, None, None, None)
mod._get_quote = _get_quote

def _do_sell(C, code, pos, price, reason):
    SELL_CALLS.append((code, reason))
    C.position_map.pop(code, None)
mod._do_sell = _do_sell

def _do_sell_half(C, code, pos, price, reason):
    SELL_HALF_CALLS.append((code, reason))
mod._do_sell_half = _do_sell_half

def _p2_decide(C, code, now_min):
    if P2_RESULT:
        return P2_RESULT
    return (None, "wait_confirm")
mod._p2_decide = _p2_decide

def _volume_ratio_of(C, code):
    return None   # momentum guard soft-skip (data unavailable)
mod._volume_ratio_of = _volume_ratio_of

def _load_order_locks():
    return {}     # no BUY locks today -> today_bought=0
mod._load_order_locks = _load_order_locks

def _get_trade_detail_data(*a):
    class _Acct: pass
    o = _Acct(); o.m_dAvailable = 1000000.0; o.m_dBalance = 2000000.0
    return [o]
mod.get_trade_detail_data = _get_trade_detail_data

def _get_quote_price(C, code):
    return QUOTES.get(code, (None, None, None, None))
mod._get_quote = _get_quote_price

passed = 0
failed = 0

def check(name, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS {name}")
    else:
        failed += 1
        print(f"  FAIL {name}")


# ============ TEST 1: _hold_days date format fix ============
print("\n[1] _hold_days (%Y%m%d + %Y-%m-%d)")
pos = {"buy_date": "20260817"}
d1 = mod._hold_days(pos, "20260818")
check("buy 08-17, today 08-18 -> 1 day", d1 == 1)
pos2 = {"buy_date": "2026-08-16"}
d2 = mod._hold_days(pos2, "20260818")
check("compat 'YYYY-MM-DD' -> 2 days", d2 == 2)
check("missing buy_date -> 999", mod._hold_days({}, "20260818") == 999)

# ============ TEST 2: profitable holding at T+2 14:45 -> extend ============
print("\n[2] T+2 conditional: profit -> extend (t2_extended=True)")
C = _C()
C.position_map = {
    "600519.SH": {
        "shares": 1000, "can_use": 1000, "buy_price": 100.0,
        "buy_date": "20260814",   # today 08-18 -> hold 4 days? use fresh below
        "peak": 105.0, "trail_armed": False, "awaiting_new_high": False,
        "peel_peak_snapshot": 100.0, "peel_count": 0, "t2_extended": False,
        "vwap_broken": False, "wy_bc_armed": False, "pending": False,
    },
}
# make it held exactly 2 days -> T+2 day
C.position_map["600519.SH"]["buy_date"] = "20260816"   # 08-18 -> 2 days
QUOTES["600519.SH"] = (102.0, 100.0, 101.0, 103.0)    # profit +2%, above VWAP
SELL_CALLS.clear(); SELL_HALF_CALLS.clear()
now_min = mod.T2_FORCE_HHMM   # 14:45
mod._check_sell(C, None, now_min, "20260818")
check("profit holding NOT sold at T+2", len(SELL_CALLS) == 0 and len(SELL_HALF_CALLS) == 0)
check("t2_extended set True", C.position_map["600519.SH"].get("t2_extended") is True)

# ============ TEST 3: loss holding at T+2 14:45 -> force sell ============
print("\n[3] T+2 conditional: loss -> t2_force")
C2 = _C()
C2.position_map = {
    "000001.SZ": {
        "shares": 1000, "can_use": 1000, "buy_price": 100.0,
        "buy_date": "20260816", "peak": 100.0, "trail_armed": False,
        "awaiting_new_high": False, "peel_peak_snapshot": 100.0,
        "peel_count": 0, "t2_extended": False, "vwap_broken": False,
        "wy_bc_armed": False, "pending": False,
    },
}
QUOTES["000001.SZ"] = (95.0, 100.0, 95.0, 96.0)   # -5% loss
SELL_CALLS.clear(); SELL_HALF_CALLS.clear()
now_min = mod.T2_FORCE_HHMM
mod._check_sell(C2, None, now_min, "20260818")
check("loss holding force-sold", len(SELL_CALLS) == 1 and SELL_CALLS[0][0] == "000001.SZ")
check("reason contains t2_force", "t2_force" in SELL_CALLS[0][1])
check("position popped", "000001.SZ" not in C2.position_map)

# ============ TEST 4: holdings full + P2 candidate -> rotation sells weakest ============
print("\n[4] Rotation: full holdings + P2 pass -> sell weakest")
C3 = _C()
C3.sent_today = set()
pos_map = {}
# two positions: one strong (profit, above vwap), one weak (loss, below vwap)
pos_map["600001.SH"] = {
    "shares": 1000, "can_use": 1000, "buy_price": 100.0, "buy_date": "20260816",
    "peak": 103.0, "trail_armed": True, "awaiting_new_high": False,
    "peel_peak_snapshot": 100.0, "peel_count": 0, "t2_extended": False,
    "vwap_broken": False, "wy_bc_armed": False, "pending": False,
}
pos_map["600002.SH"] = {
    "shares": 1000, "can_use": 1000, "buy_price": 100.0, "buy_date": "20260816",
    "peak": 100.0, "trail_armed": False, "awaiting_new_high": False,
    "peel_peak_snapshot": 100.0, "peel_count": 0, "t2_extended": False,
    "vwap_broken": False, "wy_bc_armed": False, "pending": False,
}
C3.position_map = pos_map
QUOTES["600001.SH"] = (103.0, 100.0, 102.0, 104.0)   # +3% strong
QUOTES["600002.SH"] = (96.0, 100.0, 96.0, 97.0)     # -4% weak
# full -> add 2 more to reach MAX_HOLDINGS=4
pos_map["600003.SH"] = {"shares": 500, "can_use": 500, "buy_price": 50.0,
    "buy_date": "20260816", "peak": 51.0, "trail_armed": False,
    "awaiting_new_high": False, "peel_peak_snapshot": 50.0, "peel_count": 0,
    "t2_extended": False, "vwap_broken": False, "wy_bc_armed": False, "pending": False}
pos_map["600004.SH"] = {"shares": 500, "can_use": 500, "buy_price": 50.0,
    "buy_date": "20260816", "peak": 51.0, "trail_armed": False,
    "awaiting_new_high": False, "peel_peak_snapshot": 50.0, "peel_count": 0,
    "t2_extended": False, "vwap_broken": False, "wy_bc_armed": False, "pending": False}
QUOTES["600003.SH"] = (50.5, 50.0, 50.5, 51.0)   # +1%
QUOTES["600004.SH"] = (50.5, 50.0, 50.5, 51.0)   # +1%
P2_RESULT = (10.0, "dyn_confirm")   # candidate passed P2
SELL_CALLS.clear(); SELL_HALF_CALLS.clear()
mod._check_buy(C3, None, 10 * 60 + 20, "20260818",
               [{"symbol": "300999.SZ", "rank": 1}])
check("rotation sold exactly 1", len(SELL_CALLS) == 1)
check("weakest sold is 600002 (-4%)",
      SELL_CALLS[0][0] == "600002.SH" if SELL_CALLS else False)
check("rotation reason tagged", bool(SELL_CALLS) and "rotation" in SELL_CALLS[0][1])

print(f"\n===== {passed} passed, {failed} failed =====")
sys.exit(1 if failed else 0)
