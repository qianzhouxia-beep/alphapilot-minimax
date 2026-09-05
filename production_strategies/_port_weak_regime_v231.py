#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v2.31/v2.8/v1.19/v2.30/v1.8 弱市破位敏感退出 —— 8 端移植脚本（2026-09-03）。

参考实现：track_a/TrackA_track_a_qmt_full_chain_live.py v2.31-tpl（已手工完成）。
每处替换断言「恰好命中一次」，任一失败则该文件不写回。
全部新增内容纯 ASCII。跑完后自动做 ASCII(QMT/ptrade) + AST 校验。
"""
from __future__ import annotations

import ast
import pathlib

ROOT = pathlib.Path(r"C:\Users\elvisq\Projects\alphapilot\production_strategies")

HDR_NOTE = (
    "# {ver} (2026-09-03): weak-regime breakdown-sensitive exits (aligned with\n"
    "# Track A QMT v2.31). User directive: NO hard time exits for trend-intact\n"
    "# positions -- regime only changes how SENSITIVE breakdown exits are.\n"
    "# weak_regime flag from server-stamped market_env in the daily score json\n"
    "# (state5_q of yesterday's all-A 5d main-flow quintile; weak = q==1).\n"
    "# Weak regime: t2_force floor x0.6, peel pullback x0.7, T+2 extension only\n"
    "# for trend-intact (price >= day VWAP), T+3 hold-cap becomes a breakdown\n"
    "# check (intact keeps running, daily recheck). Non-weak: unchanged.\n"
)

# ---------------- QMT C-flavor blocks (A_sim / B_live / B_sim / B_sim26) ----------------

C_CONST_ANCHOR = "T2_FORCE_HHMM = 14 * 60 + 45\n"
C_CONST_NEW = (
    "T2_FORCE_HHMM = 14 * 60 + 45\n"
    "\n"
    "# --- weak-regime breakdown-sensitive exits (2026-09-03) ---\n"
    "WEAK_REGIME_ENABLE = True\n"
    "WEAK_FLOOR_MULT = 0.6     # t2_force dynamic floor x0.6 in weak regime\n"
    "WEAK_PB_MULT = 0.7        # peel pullback x0.7 in weak regime\n"
)

C_FLOOR_END = (
    "    floor = -tol\n"
    "    if floor < T2_FORCE_FLOOR_MAX:\n"
    "        floor = T2_FORCE_FLOOR_MAX\n"
    "    return floor\n"
)

C_HELPER_CAND = (
    "\n\n# ============ weak-regime helpers (2026-09-03) ============\n"
    "def _weak_regime(C, today):\n"
    "    \"\"\"Weak-market regime flag from today's candidates.json market_env\n"
    "    (server stamps yesterday's all-A 5d main-flow quintile state5_q;\n"
    "    weak = q==1 deep outflow). Cached per day on C. Missing/unreadable\n"
    "    -> False (legacy behavior).\"\"\"\n"
    "    cache = getattr(C, \"_weak_regime_cache\", None)\n"
    "    if cache is None:\n"
    "        cache = {}\n"
    "        C._weak_regime_cache = cache\n"
    "    if today in cache:\n"
    "        return cache[today]\n"
    "    weak = False\n"
    "    if WEAK_REGIME_ENABLE:\n"
    "        try:\n"
    "            fpath = os.path.join(C.score_dir, today + \".candidates.json\")\n"
    "            if not os.path.exists(fpath):\n"
    "                _fetch_remote_scores(C, today)\n"
    "            if os.path.exists(fpath):\n"
    "                with open(fpath, \"r\", encoding=\"utf-8\") as f:\n"
    "                    env = json.load(f).get(\"market_env\") or {}\n"
    "                weak = bool(env.get(\"weak_regime\"))\n"
    "        except Exception:\n"
    "            weak = False\n"
    "    cache[today] = weak\n"
    "    if weak:\n"
    "        print(\"[REGIME] weak day: floor x\" + str(WEAK_FLOOR_MULT) +\n"
    "              \" peel x\" + str(WEAK_PB_MULT) +\n"
    "              \" extend/cap need trend-intact\")\n"
    "    return weak\n"
    "\n\n"
    "def _weak_cap_sell_ok(C, code, price, ret):\n"
    "    \"\"\"Weak regime: the T+3 hold-cap fires only on breakdown\n"
    "    (ret <= 0 or price below day VWAP). Trend-intact positions keep\n"
    "    running and are rechecked each day -- no calendar deadline.\"\"\"\n"
    "    if ret <= 0:\n"
    "        return True\n"
    "    vw = _day_vwap(C, code)\n"
    "    if vw and vw > 0:\n"
    "        return price < vw\n"
    "    return True  # vwap unknown -> keep legacy behavior (sell at cap)\n"
)

C_HELPER_FULLPOOL = (
    "\n\n# ============ weak-regime helpers (2026-09-03) ============\n"
    "def _weak_regime(C, today):\n"
    "    \"\"\"Weak-market regime flag from today's fullpool json market_env\n"
    "    (server stamps yesterday's all-A 5d main-flow quintile state5_q;\n"
    "    weak = q==1 deep outflow). Cached per day on C. Missing/unreadable\n"
    "    -> False (legacy behavior).\"\"\"\n"
    "    cache = getattr(C, \"_weak_regime_cache\", None)\n"
    "    if cache is None:\n"
    "        cache = {}\n"
    "        C._weak_regime_cache = cache\n"
    "    if today in cache:\n"
    "        return cache[today]\n"
    "    weak = False\n"
    "    if WEAK_REGIME_ENABLE:\n"
    "        try:\n"
    "            for suffix, fn in ((\".fullpool_live.json\", _fetch_remote_fullpool_live),\n"
    "                               (\".fullpool.json\", _fetch_remote_fullpool)):\n"
    "                fpath = os.path.join(C.score_dir, today + suffix)\n"
    "                if not os.path.exists(fpath):\n"
    "                    fn(C, today)\n"
    "                if os.path.exists(fpath):\n"
    "                    with open(fpath, \"r\", encoding=\"utf-8\") as f:\n"
    "                        env = json.load(f).get(\"market_env\") or {}\n"
    "                    weak = bool(env.get(\"weak_regime\"))\n"
    "                    break\n"
    "        except Exception:\n"
    "            weak = False\n"
    "    cache[today] = weak\n"
    "    if weak:\n"
    "        print(\"[REGIME] weak day: floor x\" + str(WEAK_FLOOR_MULT) +\n"
    "              \" peel x\" + str(WEAK_PB_MULT) +\n"
    "              \" extend/cap need trend-intact\")\n"
    "    return weak\n"
    "\n\n"
    "def _weak_cap_sell_ok(C, code, price, ret):\n"
    "    \"\"\"Weak regime: the T+3 hold-cap fires only on breakdown\n"
    "    (ret <= 0 or price below day VWAP). Trend-intact positions keep\n"
    "    running and are rechecked each day -- no calendar deadline.\"\"\"\n"
    "    if ret <= 0:\n"
    "        return True\n"
    "    vw = _day_vwap(C, code)\n"
    "    if vw and vw > 0:\n"
    "        return price < vw\n"
    "    return True  # vwap unknown -> keep legacy behavior (sell at cap)\n"
)

C_ADAPT_OLD = (
    "        hs, ta, pb = _adaptive_params(C, code)\n"
    "\n"
    "        # hard stop: close-confirm window only (>=14:45)\n"
)
C_ADAPT_NEW = (
    "        hs, ta, pb = _adaptive_params(C, code)\n"
    "        # weak regime tightens the breakdown exits (price conditions\n"
    "        # only -- no calendar deadline added anywhere).\n"
    "        weak = _weak_regime(C, today)\n"
    "        if weak:\n"
    "            pb = round(pb * WEAK_PB_MULT, 4)\n"
    "\n"
    "        # hard stop: close-confirm window only (>=14:45)\n"
)

C_EXTCAP_OLD = (
    "                if hold_days != 999 and hold_days >= T2_EXTEND_MAX_DAYS:\n"
    "                    _do_sell(C, code, pos, price,\n"
    "                             \"t2_force_after_extend \" + str(round(ret, 1)) + \"%\")\n"
    "                    continue\n"
)
C_EXTCAP_NEW = (
    "                # weak regime turns the cap into a breakdown check --\n"
    "                # trend-intact positions keep running (daily recheck).\n"
    "                if (hold_days != 999 and hold_days >= T2_EXTEND_MAX_DAYS\n"
    "                        and (not weak or _weak_cap_sell_ok(C, code, price, ret))):\n"
    "                    _do_sell(C, code, pos, price,\n"
    "                             \"t2_force_after_extend \" + str(round(ret, 1)) + \"%\")\n"
    "                    continue\n"
)

C_FLOOR_OLD = (
    "                force_floor = _t2_force_floor(C, code) * 100\n"
    "                if ret < force_floor:\n"
)
C_FLOOR_NEW = (
    "                force_floor = _t2_force_floor(C, code) * 100\n"
    "                if weak:\n"
    "                    # weak regime raises the floor (less negative) so\n"
    "                    # losers are cut faster; still a price condition.\n"
    "                    force_floor = round(force_floor * WEAK_FLOOR_MULT, 2)\n"
    "                if ret < force_floor:\n"
)

C_CAPEXT_OLD = (
    "                if ((hold_days != 999 and hold_days >= T2_EXTEND_MAX_DAYS)\n"
    "                        or ret <= hs * 100):\n"
    "                    _do_sell(C, code, pos, price,\n"
    "                             \"t2_force_after_extend \" + str(round(ret, 1)) + \"%\")\n"
    "                    continue\n"
    "                pos[\"t2_extended\"] = True\n"
    "                print(\"[EXT] \" + code + \" extend px=\" + str(round(price, 2)) +\n"
    "                      \" cost=\" + str(round(cost, 2)) +\n"
    "                      \" ret=\" + str(round(ret, 1)) + \"% hold_days=\" + str(hold_days))\n"
)
C_CAPEXT_NEW = (
    "                # weak regime makes the hold-cap breakdown-conditional.\n"
    "                cap_hit = (hold_days != 999 and hold_days >= T2_EXTEND_MAX_DAYS)\n"
    "                if weak and cap_hit and not _weak_cap_sell_ok(C, code, price, ret):\n"
    "                    cap_hit = False\n"
    "                    if pos.get(\"weak_cap_hold_log\") != today:\n"
    "                        pos[\"weak_cap_hold_log\"] = today\n"
    "                        print(\"[HOLD] weak-regime \" + code + \" intact past cap\" +\n"
    "                              \" ret=\" + str(round(ret, 1)) + \"%, keep running\")\n"
    "                if cap_hit or ret <= hs * 100:\n"
    "                    _do_sell(C, code, pos, price,\n"
    "                             \"t2_force_after_extend \" + str(round(ret, 1)) + \"%\")\n"
    "                    continue\n"
    "                # weak regime grants the extra day only to trend-intact\n"
    "                # names (price >= day VWAP). A broken name is NOT force-sold\n"
    "                # here -- vwap_weak_early (armed above) fires next morning.\n"
    "                if weak:\n"
    "                    vw = _day_vwap(C, code)\n"
    "                    if vw and vw > 0 and price < vw:\n"
    "                        if pos.get(\"weak_no_extend\") != today:\n"
    "                            pos[\"weak_no_extend\"] = today\n"
    "                            print(\"[EXT] weak-regime \" + code + \" below vwap=\" +\n"
    "                                  str(round(vw, 2)) + \", no extend\")\n"
    "                    else:\n"
    "                        pos[\"t2_extended\"] = True\n"
    "                        print(\"[EXT] \" + code + \" extend px=\" + str(round(price, 2)) +\n"
    "                              \" cost=\" + str(round(cost, 2)) +\n"
    "                              \" ret=\" + str(round(ret, 1)) + \"% hold_days=\" + str(hold_days))\n"
    "                else:\n"
    "                    pos[\"t2_extended\"] = True\n"
    "                    print(\"[EXT] \" + code + \" extend px=\" + str(round(price, 2)) +\n"
    "                          \" cost=\" + str(round(cost, 2)) +\n"
    "                          \" ret=\" + str(round(ret, 1)) + \"% hold_days=\" + str(hold_days))\n"
)

# ---------------- TDX flavor (A_tdx / B_tdx): no C, log(), T2_FORCE_MIN ----------------

T_CONST_ANCHOR = "T2_FORCE_MIN = 14 * 60 + 45\n"
T_CONST_NEW = (
    "T2_FORCE_MIN = 14 * 60 + 45\n"
    "\n"
    "# --- weak-regime breakdown-sensitive exits (2026-09-03) ---\n"
    "WEAK_REGIME_ENABLE = True\n"
    "WEAK_FLOOR_MULT = 0.6     # t2_force dynamic floor x0.6 in weak regime\n"
    "WEAK_PB_MULT = 0.7        # peel pullback x0.7 in weak regime\n"
    "_WEAK_REGIME_CACHE = {}\n"
)

T_FLOOR_END = C_FLOOR_END  # same shape (module-level fn, same body)

def t_helper(score_file: str, fetch_fn: str) -> str:
    return (
        "\n\n# ============ weak-regime helpers (2026-09-03) ============\n"
        "def _weak_regime(today):\n"
        "    \"\"\"Weak-market regime flag from today's " + score_file + " market_env\n"
        "    (server stamps yesterday's all-A 5d main-flow quintile state5_q;\n"
        "    weak = q==1). Cached per day. Missing/unreadable -> False.\"\"\"\n"
        "    if today in _WEAK_REGIME_CACHE:\n"
        "        return _WEAK_REGIME_CACHE[today]\n"
        "    weak = False\n"
        "    if WEAK_REGIME_ENABLE:\n"
        "        try:\n"
        "            fpath = os.path.join(SCORE_DIR, today + \"." + score_file + "\")\n"
        "            if not os.path.exists(fpath):\n"
        "                " + fetch_fn + "(today)\n"
        "            if os.path.exists(fpath):\n"
        "                with open(fpath, \"r\", encoding=\"utf-8\") as f:\n"
        "                    env = json.load(f).get(\"market_env\") or {}\n"
        "                weak = bool(env.get(\"weak_regime\"))\n"
        "        except Exception:\n"
        "            weak = False\n"
        "    _WEAK_REGIME_CACHE[today] = weak\n"
        "    if weak:\n"
        "        log(\"[REGIME] weak day: floor x\" + str(WEAK_FLOOR_MULT) +\n"
        "            \" peel x\" + str(WEAK_PB_MULT) +\n"
        "            \" extend/cap need trend-intact\")\n"
        "    return weak\n"
        "\n\n"
        "def _weak_cap_sell_ok(code, price, ret):\n"
        "    \"\"\"Weak regime: the T+3 hold-cap fires only on breakdown\n"
        "    (ret <= 0 or price below day VWAP). Trend-intact keeps running.\"\"\"\n"
        "    if ret <= 0:\n"
        "        return True\n"
        "    vw = _day_vwap(code)\n"
        "    if vw and vw > 0:\n"
        "        return price < vw\n"
        "    return True  # vwap unknown -> keep legacy behavior (sell at cap)\n"
    )

T_ADAPT_OLD = (
    "        hs, ta, pb = _adaptive_params(code)\n"
    "\n"
    "        # hard stop: close-confirm window only (>=14:45)\n"
)
T_ADAPT_NEW = (
    "        hs, ta, pb = _adaptive_params(code)\n"
    "        # weak regime tightens the breakdown exits (price conditions only).\n"
    "        weak = _weak_regime(today)\n"
    "        if weak:\n"
    "            pb = round(pb * WEAK_PB_MULT, 4)\n"
    "\n"
    "        # hard stop: close-confirm window only (>=14:45)\n"
)

T_EXTCAP_OLD = (
    "                if hold_days != 999 and hold_days >= T2_EXTEND_MAX_DAYS:\n"
    "                    _do_sell(code, pos, price,\n"
    "                             \"t2_force_after_extend \" + str(round(ret, 1)) + \"%\")\n"
    "                    continue\n"
)
T_EXTCAP_NEW = (
    "                # weak regime turns the cap into a breakdown check.\n"
    "                if (hold_days != 999 and hold_days >= T2_EXTEND_MAX_DAYS\n"
    "                        and (not weak or _weak_cap_sell_ok(code, price, ret))):\n"
    "                    _do_sell(code, pos, price,\n"
    "                             \"t2_force_after_extend \" + str(round(ret, 1)) + \"%\")\n"
    "                    continue\n"
)

T_FLOOR_OLD = (
    "                force_floor = _t2_force_floor(code) * 100\n"
    "                if ret < force_floor:\n"
)
T_FLOOR_NEW = (
    "                force_floor = _t2_force_floor(code) * 100\n"
    "                if weak:\n"
    "                    # weak regime raises the floor (less negative).\n"
    "                    force_floor = round(force_floor * WEAK_FLOOR_MULT, 2)\n"
    "                if ret < force_floor:\n"
)

T_CAPEXT_OLD = (
    "                if ((hold_days != 999 and hold_days >= T2_EXTEND_MAX_DAYS)\n"
    "                        or ret <= hs * 100):\n"
    "                    _do_sell(code, pos, price,\n"
    "                             \"t2_force_after_extend \" + str(round(ret, 1)) + \"%\")\n"
    "                    continue\n"
    "                pos[\"t2_extended\"] = True\n"
    "                log(\"[EXT] \" + code + \" extend px=\" + str(round(price, 2)) +\n"
    "                    \" cost=\" + str(round(cost, 2)) +\n"
    "                    \" ret=\" + str(round(ret, 1)) + \"% hold_days=\" + str(hold_days))\n"
)
T_CAPEXT_NEW = (
    "                # weak regime makes the hold-cap breakdown-conditional.\n"
    "                cap_hit = (hold_days != 999 and hold_days >= T2_EXTEND_MAX_DAYS)\n"
    "                if weak and cap_hit and not _weak_cap_sell_ok(code, price, ret):\n"
    "                    cap_hit = False\n"
    "                    if pos.get(\"weak_cap_hold_log\") != today:\n"
    "                        pos[\"weak_cap_hold_log\"] = today\n"
    "                        log(\"[HOLD] weak-regime \" + code + \" intact past cap\" +\n"
    "                            \" ret=\" + str(round(ret, 1)) + \"%, keep running\")\n"
    "                if cap_hit or ret <= hs * 100:\n"
    "                    _do_sell(code, pos, price,\n"
    "                             \"t2_force_after_extend \" + str(round(ret, 1)) + \"%\")\n"
    "                    continue\n"
    "                # weak regime grants the extra day only to trend-intact\n"
    "                # names (price >= day VWAP). A broken name is NOT force-sold\n"
    "                # here -- vwap_weak_early (armed above) fires next morning.\n"
    "                if weak:\n"
    "                    vw = _day_vwap(code)\n"
    "                    if vw and vw > 0 and price < vw:\n"
    "                        if pos.get(\"weak_no_extend\") != today:\n"
    "                            pos[\"weak_no_extend\"] = today\n"
    "                            log(\"[EXT] weak-regime \" + code + \" below vwap=\" +\n"
    "                                str(round(vw, 2)) + \", no extend\")\n"
    "                    else:\n"
    "                        pos[\"t2_extended\"] = True\n"
    "                        log(\"[EXT] \" + code + \" extend px=\" + str(round(price, 2)) +\n"
    "                            \" cost=\" + str(round(cost, 2)) +\n"
    "                            \" ret=\" + str(round(ret, 1)) + \"% hold_days=\" + str(hold_days))\n"
    "                else:\n"
    "                    pos[\"t2_extended\"] = True\n"
    "                    log(\"[EXT] \" + code + \" extend px=\" + str(round(price, 2)) +\n"
    "                        \" cost=\" + str(round(cost, 2)) +\n"
    "                        \" ret=\" + str(round(ret, 1)) + \"% hold_days=\" + str(hold_days))\n"
)

# ---------------- ptrade flavor: context, _log(), load_score_file ----------------

P_CONST_NEW = C_CONST_NEW  # same T2_FORCE_HHMM anchor

P_FLOOR_END = C_FLOOR_END

P_HELPER = (
    "\n\n# ============ weak-regime helpers (2026-09-03) ============\n"
    "def _weak_regime(context, today):\n"
    "    \"\"\"Weak-market regime flag from today's candidates.json market_env\n"
    "    (server stamps yesterday's state5_q; weak = q==1). Cached per day on\n"
    "    context. Missing/unreadable -> False (legacy behavior).\"\"\"\n"
    "    cache = getattr(context, \"weak_regime_cache\", None)\n"
    "    if cache is None:\n"
    "        cache = {}\n"
    "        context.weak_regime_cache = cache\n"
    "    if today in cache:\n"
    "        return cache[today]\n"
    "    weak = False\n"
    "    if WEAK_REGIME_ENABLE:\n"
    "        try:\n"
    "            sc = context.scores_cache if hasattr(context, \"scores_cache\") else {}\n"
    "            d = load_score_file(today + \".candidates.json\", sc)\n"
    "            env = (d or {}).get(\"market_env\") or {}\n"
    "            weak = bool(env.get(\"weak_regime\"))\n"
    "        except Exception:\n"
    "            weak = False\n"
    "    cache[today] = weak\n"
    "    if weak:\n"
    "        _log(\"[REGIME] weak day: floor x\" + str(WEAK_FLOOR_MULT) +\n"
    "             \" peel x\" + str(WEAK_PB_MULT) +\n"
    "             \" extend/cap need trend-intact\")\n"
    "    return weak\n"
    "\n\n"
    "def _weak_cap_sell_ok(code, price, ret):\n"
    "    \"\"\"Weak regime: the T+3 hold-cap fires only on breakdown\n"
    "    (ret <= 0 or price below day VWAP). Trend-intact keeps running.\"\"\"\n"
    "    if ret <= 0:\n"
    "        return True\n"
    "    vw = _day_vwap(code)\n"
    "    if vw and vw > 0:\n"
    "        return price < vw\n"
    "    return True  # vwap unknown -> keep legacy behavior (sell at cap)\n"
)

P_ADAPT_OLD = (
    "        hs, ta, pb = _adaptive_params(code)\n"
    "\n"
    "        # hard stop: close-confirm window only\n"
)
P_ADAPT_NEW = (
    "        hs, ta, pb = _adaptive_params(code)\n"
    "        # weak regime tightens the breakdown exits (price conditions only).\n"
    "        weak = _weak_regime(context, today)\n"
    "        if weak:\n"
    "            pb = round(pb * WEAK_PB_MULT, 4)\n"
    "\n"
    "        # hard stop: close-confirm window only\n"
)

P_EXTCAP_OLD = (
    "                if hold_days != 999 and hold_days >= T2_EXTEND_MAX_DAYS:\n"
    "                    _do_sell(context, code, pos, price,\n"
    "                             \"t2_force_after_extend \" + str(round(ret, 1)) + \"%\")\n"
    "                    continue\n"
)
P_EXTCAP_NEW = (
    "                # weak regime turns the cap into a breakdown check.\n"
    "                if (hold_days != 999 and hold_days >= T2_EXTEND_MAX_DAYS\n"
    "                        and (not weak or _weak_cap_sell_ok(code, price, ret))):\n"
    "                    _do_sell(context, code, pos, price,\n"
    "                             \"t2_force_after_extend \" + str(round(ret, 1)) + \"%\")\n"
    "                    continue\n"
)

P_FLOOR_OLD = (
    "                force_floor = _t2_force_floor(code) * 100\n"
    "                if ret < force_floor:\n"
)
P_FLOOR_NEW = (
    "                force_floor = _t2_force_floor(code) * 100\n"
    "                if weak:\n"
    "                    # weak regime raises the floor (less negative).\n"
    "                    force_floor = round(force_floor * WEAK_FLOOR_MULT, 2)\n"
    "                if ret < force_floor:\n"
)

P_CAPEXT_OLD = (
    "                if ((hold_days != 999 and hold_days >= T2_EXTEND_MAX_DAYS)\n"
    "                        or ret <= hs * 100):\n"
    "                    _do_sell(context, code, pos, price,\n"
    "                             \"t2_force_after_extend \" + str(round(ret, 1)) + \"%\")\n"
    "                    continue\n"
    "                pos[\"t2_extended\"] = True\n"
    "                _log(\"[EXT] \" + code + \" extend px=\" + str(round(price, 2)) +\n"
    "                     \" cost=\" + str(round(cost, 2)) +\n"
    "                     \" ret=\" + str(round(ret, 1)) + \"% hold_days=\" + str(hold_days))\n"
)
P_CAPEXT_NEW = (
    "                # weak regime makes the hold-cap breakdown-conditional.\n"
    "                cap_hit = (hold_days != 999 and hold_days >= T2_EXTEND_MAX_DAYS)\n"
    "                if weak and cap_hit and not _weak_cap_sell_ok(code, price, ret):\n"
    "                    cap_hit = False\n"
    "                    if pos.get(\"weak_cap_hold_log\") != today:\n"
    "                        pos[\"weak_cap_hold_log\"] = today\n"
    "                        _log(\"[HOLD] weak-regime \" + code + \" intact past cap\" +\n"
    "                             \" ret=\" + str(round(ret, 1)) + \"%, keep running\")\n"
    "                if cap_hit or ret <= hs * 100:\n"
    "                    _do_sell(context, code, pos, price,\n"
    "                             \"t2_force_after_extend \" + str(round(ret, 1)) + \"%\")\n"
    "                    continue\n"
    "                # weak regime grants the extra day only to trend-intact\n"
    "                # names (price >= day VWAP). A broken name is NOT force-sold\n"
    "                # here -- vwap_weak_early (armed above) fires next morning.\n"
    "                if weak:\n"
    "                    vw = _day_vwap(code)\n"
    "                    if vw and vw > 0 and price < vw:\n"
    "                        if pos.get(\"weak_no_extend\") != today:\n"
    "                            pos[\"weak_no_extend\"] = today\n"
    "                            _log(\"[EXT] weak-regime \" + code + \" below vwap=\" +\n"
    "                                 str(round(vw, 2)) + \", no extend\")\n"
    "                    else:\n"
    "                        pos[\"t2_extended\"] = True\n"
    "                        _log(\"[EXT] \" + code + \" extend px=\" + str(round(price, 2)) +\n"
    "                             \" cost=\" + str(round(cost, 2)) +\n"
    "                             \" ret=\" + str(round(ret, 1)) + \"% hold_days=\" + str(hold_days))\n"
    "                else:\n"
    "                    pos[\"t2_extended\"] = True\n"
    "                    _log(\"[EXT] \" + code + \" extend px=\" + str(round(price, 2)) +\n"
    "                         \" cost=\" + str(round(cost, 2)) +\n"
    "                         \" ret=\" + str(round(ret, 1)) + \"% hold_days=\" + str(hold_days))\n"
)


def hdr(old_title: str, new_title: str, ver: str) -> tuple[str, str]:
    return (old_title + "\n",
            new_title + "\n" + HDR_NOTE.replace("{ver}", ver))


FILES = {
    # ---- QMT C flavor ----
    "track_a/TrackA_track_a_qmt_full_chain_sim.py": [
        hdr("# AlphaPilot -- Track A QMT sim full-chain strategy v2.30 (vwap 2nd confirm)",
            "# AlphaPilot -- Track A QMT sim full-chain strategy v2.31 (weak-regime exits)",
            "v2.31"),
        (C_CONST_ANCHOR, C_CONST_NEW),
        (C_FLOOR_END, C_FLOOR_END + C_HELPER_CAND),
        (C_ADAPT_OLD, C_ADAPT_NEW),
        (C_EXTCAP_OLD, C_EXTCAP_NEW),
        (C_FLOOR_OLD, C_FLOOR_NEW),
        (C_CAPEXT_OLD, C_CAPEXT_NEW),
    ],
    "track_b/TrackB_track_b_qmt_auction_live.py": [
        hdr("# AlphaPilot -- Track B QMT LIVE strategy TEMPLATE v2.7-tpl (vwap 2nd confirm)",
            "# AlphaPilot -- Track B QMT LIVE strategy TEMPLATE v2.8-tpl (weak-regime exits)",
            "v2.8-tpl"),
        (C_CONST_ANCHOR, C_CONST_NEW),
        (C_FLOOR_END, C_FLOOR_END + C_HELPER_FULLPOOL),
        (C_ADAPT_OLD, C_ADAPT_NEW),
        (C_EXTCAP_OLD, C_EXTCAP_NEW),
        (C_FLOOR_OLD, C_FLOOR_NEW),
        (C_CAPEXT_OLD, C_CAPEXT_NEW),
    ],
    "track_b/TrackB_track_b_qmt_auction_sim.py": [
        hdr("# AlphaPilot -- Track B QMT SIM auction-select strategy v2.7",
            "# AlphaPilot -- Track B QMT SIM auction-select strategy v2.8",
            "v2.8"),
        (C_CONST_ANCHOR, C_CONST_NEW),
        (C_FLOOR_END, C_FLOOR_END + C_HELPER_FULLPOOL),
        (C_ADAPT_OLD, C_ADAPT_NEW),
        (C_EXTCAP_OLD, C_EXTCAP_NEW),
        (C_FLOOR_OLD, C_FLOOR_NEW),
        (C_CAPEXT_OLD, C_CAPEXT_NEW),
    ],
    "track_b/TrackB_track_b_qmt_auction_sim_v2.6.py": [
        hdr("# AlphaPilot -- Track B QMT SIM auction-select strategy v2.7",
            "# AlphaPilot -- Track B QMT SIM auction-select strategy v2.8",
            "v2.8"),
        (C_CONST_ANCHOR, C_CONST_NEW),
        (C_FLOOR_END, C_FLOOR_END + C_HELPER_FULLPOOL),
        (C_ADAPT_OLD, C_ADAPT_NEW),
        (C_EXTCAP_OLD, C_EXTCAP_NEW),
        (C_FLOOR_OLD, C_FLOOR_NEW),
        (C_CAPEXT_OLD, C_CAPEXT_NEW),
    ],
    # ---- TDX flavor ----
    "track_a/TrackA_track_a_tdx_full_chain_sim.py": [
        hdr("# v2.29 2026-09-02 (vwap 2nd confirm, aligned with QMT v2.30):",
            "# v2.30 2026-09-03 (weak-regime exits, aligned with QMT v2.31):",
            "v2.30"),
        (T_CONST_ANCHOR, T_CONST_NEW),
        (T_FLOOR_END, T_FLOOR_END + t_helper("candidates.json", "_fetch_remote_scores")),
        (T_ADAPT_OLD, T_ADAPT_NEW),
        (T_EXTCAP_OLD, T_EXTCAP_NEW),
        (T_FLOOR_OLD, T_FLOOR_NEW),
        (T_CAPEXT_OLD, T_CAPEXT_NEW),
    ],
    "track_b/TrackB_track_b_tdx_auction_sim.py": [
        hdr("# AlphaPilot -- Track B TDX SIM auction-select strategy v1.18",
            "# AlphaPilot -- Track B TDX SIM auction-select strategy v1.19",
            "v1.19"),
        (T_CONST_ANCHOR, T_CONST_NEW),
        (T_FLOOR_END, T_FLOOR_END + t_helper("fullpool_live.json", "_fetch_remote_fullpool_live")),
        (T_ADAPT_OLD, T_ADAPT_NEW),
        (T_EXTCAP_OLD, T_EXTCAP_NEW),
        (T_FLOOR_OLD, T_FLOOR_NEW),
        (T_CAPEXT_OLD, T_CAPEXT_NEW),
    ],
    # ---- ptrade flavor ----
    "ptrade/TrackA_track_a_ptrade_live.py": [
        hdr("# AlphaPilot -- Track A Ptrade LIVE strategy TEMPLATE v1.7-tpl (vwap 2nd confirm)",
            "# AlphaPilot -- Track A Ptrade LIVE strategy TEMPLATE v1.8-tpl (weak-regime exits)",
            "v1.8-tpl"),
        (P_CONST_NEW and C_CONST_ANCHOR, P_CONST_NEW),
        (P_FLOOR_END, P_FLOOR_END + P_HELPER),
        (P_ADAPT_OLD, P_ADAPT_NEW),
        (P_EXTCAP_OLD, P_EXTCAP_NEW),
        (P_FLOOR_OLD, P_FLOOR_NEW),
        (P_CAPEXT_OLD, P_CAPEXT_NEW),
    ],
    "ptrade/TrackA_track_a_ptrade_sim.py": [
        hdr("# AlphaPilot -- Track A Ptrade SIM strategy v1.7 (vwap 2nd confirm)",
            "# AlphaPilot -- Track A Ptrade SIM strategy v1.8 (weak-regime exits)",
            "v1.8"),
        (C_CONST_ANCHOR, P_CONST_NEW),
        (P_FLOOR_END, P_FLOOR_END + P_HELPER),
        (P_ADAPT_OLD, P_ADAPT_NEW),
        (P_EXTCAP_OLD, P_EXTCAP_NEW),
        (P_FLOOR_OLD, P_FLOOR_NEW),
        (P_CAPEXT_OLD, P_CAPEXT_NEW),
    ],
}


def main() -> int:
    ok_all = True
    for rel, reps in FILES.items():
        p = ROOT / rel
        text = p.read_text(encoding="utf-8")
        errs = []
        for i, (old, new) in enumerate(reps):
            n = text.count(old)
            if n != 1:
                errs.append(f"  rep#{i} anchor count={n} (need 1): {old[:70]!r}")
                continue
            text = text.replace(old, new, 1)
        if errs:
            ok_all = False
            print(f"[FAIL] {rel}")
            for e in errs:
                print(e)
            continue
        p.write_text(text, encoding="utf-8", newline="\n")
        print(f"[OK]   {rel} ({len(reps)} edits)")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
