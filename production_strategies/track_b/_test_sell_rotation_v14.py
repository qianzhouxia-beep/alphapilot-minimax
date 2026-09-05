# -*- coding: utf-8 -*-
"""v1.4 sell-side rework offline tests for Track B QMT SIM/LIVE:
T+2 conditional + weakness rotation. Verifies the same scenarios as the
Track A v2.15 test but against the Track B codebase (auction strategy)."""
import importlib.util
import sys
from pathlib import Path

STRAT = Path(r"C:\Users\elvisq\Projects\alphapilot\production_strategies\track_b\TrackB_track_b_qmt_auction_sim.py")

spec = importlib.util.spec_from_file_location("trackb_v14", STRAT)
mod = importlib.util.module_from_spec(spec)
sys.modules["trackb_v14"] = mod

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
def _get_prev_close(*a): return 10.0
def _adaptive_params(*a): return (-0.10, 0.03, 0.015)
def _day_vwap(*a): return None
def _is_trading_time(*a): return True
def passorder(*a): return 0
def get_trade_detail_data(*a): return []
def _annual_vol(*a): return 0.3
def _get_prev_day_vwap(*a): return None
def _wyckoff_holding_bc(*a): return False
def _closed_5m_bars(*a): return 48
def _get_volume_ratio(*a): return None
def _get_m5_bars(*a): return None
def _bar_times(*a): return []
def _vol_ma5(*a): return 0.0
def _p1_gate(*a): pass
def _p2_gate(*a): return []
def _update_auction_state(*a): pass
def _is_auction_eligible(*a): return True
def _dump_gate(*a): pass
def _live_pool_survivors(*a): return []
def _load_remote_json(*a): return None
def _fetch_remote(*a): return None
def _load_fullpool(*a): return []
def _load_fullpool_live(*a): return []
def _sector_gap(*a): return 0.0
def _day_gap(*a): return 0.0
def _save_json(*a): pass
def _snap(*a): return None
def _last_price(*a): return None
def _load_json(*a): return None
def _find_quote(*a): return None
def _query_cash(*a): return (1000000.0, 2000000.0)

for name, fn in [
    ("_qmt_code", _qmt_code), ("_is_limit_up", _is_limit_up),
    ("_wyckoff_distribution", _wyckoff_distribution), ("_board_allowed", _board_allowed),
    ("_order_locked", _order_locked), ("_mark_order_locked", _mark_order_locked),
    ("_load_order_locks", _load_order_locks), ("_load_candidates", _load_candidates),
    ("_load_scores", _load_scores), ("_sync_holdings", _sync_holdings),
    ("_snap_daily", _snap_daily), ("_get_prev_close", _get_prev_close),
    ("_adaptive_params", _adaptive_params), ("_day_vwap", _day_vwap),
    ("_is_trading_time", _is_trading_time), ("passorder", passorder),
    ("get_trade_detail_data", get_trade_detail_data), ("_annual_vol", _annual_vol),
    ("_get_prev_day_vwap", _get_prev_day_vwap), ("_wyckoff_holding_bc", _wyckoff_holding_bc),
    ("_closed_5m_bars", _closed_5m_bars), ("_get_volume_ratio", _get_volume_ratio),
    ("_get_m5_bars", _get_m5_bars), ("_bar_times", _bar_times), ("_vol_ma5", _vol_ma5),
    ("_p1_gate", _p1_gate), ("_p2_gate", _p2_gate),
    ("_update_auction_state", _update_auction_state),
    ("_is_auction_eligible", _is_auction_eligible), ("_dump_gate", _dump_gate),
    ("_live_pool_survivors", _live_pool_survivors),
    ("_load_remote_json", _load_remote_json), ("_fetch_remote", _fetch_remote),
    ("_load_fullpool", _load_fullpool), ("_load_fullpool_live", _load_fullpool_live),
    ("_sector_gap", _sector_gap), ("_day_gap", _day_gap), ("_save_json", _save_json),
    ("_snap", _snap), ("_last_price", _last_price), ("_load_json", _load_json),
    ("_find_quote", _find_quote), ("_query_cash", _query_cash),
]:
    setattr(mod, name, fn)
