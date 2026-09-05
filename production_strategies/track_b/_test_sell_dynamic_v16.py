# -*- coding: utf-8 -*-
"""v1.6 dynamic T+2 force-close floor offline tests (Track B QMT SIM):
a wide-amplitude / high-vol name must NOT be force-sold at the old fixed 0%
floor when its pullback is inside the day's range. 300591 08-19 regression:
filled 8.54 on a 7.88 trigger (buy slip), next day -8.7% vs cost -> the fixed
0% floor sold it; the dynamic floor should hold it to T+3."""
import importlib.util
import sys
from pathlib import Path

STRAT = Path(r"C:\Users\elvisq\Projects\alphapilot\production_strategies\track_b\TrackB_track_b_qmt_auction_sim.py")

spec = importlib.util.spec_from_file_location("trackb_v16", STRAT)
mod = importlib.util.module_from_spec(spec)
sys.modules["trackb_v16"] = mod

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
def _annual_vol(*a): return 0.6
def _get_prev_day_vwap(*a): return None
def _wyckoff_holding_bc(*a): return False
def _closed_5m_bars(*a): return 48
def _get_volume_ratio(*a): return None
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
def _get_last(*a): return None
def _get_turnover(*a): return None
def _is_auction_eligible(*a): return True

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
    ("_bar_times", _bar_times), ("_vol_ma5", _vol_ma5),
    ("_p1_gate", _p1_gate), ("_p2_gate", _p2_gate),
    ("_update_auction_state", _update_auction_state),
    ("_dump_gate", _dump_gate), ("_live_pool_survivors", _live_pool_survivors),
    ("_load_remote_json", _load_remote_json), ("_fetch_remote", _fetch_remote),
    ("_load_fullpool", _load_fullpool), ("_load_fullpool_live", _load_fullpool_live),
    ("_sector_gap", _sector_gap), ("_day_gap", _day_gap), ("_save_json", _save_json),
    ("_snap", _snap), ("_last_price", _last_price), ("_load_json", _load_json),
    ("_find_quote", _find_quote), ("_query_cash", _query_cash),
    ("_get_last", _get_last), ("_get_turnover", _get_turnover),
]:
    setattr(mod, name, fn)
spec.loader.exec_module(mod)

QUOTES = {}
SELL_CALLS = []
SELL_HALF_CALLS = []

# NOTE: exec_module re-binds module-level defs, so the stubs above are only
# fallbacks. Re-assert the mocks we actually rely on AFTER exec_module.

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

def _get_prev_close(*a): return 8.41
mod._get_prev_close = _get_prev_close

# Kimi #11: _annual_vol was only rebound by test [3]'s side effect; exec_module
# re-binds module-level defs, so the pre-exec stub is silently dropped and every
# case that needs the vol term runs the real function (None -> VOL_BASELINE 0.30,
# floor -1.45% instead of the claimed -4.45%). Re-assert explicitly here.
def _annual_vol_06(*a): return 0.6
mod._annual_vol = _annual_vol_06
def _vol_03(*a): return 0.3

# Mock 5m bars: today high=11.0 low=8.5 (amp ~25%), so a -9% loss is inside range
def _m5_bars(*a):
    # (tmin, open, close, high, low, vol)
    return [
        (9*60+35, 10.5, 10.8, 11.0, 10.0, 100),
        (9*60+40, 10.8, 10.0, 11.0, 9.5, 120),
        (9*60+45, 10.0, 9.3, 10.0, 8.8, 150),
        (9*60+50, 9.3, 9.0, 9.3, 8.5, 140),
    ]
mod._get_m5_bars = _m5_bars

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

# [1] _day_amplitude_pct: high 11.0 low 8.5, prev_close 8.41 -> ~29.7%
print("\n[1] _day_amplitude_pct")
amp = mod._day_amplitude_pct(None, "300591.SZ")
check(f"amplitude ~29.7% (got {amp:.1f})", abs(amp - 29.7) < 1.0)

