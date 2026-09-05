# -*- coding: utf-8 -*-
"""v1.5 rotation hardening tests for Track B QMT sim (2026-08-18, DSH review).
Mirrors the Track A v2.16 tests:
  1. T+1 protection: holding bought yesterday (hold_days=1) is immune to rotation.
  2. Hysteresis gate (ROTATION_WEAK_GATE): healthy weakest holding is not rotated.
  3. Daily rotation cap (ROTATION_DAILY_MAX=1): second rotation same day is blocked.
"""
import importlib.util
import sys
from pathlib import Path

STRAT = Path(r"C:\Users\elvisq\Projects\alphapilot\production_strategies\track_b\TrackB_track_b_qmt_auction_sim.py")

spec = importlib.util.spec_from_file_location("trackb_v15", STRAT)
mod = importlib.util.module_from_spec(spec)
sys.modules["trackb_v15"] = mod

class _C:
    pass

def _qmt_code(s): return s
def _is_limit_up(*a): return False
def _wyckoff_distribution(*a): return False
def _board_allowed(*a): return True
def _load_candidates(*a): return None
def _load_scores(*a): return None
def _sync_holdings(*a): pass
def _snap_daily(*a): pass
def _log_trade(*a): pass
def _adaptive_params(*a): return (-0.10, 0.03, 0.015)
def _is_trading_time(*a): return True
def passorder(*a): return 0
def _annual_vol(*a): return 0.3
def _get_prev_day_vwap(*a): return None
def _wyckoff_holding_bc(*a): return False
def _is_today_buy(*a): return False

for name, fn in [
    ("_qmt_code", _qmt_code), ("_is_limit_up", _is_limit_up),
    ("_wyckoff_distribution", _wyckoff_distribution), ("_board_allowed", _board_allowed),
    ("_load_candidates", _load_candidates), ("_load_scores", _load_scores),
    ("_sync_holdings", _sync_holdings), ("_snap_daily", _snap_daily),
    ("_log_trade", _log_trade), ("_adaptive_params", _adaptive_params),
    ("_is_trading_time", _is_trading_time), ("passorder", passorder),
    ("_annual_vol", _annual_vol), ("_get_prev_day_vwap", _get_prev_day_vwap),
    ("_wyckoff_holding_bc", _wyckoff_holding_bc), ("_is_today_buy", _is_today_buy),
]:
    setattr(mod, name, fn)
spec.loader.exec_module(mod)

LOCKS = {}

def _order_locked(today, code, reason):
    return bool(LOCKS.get(today, {}).get(code, {}).get(reason, False))

def _mark_order_locked(today, code, reason):
    LOCKS.setdefault(today, {}).setdefault(code, {})[reason] = True

def _load_order_locks():
    return LOCKS

mod._order_locked = _order_locked
mod._mark_order_locked = _mark_order_locked
mod._load_order_locks = _load_order_locks

QUOTES = {}
PREV_CLOSE = {}
VWAPS = {}
SELL_CALLS = []

def _get_quote(C, code):
    return QUOTES.get(code, (None, None, None, None))
mod._get_quote = _get_quote

def _get_prev_close(C, code):
    return PREV_CLOSE.get(code)
mod._get_prev_close = _get_prev_close

def _day_vwap(C, code):
    return VWAPS.get(code)
mod._day_vwap = _day_vwap

def _get_volume_ratio(C, code):
    return None
mod._get_volume_ratio = _get_volume_ratio

def _do_sell(C, code, pos, price, reason):
    SELL_CALLS.append((code, reason))
    C.position_map.pop(code, None)
mod._do_sell = _do_sell

def _do_sell_half(C, code, pos, price, reason):
    SELL_CALLS.append((code, reason))
mod._do_sell_half = _do_sell_half

def mkpos(buy_date, buy_price=100.0):
    return {
        "shares": 1000, "can_use": 1000, "buy_price": buy_price,
        "buy_date": buy_date, "peak": buy_price, "trail_armed": False,
        "awaiting_new_high": False, "peel_peak_snapshot": buy_price,
        "peel_count": 0, "t2_extended": False, "vwap_broken": False,
        "wy_bc_armed": False, "pending": False,
    }

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

TODAY = "20260818"