spec.loader.exec_module(mod)

QUOTES = {}
SELL_CALLS = []
SELL_HALF_CALLS = []

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

# [1] _hold_days
print("\n[1] _hold_days (%Y%m%d + %Y-%m-%d)")
check("buy 08-17 today 08-18 -> 1", mod._hold_days({"buy_date": "20260817"}, "20260818") == 1)
check("compat 'YYYY-MM-DD' -> 2", mod._hold_days({"buy_date": "2026-08-16"}, "20260818") == 2)
check("missing -> 999", mod._hold_days({}, "20260818") == 999)

# [2] T+2 conditional: profit -> extend
print("\n[2] T+2 conditional: profit -> extend")
C = _C()
C.position_map = {
    "600519.SH": {
        "shares": 1000, "can_use": 1000, "buy_price": 100.0,
        "buy_date": "20260816", "peak": 105.0, "trail_armed": False,
        "awaiting_new_high": False, "peel_peak_snapshot": 100.0,
        "peel_count": 0, "t2_extended": False, "vwap_broken": False,
        "wy_bc_armed": False, "pending": False, "today_high": 102.0,
    },
}
QUOTES["600519.SH"] = (102.0, 100.0, 101.0, 103.0)
SELL_CALLS.clear(); SELL_HALF_CALLS.clear()
mod._check_sell(C, None, mod.T2_FORCE_HHMM, "20260818")
check("profit NOT sold at T+2", len(SELL_CALLS) == 0 and len(SELL_HALF_CALLS) == 0)
check("t2_extended True", C.position_map["600519.SH"].get("t2_extended") is True)

# [3] T+2 conditional: loss -> force sell
print("\n[3] T+2 conditional: loss -> t2_force")
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
QUOTES["000001.SZ"] = (95.0, 100.0, 95.0, 96.0)
SELL_CALLS.clear(); SELL_HALF_CALLS.clear()
mod._check_sell(C2, None, mod.T2_FORCE_HHMM, "20260818")
check("loss force-sold", len(SELL_CALLS) == 1 and SELL_CALLS[0][0] == "000001.SZ")
check("reason t2_force", "t2_force" in SELL_CALLS[0][1])
check("position popped", "000001.SZ" not in C2.position_map)

# [4] weakness score + rotation pick
print("\n[4] _weakness_score picks weakest / skips momentum guard")
C3 = _C()
C3.position_map = {
    "600001.SH": {
        "shares": 1000, "can_use": 1000, "buy_price": 100.0, "buy_date": "20260816",
        "peak": 103.0, "trail_armed": True, "awaiting_new_high": False,
        "peel_peak_snapshot": 100.0, "peel_count": 0, "t2_extended": False,
        "vwap_broken": False, "wy_bc_armed": False, "pending": False,
    },
    "600002.SH": {
        "shares": 1000, "can_use": 1000, "buy_price": 100.0, "buy_date": "20260816",
        "peak": 100.0, "trail_armed": False, "awaiting_new_high": False,
        "peel_peak_snapshot": 100.0, "peel_count": 0, "t2_extended": False,
        "vwap_broken": False, "wy_bc_armed": False, "pending": False,
    },
}
QUOTES["600001.SH"] = (103.0, 100.0, 102.0, 104.0)
QUOTES["600002.SH"] = (96.0, 100.0, 96.0, 97.0)
cands, sellable = mod._weakness_score(C3, "20260818")
check("2 sellable", len(sellable) == 2)
check("weakest ranked first (600002 -4%)",
      sellable[0]["code"] == "600002.SH" if sellable else False)

print(f"\n===== {passed} passed, {failed} failed =====")
sys.exit(1 if failed else 0)