# [2] _t2_force_floor: amp ~29.7%, vol 0.6
#   tol = (29.7-4)*0.5/100 = 0.1285 + (0.6-0.3)*0.10 = 0.03 -> floor -0.1585 -> capped -0.10
print("\n[2] _t2_force_floor")
floor = mod._t2_force_floor(None, "300591.SZ")
check(f"floor capped at -0.10 (got {floor:.3f})", abs(floor + 0.10) < 0.001)
# Kimi #11: verify the vol term is actually live (0.6 stub, NOT the real fn).
# A high-vol name must have a wider (more negative) floor than a low-vol name
# at the same amplitude; without the vol contribution both would be identical.
def _m5_real(*a):
    return [
        (9*60+35, 8.33, 8.30, 8.36, 8.28, 100),
        (10*60+0, 8.25, 8.10, 8.28, 8.05, 120),
        (11*60+0, 8.05, 7.95, 8.05, 7.90, 150),
        (14*60+30, 7.90, 7.82, 7.92, 7.78, 140),
    ]
mod._get_m5_bars = _m5_real
mod._annual_vol = _annual_vol_06          # 0.6
f_hi = mod._t2_force_floor(None, "300591.SZ")
mod._annual_vol = _vol_03                  # 0.3
f_lo = mod._t2_force_floor(None, "300591.SZ")
mod._annual_vol = _annual_vol_06           # restore
check(f"vol term live: hi-vol floor < lo-vol floor ({f_hi*100:.2f}% vs {f_lo*100:.2f}%)",
      f_hi < f_lo)
mod._get_m5_bars = _m5_bars

# [3] low-vol / low-amp name: floor stays near 0 (close to old behavior)
def _m5_flat(*a):
    return [(9*60+35, 8.4, 8.5, 8.5, 8.3, 100)]
mod._get_m5_bars = _m5_flat
def _vol_03(*a): return 0.3
mod._annual_vol = _vol_03
floor2 = mod._t2_force_floor(None, "600519.SH")
check(f"flat name floor ~0 (got {floor2:.3f})", abs(floor2) < 0.005)
mod._annual_vol = _annual_vol_06
mod._get_m5_bars = _m5_bars

# [4] wide-amp loss NOT force-sold: buy 8.54 (blown cost), now 7.80 (-8.7%),
#     but day amplitude 25% -> floor -10% -> -8.7% inside floor -> extend
print("\n[4] wide-amp -8.7% loss held (300591 regression)")
C = _C()
C.position_map = {
    "300591.SZ": {
        "shares": 1000, "can_use": 1000, "buy_price": 8.54,
        "buy_date": "20260818", "peak": 8.55, "trail_armed": False,
        "awaiting_new_high": False, "peel_peak_snapshot": 8.54,
        "peel_count": 0, "t2_extended": False, "vwap_broken": False,
        "wy_bc_armed": False, "pending": False, "today_high": 8.5,
    },
}
QUOTES["300591.SZ"] = (7.80, 8.41, 8.33, 8.33)
SELL_CALLS.clear(); SELL_HALF_CALLS.clear()
mod._check_sell(C, None, mod.T2_FORCE_HHMM, "20260819")
check("NOT force-sold", len(SELL_CALLS) == 0 and len(SELL_HALF_CALLS) == 0)
check("t2_extended True", C.position_map["300591.SZ"].get("t2_extended") is True)

# [5] shallow-amp deep loss still force-sold: flat day, -8.7% -> floor ~0 -> sell
print("\n[5] flat-day -8.7% loss force-sold")
mod._get_m5_bars = _m5_flat
C4 = _C()
C4.position_map = {
    "000002.SZ": {
        "shares": 1000, "can_use": 1000, "buy_price": 8.54,
        "buy_date": "20260818", "peak": 8.55, "trail_armed": False,
        "awaiting_new_high": False, "peel_peak_snapshot": 8.54,
        "peel_count": 0, "t2_extended": False, "vwap_broken": False,
        "wy_bc_armed": False, "pending": False, "today_high": 8.5,
    },
}
QUOTES["000002.SZ"] = (7.80, 8.41, 8.33, 8.33)
SELL_CALLS.clear(); SELL_HALF_CALLS.clear()
mod._check_sell(C4, None, mod.T2_FORCE_HHMM, "20260819")
check("flat-day loss force-sold", len(SELL_CALLS) == 1 and "t2_force" in SELL_CALLS[0][1])
mod._get_m5_bars = _m5_bars

