# -*- coding: utf-8 -*-
"""Cross-file offline test: _hold_days / _hold_days_short must count TRADING
days, not calendar days (fix 2026-08-31, all 8 strategies aligned).

Regression this guards against: a Friday buy was counted as hold=3 on Monday
(calendar (t-b).days), which prematurely triggered t2_force_after_extend
(002466 天齐锂业) and rotation_sell (002058 紫竹高科). Friday buy must be
T+1 on Monday, T+2 on Tuesday.

Each file is read via AST and only the pure helper functions are exec'd, so no
trading-platform builtins are needed. The file is validated as loaded, i.e. any
future drift of these helpers is caught immediately."""
import ast
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(r"C:\Users\elvisq\Projects\alphapilot\production_strategies")

FILES = [
    ("QMT live A", ROOT / "track_a" / "TrackA_track_a_qmt_full_chain_live.py", "v2.30-tpl"),
    ("QMT sim A",  ROOT / "track_a" / "TrackA_track_a_qmt_full_chain_sim.py", "v2.30"),
    ("TDX sim A",  ROOT / "track_a" / "TrackA_track_a_tdx_full_chain_sim.py", "v2.29"),
    ("QMT sim B",  ROOT / "track_b" / "TrackB_track_b_qmt_auction_sim.py", "v2.7"),
    ("QMT live B", ROOT / "track_b" / "TrackB_track_b_qmt_auction_live.py", "v2.7-tpl"),
    ("TDX sim B",  ROOT / "track_b" / "TrackB_track_b_tdx_auction_sim.py", "v1.18"),
    ("ptrade sim A", ROOT / "ptrade" / "TrackA_track_a_ptrade_sim.py", "v1.7"),
    ("ptrade live A", ROOT / "ptrade" / "TrackA_track_a_ptrade_live.py", "v1.7-tpl"),
]

CASES = [
    # buy_date, today, expect, label
    ("20260828", "20260831", 1, "Fri buy -> Mon = T+1 (user's 002466/002058 case)"),
    ("20260828", "20260901", 2, "Fri buy -> Tue = T+2"),
    ("20260831", "20260831", 0, "same-day buy = T0"),
    ("20260831", "20260907", 5, "Mon buy -> next Mon = 5 trading days"),
    ("20260930", "20261009", 2, "Wed before Golden Week -> Fri after = 2 (holidays excluded)"),
    ("20261008", "20261012", 2, "Thu after Golden Week -> next Mon = 2 (Fri+Mon)"),
]


def _load_helpers(raw):
    """Exec-only the pure hold-day helpers + closed-dates constant."""
    tree = ast.parse(raw)
    ns = {"datetime": datetime, "timedelta": timedelta}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tg in node.targets:
                if isinstance(tg, ast.Name) and tg.id == "_ASHARE_CLOSED_2026":
                    exec(ast.get_source_segment(raw, node), ns)
        elif isinstance(node, ast.FunctionDef) and node.name in (
            "_is_trading_day", "_trading_days_between", "_hold_days", "_hold_days_short",
        ):
            exec(ast.get_source_segment(raw, node), ns)
    return ns


def D(s):
    return datetime.strptime(s, "%Y%m%d").date()


passed = failed = 0


def check(name, cond):
    global passed, failed
    if cond:
        passed += 1
        print("  PASS " + name)
    else:
        failed += 1
        print("  FAIL " + name)


for label, path, expect_ver in FILES:
    raw = path.read_text(encoding="utf-8", errors="replace")
    ns = _load_helpers(raw)

    has_hd = "_hold_days" in ns
    has_hds = "_hold_days_short" in ns
    has_helper = "_trading_days_between" in ns and "_is_trading_day" in ns
    check(f"{label}: helpers present", has_hd and has_helper)

    if not has_hd:
        continue

    for b, t, exp, cname in CASES:
        got = ns["_hold_days"]({"buy_date": b}, t)
        check(f"{label}: {cname} ({b}->{t} = {got}, exp {exp})", got == exp)

    # short variant, where present
    if has_hds:
        got = ns["_hold_days_short"]({"buy_date": "20260828"}, "20260831")
        check(f"{label}: _hold_days_short Fri->Mon = T+1 (got {got})", got == 1)

    # missing / bad buy_date still 999
    check(f"{label}: missing buy_date -> 999", ns["_hold_days"]({}, "20260831") == 999)
    check(f"{label}: bad buy_date -> 999", ns["_hold_days"]({"buy_date": "xx"}, "20260831") == 999)

    # trading-day boundary checks through _is_trading_day
    check(f"{label}: 08-29 (Sat) not trading", ns["_is_trading_day"](D("20260829")) is False)
    check(f"{label}: 10-01 (holiday) not trading", ns["_is_trading_day"](D("20261001")) is False)
    check(f"{label}: 10-09 (Fri) trading", ns["_is_trading_day"](D("20261009")) is True)

print("\n===== %d passed, %d failed =====" % (passed, failed))
sys.exit(1 if failed else 0)
