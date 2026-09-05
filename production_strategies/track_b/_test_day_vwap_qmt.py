# -*- coding: utf-8 -*-
"""v1.6 day-VWAP source test (Track B QMT SIM):
Primary path must be QMT's own real-time tick (get_full_tick amount/pvolume =
authoritative intraday avg price, no hand/share conversion), with a plausibility
guard (0.5x..2x of lastPrice) that rejects a residual 100x unit mismatch and
falls back to 5m bars. Regression: 300591 08-19 vwap=806.98 for a ~8.07 tape
was a unit bug in the calc path, NOT a QMT data fetch error."""
import importlib.util
import sys
from datetime import datetime
from pathlib import Path

STRAT = Path(r"C:\Users\elvisq\Projects\alphapilot\production_strategies\track_b\TrackB_track_b_qmt_auction_sim.py")

spec = importlib.util.spec_from_file_location("trackb_vwap", STRAT)
mod = importlib.util.module_from_spec(spec)
sys.modules["trackb_vwap"] = mod

# stub the many module-level deps so exec_module succeeds
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
def _get_prev_close(*a): return 8.41
def _adaptive_params(*a): return (-0.10, 0.03, 0.015)
def _is_trading_time(*a): return True
def passorder(*a): return 0
def get_trade_detail_data(*a): return []
def _annual_vol(*a): return 0.6
def _get_prev_day_vwap(*a): return None
def _wyckoff_holding_bc(*a): return False
def _closed_5m_bars(*a): return 48
def _get_volume_ratio(*a): return None
def _get_turnover(*a): return None
def _get_quote(*a): return (8.0, 8.41, 8.3, 8.5)
def _get_last(*a): return 8.1
def _get_m5_bars(*a): return [(9*60+35, 8.0, 8.1, 8.2, 7.9, 100)]
def _day_amplitude_pct(*a): return 6.9
def _t2_force_floor(*a): return -0.0445
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
def _last_price(*a): return 8.1
def _load_json(*a): return None
def _find_quote(*a): return None
def _query_cash(*a): return (1000000.0, 2000000.0)
def _do_sell(*a): pass
def _do_sell_half(*a): pass

for name, fn in [
    ("_qmt_code", _qmt_code), ("_is_limit_up", _is_limit_up),
    ("_wyckoff_distribution", _wyckoff_distribution), ("_board_allowed", _board_allowed),
    ("_order_locked", _order_locked), ("_mark_order_locked", _mark_order_locked),
    ("_load_order_locks", _load_order_locks), ("_load_candidates", _load_candidates),
    ("_load_scores", _load_scores), ("_sync_holdings", _sync_holdings),
    ("_snap_daily", _snap_daily), ("_get_prev_close", _get_prev_close),
    ("_adaptive_params", _adaptive_params), ("_is_trading_time", _is_trading_time),
    ("passorder", passorder), ("get_trade_detail_data", get_trade_detail_data),
    ("_annual_vol", _annual_vol), ("_get_prev_day_vwap", _get_prev_day_vwap),
    ("_wyckoff_holding_bc", _wyckoff_holding_bc), ("_closed_5m_bars", _closed_5m_bars),
    ("_get_volume_ratio", _get_volume_ratio), ("_get_turnover", _get_turnover),
    ("_get_quote", _get_quote), ("_get_last", _get_last), ("_get_m5_bars", _get_m5_bars),
    ("_day_amplitude_pct", _day_amplitude_pct), ("_t2_force_floor", _t2_force_floor),
    ("_p1_gate", _p1_gate), ("_p2_gate", _p2_gate),
    ("_update_auction_state", _update_auction_state), ("_dump_gate", _dump_gate),
    ("_live_pool_survivors", _live_pool_survivors), ("_load_remote_json", _load_remote_json),
    ("_fetch_remote", _fetch_remote), ("_load_fullpool", _load_fullpool),
    ("_load_fullpool_live", _load_fullpool_live), ("_sector_gap", _sector_gap),
    ("_day_gap", _day_gap), ("_save_json", _save_json), ("_snap", _snap),
    ("_last_price", _last_price), ("_load_json", _load_json), ("_find_quote", _find_quote),
    ("_query_cash", _query_cash), ("_do_sell", _do_sell), ("_do_sell_half", _do_sell_half),
]:
    setattr(mod, name, fn)
spec.loader.exec_module(mod)

# re-assert the ones the day-vwap test actually relies on, AFTER exec_module
# (exec_module re-binds module-level defs, so pre-set stubs are overwritten).

def _bar_times(df, n):
    """Fake QMT 5m index: all bars are today so the date filter keeps them."""
    today = datetime.now().strftime("%Y-%m-%d")
    return [(today, 575), (today, 580)]
mod._bar_times = _bar_times

def _col(df, name):
    """dict-of-lists fake of QMT DataFrame column extraction."""
    return [float(x) for x in df.get(name, [])]
mod._col = _col

class _C:
    def __init__(self, tick=None, m5=None, no_tick=False):
        self._tick = tick
        self._m5 = m5 if m5 is not None else {}
        self._no_tick = no_tick
    def get_full_tick(self, codes):
        if self._no_tick:
            raise AttributeError("no get_full_tick in this QMT build")
        return {codes[0]: self._tick} if self._tick else {}
    def get_market_data_ex(self, fields, codes, **kw):
        return {codes[0]: self._m5}

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

# [1] correct QMT tick: amount/pvolume = authoritative day VWAP, inside the
#     plausibility band -> used directly (no hand/share conversion).
print("\n[1] get_full_tick primary path (amount/pvolume)")
C1 = _C(tick={"amount": 8130000.0, "pvolume": 1000000, "lastPrice": 8.13})
v = mod._day_vwap(C1, "300591.SZ")
check(f"VWAP from tick = 8.13 (got {v})", v is not None and abs(v - 8.13) < 1e-6)

M5_OK = {"close": [8.0, 8.1], "volume": [1000, 2000], "amount": [813000.0, 1626000.0]}
# sum amount 2439000 / (sum volume 3000 hands x100 = 300000 shares) = 8.13

# [2] 100x unit mismatch in tick: amount/pvolume = 813 vs lastPrice 8.13 ->
#     rejected by the 0.5x..2x guard -> falls back to 5m bars.
print("\n[2] implausible tick rejected -> 5m fallback")
C2 = _C(tick={"amount": 813000000.0, "pvolume": 1000000, "lastPrice": 8.13}, m5=M5_OK)
v = mod._day_vwap(C2, "300591.SZ")
check(f"5m fallback VWAP = 8.13 (got {v})", v is not None and abs(v - 8.13) < 1e-6)

# [3] QMT build without get_full_tick -> 5m fallback still correct.
print("\n[3] no get_full_tick -> 5m fallback")
C3 = _C(no_tick=True, m5=M5_OK)
v = mod._day_vwap(C3, "300591.SZ")
check(f"5m fallback VWAP = 8.13 (got {v})", v is not None and abs(v - 8.13) < 1e-6)

# [4] tick present but amount 0 -> 5m fallback.
print("\n[4] empty tick -> 5m fallback")
C4 = _C(tick={"amount": 0.0, "pvolume": 1000000, "lastPrice": 8.13}, m5=M5_OK)
v = mod._day_vwap(C4, "300591.SZ")
check(f"5m fallback VWAP = 8.13 (got {v})", v is not None and abs(v - 8.13) < 1e-6)

print(f"\n===== {passed} passed, {failed} failed =====")
sys.exit(1 if failed else 0)