# [6] REAL 300591 08-19 (amplitude 6.9%, high 8.36 / low 7.78 / prev 8.41):
#     fair cost 7.88 (P2 trigger, slip guard blocks the 8.54 blow-up) ->
#     next day 7.80 = -1.0% vs cost, floor -4.45% -> held to T+3.
print("\n[6] real 08-19 amp 6.9% fair-cost -1.0% held (slip guard case)")
def _m5_real(*a):
    return [
        (9*60+35, 8.33, 8.30, 8.36, 8.28, 100),
        (10*60+0, 8.25, 8.10, 8.28, 8.05, 120),
        (11*60+0, 8.05, 7.95, 8.05, 7.90, 150),
        (14*60+30, 7.90, 7.82, 7.92, 7.78, 140),
    ]
mod._get_m5_bars = _m5_real
C6 = _C()
C6.position_map = {
    "300591.SZ": {
        "shares": 1000, "can_use": 1000, "buy_price": 7.88,
        "buy_date": "20260818", "peak": 8.1, "trail_armed": False,
        "awaiting_new_high": False, "peel_peak_snapshot": 7.88,
        "peel_count": 0, "t2_extended": False, "vwap_broken": False,
        "wy_bc_armed": False, "pending": False, "today_high": 8.36,
    },
}
QUOTES["300591.SZ"] = (7.80, 8.41, 8.33, 8.33)
SELL_CALLS.clear(); SELL_HALF_CALLS.clear()
mod._check_sell(C6, None, mod.T2_FORCE_HHMM, "20260819")
check("real amp6.9% -1.0% NOT force-sold", len(SELL_CALLS) == 0 and len(SELL_HALF_CALLS) == 0)
check("real amp6.9% -1.0% t2_extended True", C6.position_map["300591.SZ"].get("t2_extended") is True)

# [7] REAL 300591 08-19 same day, but blown cost 8.54 -> -8.7% vs cost:
#     still below the -4.45% floor -> force-sold. This is the case the BUY
#     slip guard must prevent upstream; the dynamic floor alone cannot save
#     a blown-cost position on a moderate-amplitude day.
print("\n[7] real 08-19 amp 6.9% blown-cost -8.7% still force-sold")
C7 = _C()
C7.position_map = {
    "300591.SZ": {
        "shares": 1000, "can_use": 1000, "buy_price": 8.54,
        "buy_date": "20260818", "peak": 8.55, "trail_armed": False,
        "awaiting_new_high": False, "peel_peak_snapshot": 8.54,
        "peel_count": 0, "t2_extended": False, "vwap_broken": False,
        "wy_bc_armed": False, "pending": False, "today_high": 8.36,
    },
}
QUOTES["300591.SZ"] = (7.80, 8.41, 8.33, 8.33)
SELL_CALLS.clear(); SELL_HALF_CALLS.clear()
mod._check_sell(C7, None, mod.T2_FORCE_HHMM, "20260819")
check("blown-cost -8.7% force-sold", len(SELL_CALLS) == 1 and "t2_force" in SELL_CALLS[0][1])
mod._get_m5_bars = _m5_bars

# [8] Kimi #3: vwap_broken set in the SAME 14:45 pass must NOT short-circuit the
#     dynamic floor. price 7.80 < vwap 8.05 -> vwap_broken=True, ret=-1.0% still
#     inside the -4.45% floor -> extend, not t2_force_after_extend.
print("\n[8] vwap_broken same-pass does not short-circuit dynamic floor")
def _day_vwap_805(*a): return 8.05
mod._day_vwap = _day_vwap_805
C8 = _C()
C8.position_map = {
    "300591.SZ": {
        "shares": 1000, "can_use": 1000, "buy_price": 7.88,
        "buy_date": "20260818", "peak": 8.1, "trail_armed": False,
        "awaiting_new_high": False, "peel_peak_snapshot": 7.88,
        "peel_count": 0, "t2_extended": False, "vwap_broken": False,
        "wy_bc_armed": False, "pending": False, "today_high": 8.36,
    },
}
QUOTES["300591.SZ"] = (7.80, 8.41, 8.33, 8.33)
SELL_CALLS.clear(); SELL_HALF_CALLS.clear()
mod._check_sell(C8, None, mod.T2_FORCE_HHMM, "20260819")
check("vwap_broken armed (px<vw)", C8.position_map["300591.SZ"].get("vwap_broken") is True)
check("vwap_broken NOT force-sold (floor holds)", len(SELL_CALLS) == 0 and len(SELL_HALF_CALLS) == 0)
check("vwap_broken t2_extended True", C8.position_map["300591.SZ"].get("t2_extended") is True)
mod._day_vwap = _day_vwap