# ============ TEST 1: T+1 immunity ============
print("\n[1] Rotation: T+1 holding (bought yesterday) is immune")
C = _C()
C.position_map = {
    "600100.SH": mkpos("20260817", 100.0),   # hold 1 day - weakest, must be immune
    "600002.SH": mkpos("20260816", 100.0),   # hold 2 days - weakest among sellable
    "600003.SH": mkpos("20260816", 50.0),
    "600004.SH": mkpos("20260816", 50.0),
}
QUOTES["600100.SH"] = (80.0, 100.0, 82.0, 90.0)
QUOTES["600002.SH"] = (96.0, 100.0, 96.0, 97.0)
QUOTES["600003.SH"] = (50.5, 50.0, 50.5, 51.0)
QUOTES["600004.SH"] = (50.5, 50.0, 50.5, 51.0)
PREV_CLOSE = {"600100.SH": 100.0, "600002.SH": 100.0,
              "600003.SH": 50.0, "600004.SH": 50.0}
VWAPS = {"600002.SH": 97.0, "600003.SH": 50.0, "600004.SH": 50.0}
LOCKS.clear(); SELL_CALLS.clear()
sold = mod._rotation_sell(C, None, 10 * 60 + 20, TODAY, mod.ROTATION_SELL_N)
check("T+1 weakest (600100) NOT sold", "600100.SH" not in sold)
check("600100 still held", "600100.SH" in C.position_map)
check("rotated out 600002 (weakest sellable)", sold == ["600002.SH"])

# ============ TEST 2: hysteresis gate - healthy weakest not churned ============
print("\n[2] Hysteresis: weakest-but-healthy holding is NOT rotated")
C2 = _C()
C2.position_map = {
    "600001.SH": mkpos("20260816", 100.0),
    "600002.SH": mkpos("20260816", 100.0),   # relatively weakest but healthy
    "600003.SH": mkpos("20260816", 100.0),
    "600004.SH": mkpos("20260816", 100.0),
}
QUOTES["600001.SH"] = (103.0, 100.0, 102.0, 104.0)
QUOTES["600002.SH"] = (101.5, 100.0, 101.0, 102.0)
QUOTES["600003.SH"] = (104.0, 100.0, 103.0, 105.0)
QUOTES["600004.SH"] = (102.0, 100.0, 101.5, 103.0)
PREV_CLOSE = {"600001.SH": 100.0, "600002.SH": 101.0,
              "600003.SH": 100.0, "600004.SH": 100.0}
VWAPS = {"600001.SH": 101.0, "600002.SH": 100.5,
         "600003.SH": 102.0, "600004.SH": 100.5}
LOCKS.clear(); SELL_CALLS.clear()
sold = mod._rotation_sell(C2, None, 10 * 60 + 20, TODAY, mod.ROTATION_SELL_N)
check("rotation skipped (no weakness signal)", sold == [])
check("no sell fired", len(SELL_CALLS) == 0)
check("all holdings kept", len(C2.position_map) == 4)

# ============ TEST 3: daily rotation cap ============
print("\n[3] Daily cap: second rotation same day is blocked")
C3 = _C()
def fresh_map():
    return {
        "600001.SH": mkpos("20260816", 100.0),
        "600002.SH": mkpos("20260816", 100.0),
        "600003.SH": mkpos("20260816", 100.0),
        "600004.SH": mkpos("20260816", 100.0),
    }
QUOTES.update({
    "600001.SH": (96.0, 100.0, 96.0, 97.0),
    "600002.SH": (96.0, 100.0, 96.0, 97.0),
    "600003.SH": (103.0, 100.0, 102.0, 104.0),
    "600004.SH": (102.0, 100.0, 101.5, 103.0),
})
PREV_CLOSE.update({"600001.SH": 100.0, "600002.SH": 100.0,
                   "600003.SH": 100.0, "600004.SH": 100.0})
VWAPS.update({"600001.SH": 97.0, "600002.SH": 97.0,
              "600003.SH": 101.0, "600004.SH": 100.5})
LOCKS.clear(); SELL_CALLS.clear()
C3.position_map = fresh_map()
sold1 = mod._rotation_sell(C3, None, 10 * 60 + 20, TODAY, mod.ROTATION_SELL_N)
check("first rotation fires (1 sold)", len(sold1) == 1 and len(SELL_CALLS) == 1)
C3.position_map.update(fresh_map())
C3.position_map["600005.SH"] = mkpos("20260816", 100.0)
QUOTES["600005.SH"] = (96.0, 100.0, 96.0, 97.0)
PREV_CLOSE["600005.SH"] = 100.0
VWAPS["600005.SH"] = 97.0
sold2 = mod._rotation_sell(C3, None, 10 * 60 + 30, TODAY, mod.ROTATION_SELL_N)
check("second rotation same day blocked by __ROT__ lock", sold2 == [])
check("no second sell fired", len(SELL_CALLS) == 1)

print(f"\n===== {passed} passed, {failed} failed =====")
sys.exit(1 if failed else 0)