# [9] vwap_broken is a NEXT-MORNING exit signal (09:35-09:50), so it must fire
#     there -- previously the T+2 14:45 branch killed the position before the
#     window was ever reached (dead code). Hold a broken position into 09:40.
print("\n[9] vwap_broken next-morning vwap_weak_early fires (not dead code)")
def _day_vwap_805b(*a): return 8.05
mod._day_vwap = _day_vwap_805b
C9 = _C()
C9.position_map = {
    "300591.SZ": {
        "shares": 1000, "can_use": 1000, "buy_price": 7.88,
        "buy_date": "20260818", "peak": 7.95, "trail_armed": False,
        "awaiting_new_high": False, "peel_peak_snapshot": 7.88,
        "peel_count": 0, "t2_extended": True, "vwap_broken": True,
        "wy_bc_armed": False, "pending": False, "today_high": 8.0,
    },
}
QUOTES["300591.SZ"] = (7.80, 8.41, 8.33, 8.33)
SELL_CALLS.clear(); SELL_HALF_CALLS.clear()
mod._check_sell(C9, None, 9 * 60 + 40, "20260820")
check("next-morning vwap_weak_early sell", len(SELL_CALLS) == 1 and "vwap_weak_early" in SELL_CALLS[0][1])
mod._day_vwap = _day_vwap

# [10] v2.5 next-morning confirm: price recovered above vwap_ref -> cancel
print("\n[10] v2.5 price >= vwap_ref next-morning -> cancel weak-early")
C10 = _C()
C10.position_map = {
    "300591.SZ": {
        "shares": 1000, "can_use": 1000, "buy_price": 7.88,
        "buy_date": "20260818", "peak": 7.95, "trail_armed": False,
        "awaiting_new_high": False, "peel_peak_snapshot": 7.88,
        "peel_count": 0, "t2_extended": True, "vwap_broken": True,
        "vwap_ref": 8.05, "wy_bc_armed": False, "pending": False,
        "today_high": 8.0,
    },
}
QUOTES["300591.SZ"] = (8.20, 8.41, 8.33, 8.33)   # price 8.20 >= vwap_ref 8.05
SELL_CALLS.clear(); SELL_HALF_CALLS.clear()
mod._check_sell(C10, None, 9 * 60 + 40, "20260820")
check("recovered -> NO sell", len(SELL_CALLS) == 0 and len(SELL_HALF_CALLS) == 0)
check("recovered -> signal cleared", C10.position_map["300591.SZ"].get("vwap_broken") is False)
check("recovered -> vwap_ref cleared", C10.position_map["300591.SZ"].get("vwap_ref") == 0)

# [11] v2.5 next-morning confirm: price still below vwap_ref -> fire
print("\n[11] v2.5 price < vwap_ref next-morning -> vwap_weak_early fires")
C11 = _C()
C11.position_map = {
    "300591.SZ": {
        "shares": 1000, "can_use": 1000, "buy_price": 7.88,
        "buy_date": "20260818", "peak": 7.95, "trail_armed": False,
        "awaiting_new_high": False, "peel_peak_snapshot": 7.88,
        "peel_count": 0, "t2_extended": True, "vwap_broken": True,
        "vwap_ref": 8.05, "wy_bc_armed": False, "pending": False,
        "today_high": 8.0,
    },
}
QUOTES["300591.SZ"] = (7.80, 8.41, 8.33, 8.33)   # price 7.80 < vwap_ref 8.05
SELL_CALLS.clear(); SELL_HALF_CALLS.clear()
mod._check_sell(C11, None, 9 * 60 + 40, "20260820")
check("still weak -> vwap_weak_early sell", len(SELL_CALLS) == 1 and "vwap_weak_early" in SELL_CALLS[0][1])

print(f"\n===== {passed} passed, {failed} failed =====")
sys.exit(1 if failed else 0)
