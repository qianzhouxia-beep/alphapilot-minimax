# -*- coding: utf-8 -*-
# AlphaPilot -- Track B TDX SIM auction-select strategy v1.18
# =========================================================
# v1.18 changes vs v1.17 (2026-09-02, vwap 2nd confirm, aligned with QMT v2.7):
#   * vwap_weak_early needs TWO still-below minutes.
# v1.17 changes vs v1.16 (2026-08-31, trading-day hold fix, aligned with QMT v2.6):
#   * _hold_days counts TRADING days, not calendar days. The old
#     (today - buy_date).days counted weekends/holidays, so a Friday buy read
#     as hold=3 on the following Monday (real T+1) and wrongly hit
#     t2_force_after_extend / rotation_sell. New _ASHARE_CLOSED_2026 set +
#     _trading_days_between(); only weekend + 2026 official closures excluded.
# v1.16 changes vs v1.15 (2026-08-31, vwap_weak_early next-morning confirm,
# aligned with QMT Track B v2.5):
#   * Sell at next open only if the live price is still BELOW the day-VWAP
#     reference recorded when the signal armed (price < vwap_ref). If the price
#     has recovered above the reference, cancel the signal and keep holding.
#     Evidence (QMT sim 08-31, n=3): unconditional next-open sell hit the day's
#     low and all three rallied +3.5%/+3.8%/+7.0%. New persisted field vwap_ref.
# v1.15 changes vs v1.14 (2026-08-29, P2 sweet-zone trigger priority):
#   * New SWEET_ZONE_MODE (0=off / 1=priority / 2=only): within each buy tier
#     (money_pass / fallback), candidates whose auction gap is in [-1.5%, 0]
#     get priority for the daily buy slots. Ordering-only, no scoring change.
#     BUY logs tagged [SWEET]. Aligned with QMT Track B v2.4.
# v1.14 changes vs v1.13 (2026-08-27, pos state persistence across TDX restarts):
#   * Persist sell-side metadata to b_tdx_pos_state.json (aligned with QMT Track B v2.3).
# v1.13 changes vs v1.12 (2026-08-26, fallback rank window + P2 day_low sync):
#   * fallback: before 10:00 rank<=10; from 10:00 rank<=15; rank>15 / hard_fail skip.
# v1.12 changes vs v1.11 (2026-08-26, P2 dynamic session-low trend):
#   * P2 trend c > day_low; drop p935 and prev_close day-trend guards.
# v1.11 changes vs v1.10 (2026-08-26, P2 board-gap + day-high guard):
#   * Board-aware no-chase + CONF_DAY_HIGH_MAX=0.85 (aligned with QMT Track B v2.0).
# v1.10 changes vs v1.9 (2026-08-22, stop hard-kicking gap<-2%):
#   * Individual open/auction gap below -2% is no longer eliminated;
#     it uses the existing demote band (gap < -0.5%).
# v1.9 changes vs v1.8 (2026-08-21, TDX 5m field-name fix):
#   * get_market_data now requests lowercase open/close/high/low/volume
#     (capitalized Open/Close made tqcenter warn 'field not in result').
#   * Empty 5m replies are cached after 2 fails so the console is not flooded;
#     P2/VWAP keep using snapshot fallback.
# v1.8 changes vs v1.7 (2026-08-20, T+1 winner force-sell fix):
#   * _today_buy_date recovers buy_date from the local trade log when the old
#     in-memory entry is gone after a restart and TodayBuyPosition is 0 (T+1
#     already unlocked), so _hold_days never sees an empty date and force-sells
#     a fresh winner at 14:45 (000651 QMT-SIM on 08-20: +1.5% t2_force_after_extend).
#   * _check_sell T+2 maturity check adds hold_days != 999 guard.
# v1.7 changes vs v1.6 (2026-08-19, Kimi 3 cross-validation fixes):
#   * P0-B: vwap_broken / wy_bc_armed no longer short-circuit the dynamic
#     t2_force floor at 14:45; they fire next morning (09:35-09:50) instead.
#   * P1: t2_extended positions are held until hold_days >= T2_EXTEND_MAX_DAYS
#     (old code sold on the very next 14:45 pass, so T+3 meant only +1 day).
# v1.6 changes vs v1.5 (2026-08-19, pattern-breakout boost into auction gate):
#   * _load_fullpool_classic now normalizes each row: score = server final
#     score (includes pattern-breakout and other soft boosts; fullpool.json
#     "score" field since 08-19), fall back to raw score_0500 when missing.
#   * _p1_gate base score prefers "score" over "score_0500", so the pattern-
#     breakout soft boost now influences the 09:25-09:35 auction ranking
#     (previously only the raw 05:00 model score was used).
# v1.5 changes vs v1.4 (2026-08-18, DSH review of sell-side rework):
#   * Rotation protection: T+0 AND T+1 holdings are immune to rotation
#     (ROTATION_MIN_HOLD_DAYS 1 -> 2); only T+2+ positions may be rotated.
#   * Daily rotation cap ROTATION_DAILY_MAX=1 (limit churn & fees).
#   * Hysteresis (ROTATION_WEAK_GATE): only rotate when the weakest holding shows a
#     concrete weakness signal (day<0 / below day-VWAP / early-exit / underwater).
# v1.4 changes vs v1.3 (2026-08-18, DHS sell-side eval P0+P1, aligned with Track A v2.13):
#   * T+2 force-close is now conditional: loss (ret<0) force-sell; profit without
#     an early-exit signal extends to T+3 (T2_EXTEND_MAX_DAYS, peel stays armed).
#   * Dynamic weakness rotation (P1): when holdings are full (MAX_HOLDINGS) and a
#     candidate passed P2, first sell the weakest position to free a slot, then
#     buy on the same bar. Weakness score = ret30% + vwap20% + day20% + early15%
#     + peel10% + days5%, relative-rank normalized, momentum guard (day>3% and
#     vol-ratio>1.3 -> skip).
# v1.3 changes vs v1.2 (2026-08-18):
#   _p2_decide bars path adds a day-trend guard (c >= prev_close): only confirm
#   when the stock is not down on the day. Prevents P2 from firing on intraday
#   rebounds inside an overall down session (e.g. the 08-18 Xidian 301130 QMT-SIM
#   case, where a stale-5m-bar bug let a money_flow_pass=false, -2.25% day stock
#   through at a fabricated 30.6 trigger price). Same rule as the snapshot
#   fallback (price > prev_close) -- keeps the three Track B clients in sync.
# v1.2 changes vs v1.1 (2026-08-17):
#   fullpool_live (server 09:36 rerank pool) synced from the QMT SIM version:
#   after LIVE_FULLPOOL_MIN (09:36) Track B uses {date}.fullpool_live.json
#   (server-applied 106-d factor + money + research gates, score = 0.6*pipeline
#   + 0.4*live momentum z) instead of the 05:00 classic fullpool. Client keeps
#   only real-time ABR soft re-check + P2 dynamic confirm (_p2_decide) as the
#   final trigger.
# v1.1 changes vs v1.0 (2026-08-17):
#   Buy window widened from a 09:40 hard cutoff to two intraday windows
#   (morning 09:36-11:30 + afternoon 13:00-14:00). Real Top10-pool backtest
#   (07-20..07-31, 50 P2 triggers): first-trigger 09:35-10:00 2% / 10:00-10:30
#   28% / 10:30-11:30 44% / 13:00-14:00 20% / 14:00+ 6%; old 09:40 cutoff
#   caught 0/50 (0%). Afternoon 13:00-14:00 best T+1 (+1.80%); tail 14:00+
#   worst (-3.66%) -> closed. top2_fired only closes when the daily budget is
#   full or the window closes (wait_confirm candidates retried every bar).
#   no_confirm_eod / skip_high_turnover now abandon via sent_today.
#   wait_confirm logs silenced (would spam 40-80 lines/bar on the widened pool).
# Track B (NEW) TongDaXin TdxQuant (TQ) version:
#   09:25-09:35 full-pool gated call-auction stock selection.
# Key differences vs Track A (TrackA_track_a_tdx_full_chain_sim.py v2.14):
#   [A] Track A reads {date}.candidates.json (Top10, server pre-picked)
#       -> P2 dynamic confirm -> Top2 buy.
#   [B] Track B reads {date}.fullpool.json (05:00 full candidate pool,
#       server only exports) -> TQ gating over ALL candidates:
#           P0 hard filter (board permission / near limit-up / no auction data)
#           P1 auction gate (aligns server pre_market_gate.py:
#                            near limit-up / gap-down / double-weak /
#                            demote / keep) + sector diversity
#                            (Top10<=2, Top20<=3, pool<=5)
#           P2 money gate (aligns server money_flow_gate.py; TDX uses
#                          snapshot-field approximation)
#       -> sort Top2 (money-gate pass first, then score_0500 desc)
#       -> order_stock buy
#   Sell logic identical to Track A TDX v2.10.
#
# TDX data differences (vs QMT Track B):
#   * no per-tick / no Level2 / no active-buy-ratio field -> P2 active-buy
#     ratio approximated by snapshot order-book ratio (Buy1Vol vs Sell1Vol),
#     as a SOFT signal: skip if unavailable, never hard-block.
#   * auction gap from snapshot Open/LastClose.
#   * turnover from snapshot Volume(hands)*100 / float shares
#     (same as TDX v2.10 _get_turnover).
#   * volume ratio = snapshot Volume(hands) / prev-5d avg 1d volume.
#
# Cross-validation findings implemented (DUAL_TRACK_BRIEFING.md sec.6):
#   * 1-minute loop granularity (TDX POLL_SEC already 20s, gate throttled)
#   * tick-approx active-buy ratio only after 09:30 (continuous session)
#   * P1 late-data cutoff CALL_DATA_CUTOFF=09:30 (new gaps update state
#     only, never enter decision)
#   * score_0500 = icir_raw_score -> score_raw -> ml_score (server fallback)
#   * main_net_5d pre-set by server; ==0 means missing -> skip money hard gate
#   * sector aggregation: TQ get_stock_info / sector members unreliable ->
#     aggregate candidate gaps within the pool itself (the candidate pool
#     spans many sectors, keeps full-pool sample avoiding n=1 distortion)
#
# Naming convention (distinguishable at a glance from Track A):
#   Track A: TrackA_track_a_qmt_full_chain_sim.py  (QMT SIM)
#            TrackA_track_a_qmt_full_chain_live.py (QMT LIVE template)
#            TrackA_track_a_tdx_full_chain_sim.py  (TDX SIM)
#   Track B: TrackB_track_b_qmt_auction_sim.py   (QMT SIM)
#            TrackB_track_b_qmt_auction_live.py  (QMT LIVE template, per account)
#            TrackB_track_b_tdx_auction_sim.py   (TDX SIM)
#
# How to run:
#   1) start TongDaXin "quant terminal (SIM)" and login a SIM trade account
#   2) strongly suggested: system menu -> download after-hours data,
#      tick 1m/5m lines (P2 confirm needs them)
#   3) set ACCOUNT below to your TDX SIM capital account
#      (leave empty = auto use currently logged-in account)
#   4) python TrackB_track_b_tdx_auction_sim.py
# =========================================================
from __future__ import print_function

import os
import sys

# ---- tqcenter auto-locate (same as Track A TDX v2.10) ----
def _find_tq_user():
    cands = []
    env = os.environ.get("TDX_PYPLUGIN", "")
    if env:
        cands.append(env)
    root = os.environ.get("TDX_ROOT", "")
    if root:
        cands.append(os.path.join(root, "PYPlugins", "user"))
    for d in (r"C:\new_tdx_mock", r"D:\new_tdx_mock",
              r"C:\gjzq_quant_terminal", r"D:\gjzq_quant_terminal",
              r"C:\tdx_mock", r"D:\tdx_mock"):
        cands.append(os.path.join(d, "PYPlugins", "user"))
    for drive in ("C", "D", "E"):
        try:
            for name in os.listdir(drive + ":\\"):
                p = os.path.join(drive + ":\\", name, "PYPlugins", "user")
                if os.path.isdir(p):
                    cands.append(p)
        except OSError:
            pass
    seen = set()
    for p in cands:
        if p in seen:
            continue
        seen.add(p)
        if os.path.isdir(p):
            if p not in sys.path:
                sys.path.insert(0, p)
            return p
    return None


_TQ_USER = _find_tq_user()
if _TQ_USER is None:
    sys.stderr.write("[FATAL] cannot find TDX quant PYPlugins\\user dir\n")
    sys.stderr.write("  set env TDX_ROOT (TDX install root dir) or\n")
    sys.stderr.write("  run this script from the quant PYPlugins\\user dir\n")
    sys.exit(1)

from tqcenter import tq, tqconst

import json
import math
import time
from datetime import datetime, timedelta

# =========================================================
# A-share trading-day calendar (2026). hold_days must count TRADING days,
# not calendar days: the old (today - buy_date).days counted weekends and
# holidays, so a Friday buy read as hold=3 on the following Monday (real
# T+1) and wrongly triggered t2_force_after_extend / rotation sells (QMT
# live 08-31: 002466 and 002058). Closures per SSE/SZSE/BSE 2026 notice.
# Weekends are excluded by weekday(); this set lists holiday weekdays only.
_ASHARE_CLOSED_2026 = frozenset({
    "20260101", "20260102",                     # New Year
    "20260216", "20260217", "20260218",         # Spring Festival
    "20260219", "20260220", "20260223",
    "20260406",                                 # Qingming
    "20260501", "20260504", "20260505",         # Labour Day
    "20260619",                                 # Dragon Boat
    "20260925",                                 # Mid-Autumn
    "20261001", "20261002", "20261005",         # National Day
    "20261006", "20261007",
})


def _is_trading_day(d):
    """True if date d is an A-share trading day in 2026."""
    if d.weekday() >= 5:
        return False
    return d.strftime("%Y%m%d") not in _ASHARE_CLOSED_2026


def _trading_days_between(b, t):
    """Number of trading days in (b, t]; buy day excluded, today included."""
    n = 0
    d = b
    while d < t:
        d = d + timedelta(days=1)
        if _is_trading_day(d):
            n += 1
    return n

# ================= CONFIG =================
ACCOUNT = "1190388433"  # TDX SIM capital account (empty = auto use logged-in account)
SCORE_DIR = r"C:\alphapilot\scores"
REMOTE_SCORE_BASE = "http://150.158.100.236/qmt_scores"  # server nginx static dir
REMOTE_FETCH_SEC = 60         # min interval between remote fetch attempts
REMOTE_TIMEOUT = 8            # seconds per remote fetch
REMOTE_FETCH_START_MIN = 6 * 60 + 30  # fullpool ready 06:30; fetch after 07:00
TRADE_LOG = r"C:\alphapilot\b_tdx_trades.json"
LEDGER_DAILY = r"C:\alphapilot\b_tdx_ledger_daily.json"
LOG_FILE = r"C:\alphapilot\b_tdx_auction.log"
ORDER_LOCK_FILE = r"C:\alphapilot\b_tdx_order_locks.json"
GATE_LOG = r"C:\alphapilot\b_tdx_auction_gate.json"   # gate detail (debug)

MAX_HOLDINGS = 4
MAX_DAILY_BUY = 2
POSITION_PCT = 0.22

# --- Track B time windows ---
AUCTION_START_MIN = 9 * 60 + 25
GATE_START_MIN = 9 * 60 + 30
DECIDE_MIN = 9 * 60 + 35
CALL_DATA_CUTOFF = 9 * 60 + 30

# --- Track B LIVE pool (09:36 server rerank, added 2026-08-17) ---
# Server runs live_momentum_scanner (09:35) + morning_live_fund_select then
# export_qmt_scores.py --fullpool-live at 09:36, producing
# {date}.fullpool_live.json with per-stock server-computed fields:
#   score(=0.6*pipeline106d + 0.4*live momentum z), money_flow_pass,
#   research_tier, live_momentum_z, main_net, main_net_5d, active_buy_ratio,
#   turnover, volume_ratio, change_pct, pre_market_gap_pct, pre_market_action.
# Track B switches to this live pool after LIVE_FULLPOOL_MIN: rank by server
# score, gate by server money_flow_pass/research_tier (106-d factor + money +
# research gates all already applied server-side), keep TDX-side P2 dynamic
# confirm (_p2_decide) as the final buy trigger. Before 09:36 (or when the
# live file is missing) the classic 09:25-09:35 P1/P2 auction flow is used.
LIVE_FULLPOOL_MIN = 9 * 60 + 36   # switch to server live pool at/after 09:36
USE_SERVER_GATES = True           # use server money_flow_pass/research_tier/score

# --- Track B buy window (v1.1, 2026-08-17): widened from 09:40 hard cutoff ---
# Evidence (real production Top10 pool backtest 2026-07-20..07-31, 50 P2
# triggers): first-trigger time 09:35-10:00 2% / 10:00-10:30 28% /
# 10:30-11:30 44% / 13:00-14:00 20% / 14:00-14:57 6%. The old DECIDE_END_MIN
# =09:40 caught 0/50 triggers (0%) -> Track B never bought. Now two intraday
# windows: morning 09:36-11:30 (74% of triggers) + afternoon 13:00-14:00 (20%,
# best T+1 +1.80%); close after 14:00 (tail T+1 -3.66%, small n=3).
BUY_AM_END_MIN = 11 * 60 + 30
BUY_PM_START_MIN = 13 * 60
BUY_PM_END_MIN = 14 * 60

# --- P1 auction gate (aligns server pre_market_gate.py) ---
GAP_LIMIT_UP = 9.0
# GAP_HARD_DROP removed 2026-08-22: gap<-2% now demotes, does not eliminate.
GAP_DEMOTE = -0.5
SECTOR_WEAK_THRESHOLD = -1.5
MAX_SAME_SECTOR_IN_TOP10 = 2
MAX_SAME_SECTOR_IN_TOP20 = 3
MAX_SAME_SECTOR_IN_POOL = 5
P1_KEEP_TOP_N = 50

# --- P2 sweet-zone priority (v1.15, 2026-08-29, aligned with QMT v2.4) ---
# P2 triggers with auction gap in [-1.5%, 0] (slight low-open) show upward-bias
# T+1 vs the rest. Trigger-order preference only, not a scoring change.
#   SWEET_ZONE_MODE 0 = off (status quo)
#                    1 = priority (sweet first, non-sweet still fill)
#                    2 = only (strictly sweet-zone, fewer trades)
SWEET_ZONE_MODE = 1
SWEET_GAP_LO = -1.5               # sweet zone = gap% in [LO, HI]
SWEET_GAP_HI = 0.0

# --- P2 money gate (aligns server money_flow_gate.py; TDX snapshot approx) ---
MIN_ACTIVE_BUY = 0.52
MIN_TURNOVER = 2.0
MAX_TURNOVER = 35.0
MIN_VOL_RATIO = 0.8
MAX_DROP_PCT = -5.0
MIN_MAIN_NET_5D = 0.0

# --- P2 dynamic confirm (same as TDX v2.10) ---
CONF_VOL_RATIO = 1.3
CONF_MAX_GAP = 0.08           # legacy uniform cap (superseded by _p2_max_gap)
CONF_DAY_HIGH_MAX = 0.85      # skip if (c-low)/(high-low) > 0.85 (top 15% of range)
CONF_START_MIN = 9 * 60 + 35
CONF_END_MIN = 14 * 60 + 57
CONF_MAX_TURNOVER = 5.0

# --- fallback buy rank window (v1.13, 2026-08-26) ---
FALLBACK_RANK_OPEN_MIN = 10 * 60
FALLBACK_RANK_CAP_AM = 10
FALLBACK_RANK_CAP_PM = 15
FALLBACK_SKIP_HARD_FAIL = True

# --- board permission filter ---
ALLOW_STAR = True             # STAR market 688/689
ALLOW_CHINEXT = True          # ChiNext 300/301
ALLOW_BSE = True              # BSE 8xx/4xx/920

# --- adaptive exit (aligned with QMT) ---
DEF_HARD_STOP = -0.10
DEF_TRAIL_ARM = 0.03
DEF_PEEL_PB = 0.015
PEEL_MAX_STEPS = 2
VOL_BASELINE = 0.30

# --- T+2 force close ---
T2_FORCE_MIN = 14 * 60 + 45
T2_EXTEND_MIN_PRICE_RATIO = 0.95

# --- T+2 conditional force-close + dynamic weakness rotation (v1.5, 2026-08-18) ---
# Data basis (DHS eval + prod Top2 paired sample, 11 trading days):
#   T+2 profit group holding +1d: mean slightly up but only 44% keep rising,
#     must be backed by peel; T+2 loss group holding +1d: mean -0.82pp, force sell.
#   T+3 profit group holding to T+4: +1.71pp / 62.5% keep rising, but n=14 -> default T+3.
T2_EXTEND_MAX_DAYS = 3          # max hold days for a profitable position (T+3; try 4 for T+4)
T2_EXTEND_PROFIT_MIN = 0.0      # legacy: superseded by the dynamic t2_force floor (v1.7)
# Dynamic T+2 force-close floor (v1.6, 2026-08-19): a wide intraday amplitude
# and high vol name tolerates a deeper normal pullback. A fixed 0% floor
# force-sold healthy names on noise (300591 08-19: buy slip to 8.54 made the
# next day's -1% look like -8.7%; 301130 was force-sold at +33% only because
# the _day_vwap unit bug set vwap_broken). Now ret must fall below the dynamic
# floor to force-sell; hard_stop (hs) still catches the true tail risk.
T2_FORCE_AMP_FRAC = 0.50        # fraction of day amplitude (%) added to the floor
T2_FORCE_AMP_MIN = 4.0          # amplitude below this adds no extra tolerance
T2_FORCE_VOL_K = 0.10           # +0.10 annual vol -> -1pp more tolerance
T2_FORCE_FLOOR_MAX = -0.10      # absolute floor (never below hard_stop)

# Buy-side slip guard (v1.6, 2026-08-19): the P2 trigger is a 5m bar close that
# can lag the live tape on a fast move; a market order then fills far above the
# trigger (300591 08-18: trig 7.88 filled 8.54, +8.4%). The inflated cost turns
# a normal next-day pullback into a deep "loss" that the old fixed 0% t2_force
# floor force-sold. If the live price has already run > MAX_BUY_SLIP_PCT above
# the trigger, hold off (do not chase) instead of buying at a blown cost.
MAX_BUY_SLIP_PCT = 0.02
ROTATION_ENABLE = True          # rotation master switch (P1)
ROTATION_SELL_N = 1             # max stocks to rotate out per event (conservative; try 2)
ROTATION_MIN_HOLD_DAYS = 2      # only rotate positions held >= 2 days (T+2+); T+0/T+1 immune
ROTATION_DAILY_MAX = 1          # at most 1 rotation per day (limit churn & fees)
ROTATION_WEAK_GATE = True       # hysteresis: only rotate when the weakest holding shows a
                                #   concrete weakness signal (day<0 / below day-VWAP /
                                #   early-exit flagged / underwater from cost). Pool-independent;
                                #   rank-normalized scores collapse under ties and cannot separate
                                #   a healthy "relatively weakest" from a genuinely weak name.
ROTATION_MOMENTUM_DROP_PCT = 3.0   # daily gain > 3% = freshly launched (momentum guard)
ROTATION_MOMENTUM_VOL_RATIO = 1.3  # and vol-ratio > 1.3 to trigger momentum guard
# weakness score weights (sum = 1.0; higher = more likely to sell)
W_WEAK_RET = 0.30            # cumulative return (loss = weak)
W_WEAK_VWAP = 0.20           # below day-VWAP (technical weakness)
W_WEAK_DAY = 0.20            # daily change (laggard = weak)
W_WEAK_EARLY = 0.15          # early-exit signal flagged (Wyckoff/VWAP)
W_WEAK_PEEL = 0.10           # peel already done (profit locked -> low weak score)
W_WEAK_DAYS = 0.05           # closer to T+2 force-close day (weaker)

# --- VWAP weak-early exit ---
VWAP_CONFIRM_MIN = T2_FORCE_MIN
VWAP_SELL_START = 9 * 60 + 35
VWAP_SELL_END = 9 * 60 + 50

# --- Wyckoff distribution ---
WY_BC_WIN = 10
WY_BC_HI_LOOKBACK = 60
WY_BC_VOL_RATIO = 1.5
WY_BC_SHADOW_FRAC = 0.35
WY_UT_BOX_DAYS = 20
WY_UT_BREAK_PCT = 0.01
WY_BC_SELL_VOL_RATIO = 1.5
WY_BC_SELL_SHADOW_FRAC = 0.35
WY_BC_SELL_NEAR_PEAK = 0.98

# --- file-backed order lock ---
ORDER_LOCK_FILE = r"C:\alphapilot\b_tdx_order_locks.json"
POS_STATE_FILE = r"C:\alphapilot\b_tdx_pos_state.json"
POS_STATE_PERSIST = (
    "buy_date", "cost", "peak", "peel_count", "peel_peak_snapshot",
    "t2_extended", "vwap_broken", "vwap_ref", "vwap_early_hits", "vwap_early_min",
    "wy_bc_armed", "trail_armed",
    "awaiting_new_high",
)

# --- safety ---
LIMIT_DOWN_PCT = -9.7
ANOMALY_PCT = -21.0
POLL_SEC = 20
LEDGER_SNAP_MIN = 15 * 60 + 5
LEDGER_DUP_SEC = 300

# ================= STATE =================
ST = {
    "account": None,
    "positions": {},      # code -> {shares,cost,buy_date,peak,trail_armed,...}
    "trade_log": [],
    "sent_today": set(),
    "last_sig": {},
    "current_date": "",
    "snap_day": "",
    "prev_close": {},     # code -> prev close (for gap/turnover checks)
    "last_remote_fetch": 0,
    # Track B gate state
    "gap_cache": {},      # code -> gap_pct (auction gap, late updates ok)
    "sector_gap_mean": {},
    "p1_survivors": [],   # P1 survivors list
    "top2_fired": False,
    "gate_dump_done": False,
    "live_pool_active": False,  # True when {date}.fullpool_live.json in use
    "live_surv_ready": False,
    "last_gate_sec": 0,   # gate throttle (sec)
}


# ================= HELPERS =================
def log(msg):
    """Print to console AND append to LOG_FILE (so runtime logs survive
    even when the TDX python console is closed/restarted)."""
    line = datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " " + msg
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except BaseException:
        pass


def qmt_code(code, exchange=""):
    """Convert bare code to X.YY format (600519.SH / 300308.SZ)."""
    c = str(code or "").strip()
    if "." in c:
        return c
    c = "".join(ch for ch in c if ch.isdigit())
    if not c:
        return str(code or "")
    ex = str(exchange or "").upper()
    if ex in ("SH", "SZ", "BJ"):
        return c + "." + ex
    if c[0] in ("6", "9"):
        return c + ".SH"
    if c[0] in ("0", "2", "3"):
        return c + ".SZ"
    return c + ".BJ"


def bare_code(code):
    return str(code or "").split(".")[0]


def _dict_of(obj):
    """Normalize TDX query result (dict / list / object) to dict."""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if isinstance(obj, list):
        for x in obj:
            if isinstance(x, dict):
                return x
        obj = obj[0] if obj else None
        if obj is None:
            return {}
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return {}


# ================= LEDGER / ORDER LOCK =================
def _load_order_locks():
    try:
        with open(ORDER_LOCK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_order_locks(d):
    try:
        with open(ORDER_LOCK_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
    except Exception:
        pass


def _order_locked(today, code, reason):
    try:
        d = _load_order_locks()
        return bool(d.get(today, {}).get(code, {}).get(reason, False))
    except Exception:
        return False


def _mark_order_locked(today, code, reason):
    try:
        d = _load_order_locks()
        d.setdefault(today, {}).setdefault(code, {})[reason] = time.time()
        for old in [k for k in d if k != today]:
            d.pop(old, None)
        _save_order_locks(d)
    except Exception:
        pass


def _sell_lock_key(reason):
    if not reason:
        return "SELL"
    tok = str(reason).split(" ")[0]
    if tok.startswith("t2_force"):
        return "t2_force"
    return tok


def _load_ledger():
    try:
        if os.path.exists(TRADE_LOG):
            with open(TRADE_LOG, "r", encoding="utf-8") as f:
                ST["trade_log"] = json.load(f)
    except Exception:
        ST["trade_log"] = []
    ST["pos_state"] = _load_pos_state()


def _log_trade(action, code, price, vol, reason):
    try:
        rec = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "action": action,
            "symbol": code,
            "price": round(float(price or 0), 3),
            "volume": int(vol or 0),
            "reason": reason,
        }
        sig = (action, code, rec["price"], rec["volume"])
        now = time.time()
        last = ST["last_sig"].get(sig, 0.0)
        if now - last < LEDGER_DUP_SEC:
            return
        ST["last_sig"][sig] = now
        ledger = list(ST["trade_log"]) + [rec]
        with open(TRADE_LOG, "w", encoding="utf-8") as f:
            json.dump(ledger, f, ensure_ascii=False)
        ST["trade_log"] = ledger
    except Exception:
        pass


def _snap_daily(today, now):
    try:
        pos_list = []
        for code, pos in ST["positions"].items():
            shares = int(pos.get("shares") or 0)
            cost = float(pos.get("cost") or 0)
            if shares <= 0:
                continue
            px = _last_price(code) or cost
            pl = (px - cost) * shares
            pct = (px / cost - 1) * 100 if cost > 0 else 0.0
            pos_list.append({
                "code": code, "shares": shares, "cost": round(cost, 3),
                "price": round(px, 3), "pl": round(pl, 2),
                "pl_pct": round(pct, 2),
            })
        realized = 0.0
        for tr in ST["trade_log"]:
            if not str(tr.get("time", "")).startswith(now.strftime("%Y-%m-%d")):
                continue
            act = tr.get("action", "")
            px = float(tr.get("price") or 0)
            vol = int(tr.get("volume") or 0)
            if act.startswith("SELL"):
                realized += px * vol
        day = {
            "date": today,
            "time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "positions": pos_list,
            "unrealized_pl": round(sum(p["pl"] for p in pos_list), 2),
            "realized_proceeds": round(realized, 2),
        }
        data = {}
        if os.path.exists(LEDGER_DAILY):
            try:
                with open(LEDGER_DAILY, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        data[today] = day
        with open(LEDGER_DAILY, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        log("[LEDGER] snapshot " + today + " pos=" + str(len(pos_list)) +
            " unreal=" + str(day["unrealized_pl"]))
    except Exception:
        pass


# ================= TDX DATA =================
def _snap(code):
    """Real-time market snapshot. Returns dict or None.
    Fields: Now=last, LastClose=prev close, Open, Max(high), Min(low),
    Volume(hands), Amount, Average(avg price), Before5MinNow,
    Buy1Vol/Buy1 (bid1 vol/price), Sell1Vol/Sell1 (ask1 vol/price)."""
    try:
        s = tq.get_market_snapshot(stock_code=code)
        if not isinstance(s, dict) or not s:
            return None
        if str(s.get("ErrorId", "0")) != "0":
            return None
        return s
    except BaseException:
        return None


def _f(snap, *keys, default=None):
    """First non-empty numeric value among keys in snapshot."""
    if not isinstance(snap, dict):
        return default
    for k in keys:
        v = snap.get(k)
        if v is None:
            continue
        try:
            fv = float(v)
            if fv > 0:
                return fv
        except (TypeError, ValueError):
            continue
    return default


def _md_col(df, name):
    """Return a get_market_data column by name, case-insensitive.
    TdxQuant K-line keys are lowercase (open/close/high/low/volume). Asking
    for 'Open' makes tqcenter print 'field Open not in result, ignored'."""
    if not df:
        return None
    want = str(name or "").lower()
    try:
        for k in df:
            if str(k).lower() == want:
                return df[k]
    except Exception:
        return None
    return None


def _md_series(df, field, code):
    col = _md_col(df, field)
    if col is None:
        return None
    try:
        try:
            s = col[code]
        except Exception:
            s = col
        return s
    except Exception:
        return None


def _get_md(fields, stock_list, period, count):
    """tq.get_market_data with lowercase field names. After two empty 5m
    replies, stop polling for the session so the console is not flooded."""
    period = str(period or "")
    if period == "5m" and ST.get("_m5_dead"):
        return None
    low = [str(f).lower() for f in (fields or [])]
    df = None
    try:
        df = tq.get_market_data(
            field_list=low, stock_list=stock_list,
            period=period, count=count, dividend_type="none")
    except BaseException:
        df = None
    if period == "5m":
        has = (_md_col(df, "close") is not None or
               _md_col(df, "volume") is not None)
        if has:
            ST["_m5_fail_n"] = 0
        else:
            n = int(ST.get("_m5_fail_n") or 0) + 1
            ST["_m5_fail_n"] = n
            if n >= 2:
                ST["_m5_dead"] = True
                log("[M5] no 5m bars from get_market_data; stop polling, "
                    "P2/VWAP use snapshot fallback")
    return df


def _last_price(code):
    """Latest realtime price. Snapshot Now first, fallback 1m K-line."""
    s = _snap(code)
    if s is not None:
        p = _f(s, "Now", "LastPrice", default=None)
        if p is not None and p > 0:
            return p
    try:
        df = _get_md(["close"], [code], "1m", 1)
        closes = _md_series(df, "close", code)
        if closes is None or len(closes) == 0:
            return None
        v = closes.iloc[-1]
        return float(v)
    except BaseException:
        return None


def _prev_close(code):
    """Yesterday's close. Snapshot LastClose first, fallback 1d K-line."""
    s = _snap(code)
    if s is not None:
        p = _f(s, "LastClose", "PrevClose", default=None)
        if p is not None and p > 0:
            return p
    try:
        df = _get_md(["close"], [code], "1d", 2)
        arr = _md_series(df, "close", code)
        if arr is None or len(arr) < 2:
            return None
        return float(arr.iloc[-2])
    except BaseException:
        return None


def _snap_open_high(code):
    """(open, high) from snapshot. (None, None) on failure."""
    s = _snap(code)
    if s is None:
        return None, None
    return (_f(s, "Open", default=None), _f(s, "Max", "High", default=None))


def _annual_vol(code):
    """20-day annualized volatility (0.10~0.80), same formula as QMT."""
    try:
        df = _get_md(["close"], [code], "1d", 22)
        arr = _md_series(df, "close", code)
        if arr is None or len(arr) < 3:
            return None
        closes = [float(x) for x in arr]
        lr = [math.log(closes[i] / closes[i - 1])
              for i in range(1, len(closes))
              if closes[i - 1] > 0 and closes[i] > 0]
        if len(lr) < 2:
            return None
        m = sum(lr) / len(lr)
        var = sum((x - m) ** 2 for x in lr) / (len(lr) - 1)
        dv = math.sqrt(var)
        av = dv * math.sqrt(252)
        return max(0.10, min(0.80, av))
    except BaseException:
        return None


def _adaptive_params(code):
    """Return (hard_stop_pct, trail_arm, peel_pullback) adaptive (same as QMT)."""
    vol = _annual_vol(code)
    if vol is None:
        return DEF_HARD_STOP, DEF_TRAIL_ARM, DEF_PEEL_PB
    dev = vol - VOL_BASELINE
    hs = round(DEF_HARD_STOP - dev * 0.10, 3)
    ta = round(max(0.01, DEF_TRAIL_ARM - dev * 0.05), 3)
    pb = round(min(0.05, DEF_PEEL_PB + dev * 0.03), 3)
    return hs, ta, pb


def _day_amplitude_pct(code):
    """Today's intraday amplitude in % of prev close (high-low)/prev*100.
    0.0 when data is unavailable. Uses today's 5m bars high/low."""
    try:
        pc = _prev_close(code)
        if not pc or pc <= 0:
            return 0.0
        bars = _get_m5_bars(code)
        if not bars:
            return 0.0
        hi = max(b[3] for b in bars)
        lo = min(b[4] for b in bars)
        if hi <= 0 or lo <= 0:
            return 0.0
        return max(0.0, (hi - lo) / pc * 100.0)
    except BaseException:
        return 0.0


def _t2_force_floor(code):
    """Dynamic T+2 force-close floor (negative %). A fixed 0% floor force-sold
    every loser at 14:45 regardless of how wide the name's normal range is;
    on a wide-amplitude / high-vol day that is just noise, not weakness
    (300591 08-19: bought 7.88 P2 but the tape filled 8.54, next day -8.7%
    vs cost yet only -1% from the trigger -> the 0% floor was the aggressor).
    The floor now widens (more negative) with the day's amplitude and the
    stock's annual vol, so a normal pullback inside the day's range survives
    to T+3. Capped at T2_FORCE_FLOOR_MAX so hard_stop (hs) still owns the tail."""
    amp = _day_amplitude_pct(code)
    vol = _annual_vol(code) or VOL_BASELINE
    if amp > 0:
        tol = max(0.0, amp - T2_FORCE_AMP_MIN) * T2_FORCE_AMP_FRAC / 100.0
    else:
        tol = 0.0
    if vol > VOL_BASELINE:
        tol += (vol - VOL_BASELINE) * T2_FORCE_VOL_K
    floor = -tol
    if floor < T2_FORCE_FLOOR_MAX:
        floor = T2_FORCE_FLOOR_MAX
    return floor


def _get_m5_bars(code):
    """Today's 5m K-lines. Return [(tmin, open, close, high, low, vol), ...].
    tmin = real bar time (minutes since midnight). Only today's bars are kept."""
    try:
        df = _get_md(["open", "close", "high", "low", "volume"], [code], "5m", 48)
        closes = _md_series(df, "close", code)
        if closes is None or len(closes) == 0:
            return None
        idx = closes.index
        opens = _md_series(df, "open", code)
        highs = _md_series(df, "high", code)
        lows = _md_series(df, "low", code)
        vols = _md_series(df, "volume", code)
        if opens is None or highs is None or lows is None or vols is None:
            return None
        n = min(len(closes), len(opens), len(highs), len(lows), len(vols))
        if n < 2:
            return None
        today_str = datetime.now().strftime("%Y-%m-%d")
        out = []
        for i in range(n):
            t = idx[i]
            if t.strftime("%Y-%m-%d") != today_str:
                continue
            tmin = int(t.hour) * 60 + int(t.minute)
            out.append((tmin, float(opens.iloc[i]), float(closes.iloc[i]),
                        float(highs.iloc[i]), float(lows.iloc[i]),
                        float(vols.iloc[i])))
        if len(out) < 2:
            return None
        return out
    except BaseException:
        return None


def _day_vwap(code):
    """Day VWAP. Prefer snapshot Average, fallback 5m bars amount/volume."""
    s = _snap(code)
    if s is not None:
        avg = _f(s, "Average", "Avg", default=None)
        if avg is not None and avg > 0:
            return avg
    try:
        df = _get_md(["close", "volume"], [code], "5m", 48)
        closes = _md_series(df, "close", code)
        vols = _md_series(df, "volume", code)
        if closes is None or vols is None:
            return None
        n = min(len(closes), len(vols))
        if n < 2:
            return None
        tv = 0.0
        ta = 0.0
        for i in range(n):
            v = float(vols.iloc[i])
            c = float(closes.iloc[i])
            if v <= 0:
                continue
            tv += v
            ta += c * v
        if tv <= 0 or ta <= 0:
            return None
        return ta / tv
    except BaseException:
        return None


def _get_daily_bars(code, count=80):
    """Daily OHLCV bars (exclude today's partial bar). Return list of
    (open, high, low, close, volume) oldest-first, or None on fail."""
    try:
        df = _get_md(["open", "high", "low", "close", "volume"], [code], "1d", count)
        closes = _md_series(df, "close", code)
        if closes is None or len(closes) == 0:
            return None
        opens = _md_series(df, "open", code)
        highs = _md_series(df, "high", code)
        lows = _md_series(df, "low", code)
        vols = _md_series(df, "volume", code)
        if opens is None or highs is None or lows is None or vols is None:
            return None
        n = min(len(closes), len(opens), len(highs), len(lows), len(vols))
        if n < 3:
            return None
        out = []
        for i in range(n):
            out.append((float(opens.iloc[i]), float(highs.iloc[i]),
                        float(lows.iloc[i]), float(closes.iloc[i]),
                        float(vols.iloc[i])))
        return out[:-1]
    except BaseException:
        return None


# ================= WYCKOFF DISTRIBUTION (same as Track A TDX v2.10) =================
def _wyckoff_distribution(code):
    try:
        bars = _get_daily_bars(code, 80)
        if not bars or len(bars) < 62:
            return False
        op = [b[0] for b in bars]
        hi = [b[1] for b in bars]
        lo = [b[2] for b in bars]
        cl = [b[3] for b in bars]
        vo = [b[4] for b in bars]
        m = len(hi)
        if m < 62:
            return False
        hi60 = float(max(hi[: m - 10])) if m - 10 > 0 else 0.0
        if hi60 > 0:
            vma20 = float(sum(vo[m - 21:m - 1]) / 20) if m > 21 else 0.0
            for k in range(max(0, m - 10), m):
                if hi[k] >= hi60 * 0.97 and vo[k] > vma20 * WY_BC_VOL_RATIO:
                    body_top = max(op[k], cl[k])
                    tail = hi[k] - body_top
                    if (cl[k] < op[k] or
                            tail > (hi[k] - lo[k]) * WY_BC_SHADOW_FRAC):
                        return True
        if m >= WY_UT_BOX_DAYS:
            lo20 = float(min(lo[m - WY_UT_BOX_DAYS:m]))
            hi20 = float(max(hi[m - WY_UT_BOX_DAYS:m]))
            if hi20 > lo20 > 0:
                win5_hi = float(max(hi[m - 5:m]))
                if (win5_hi > hi20 * (1 + WY_UT_BREAK_PCT) and
                        cl[m - 1] <= hi20):
                    return True
        return False
    except BaseException:
        return False


def _wyckoff_holding_bc(code, peak):
    if peak <= 0:
        return False
    try:
        bars = _get_daily_bars(code, 22)
        if not bars or len(bars) < 5:
            return False
        vols = [b[4] for b in bars]
        vma20 = float(sum(vols[-20:]) / min(20, len(vols)))
        if vma20 <= 0:
            return False
    except BaseException:
        return False
    m5 = _get_m5_bars(code)
    if not m5 or len(m5) < 2:
        return False
    today_v = sum(b[5] for b in m5)
    if today_v <= vma20 * WY_BC_SELL_VOL_RATIO:
        return False
    for b in m5:
        _, o, c, h, l, _ = b
        if h >= peak * WY_BC_SELL_NEAR_PEAK:
            body_top = max(o, c)
            tail = h - body_top
            rng = h - l
            if (c < o or (rng > 0 and tail > rng * WY_BC_SELL_SHADOW_FRAC)):
                return True
    return False


# ================= Track B: FULLPOOL LOAD =================
def _fetch_remote_fullpool(today):
    """Fetch {date}.fullpool.json from server nginx if local file missing.
    Throttled + silent-fail, retry next loop. fullpool generated 06:30."""
    now = datetime.now()
    if now.hour * 60 + now.minute < REMOTE_FETCH_START_MIN:
        return
    ts = time.time()
    if ts - ST["last_remote_fetch"] < REMOTE_FETCH_SEC:
        return
    ST["last_remote_fetch"] = ts
    try:
        import urllib.request
    except Exception:
        log("[FETCH] urllib import fail")
        return
    if not os.path.isdir(SCORE_DIR):
        try:
            os.makedirs(SCORE_DIR)
        except Exception as e:
            log("[FETCH] cannot create score_dir " + SCORE_DIR +
                ": " + str(e)[:80])
            return
    fpath = os.path.join(SCORE_DIR, today + ".fullpool.json")
    if os.path.exists(fpath) and os.path.getsize(fpath) > 0:
        return
    url = REMOTE_SCORE_BASE + "/" + today + ".fullpool.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TDX/2.2"})
        with urllib.request.urlopen(req, timeout=REMOTE_TIMEOUT) as resp:
            body = resp.read()
            if not body:
                log("[FETCH] " + url + " empty")
                return
            with open(fpath, "wb") as f:
                f.write(body)
            log("[FETCH] fullpool <- " + url + " (" + str(len(body)) + "b)")
    except Exception as e:
        log("[FETCH] fullpool fail: " + str(e)[:90])


def _fetch_remote_fullpool_live(today):
    """Fetch {date}.fullpool_live.json from server nginx (09:36 rerank).
    Throttled (shared with classic fetch), silent-fail. Only after
    LIVE_FULLPOOL_MIN; classic fullpool is the pre-09:36 fallback."""
    now = datetime.now()
    now_min = now.hour * 60 + now.minute
    if now_min < LIVE_FULLPOOL_MIN:
        return
    ts = time.time()
    if ts - ST["last_remote_fetch"] < REMOTE_FETCH_SEC:
        return
    ST["last_remote_fetch"] = ts
    try:
        import urllib.request
    except Exception:
        log("[FETCH] urllib import fail")
        return
    if not os.path.isdir(SCORE_DIR):
        try:
            os.makedirs(SCORE_DIR)
        except Exception as e:
            log("[FETCH] cannot create score_dir " + SCORE_DIR +
                ": " + str(e)[:80])
            return
    fpath = os.path.join(SCORE_DIR, today + ".fullpool_live.json")
    if os.path.exists(fpath) and os.path.getsize(fpath) > 0:
        return
    url = REMOTE_SCORE_BASE + "/" + today + ".fullpool_live.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TDX/2.2"})
        with urllib.request.urlopen(req, timeout=REMOTE_TIMEOUT) as resp:
            body = resp.read()
            if not body:
                log("[FETCH] live empty")
                return
            with open(fpath, "wb") as f:
                f.write(body)
            log("[FETCH] fullpool_live <- " + url + " (" + str(len(body)) + "b)")
    except Exception as e:
        log("[FETCH] fullpool_live fail: " + str(e)[:90])


def _load_fullpool(today):
    """Track B candidate source:
      < LIVE_FULLPOOL_MIN: {date}.fullpool.json (05:00 full pool).
      >= LIVE_FULLPOOL_MIN: {date}.fullpool_live.json (09:35 server rerank,
      106-d factor + money + research gates), fallback to classic if missing.
    Returns [{"symbol","name","rank","industry_l1","score_0500",
    "main_net_5d", +live: score/money_flow_pass/research_tier/...}, ...]
    Fail -> None (skip this loop, retry next)."""
    now = datetime.now()
    now_min = now.hour * 60 + now.minute
    live_mode = USE_SERVER_GATES and now_min >= LIVE_FULLPOOL_MIN
    if not live_mode:
        return _load_fullpool_classic(today)

    # live pool first, classic fallback
    live = _load_fullpool_file(today, ".fullpool_live.json",
                               _fetch_remote_fullpool_live)
    if live is not None:
        ST["live_pool_active"] = True
        log("[FULLPOOL] LIVE mode n=" + str(len(live)))
        return live
    ST["live_pool_active"] = False
    return _load_fullpool_classic(today)


def _load_fullpool_classic(today):
    """Classic 05:00 fullpool (pre-09:36 fallback path).

    score normalization: prefer server A-arm final score (includes pattern
    breakout and other soft boosts; fullpool.json "score" field since 08-19),
    fall back to raw score_0500 when missing.
    """
    pool = _load_fullpool_file(today, ".fullpool.json", _fetch_remote_fullpool)
    if pool is not None:
        ST["live_pool_active"] = False
        for _it in pool:
            if _it.get("score") is None:
                _it["score"] = _it.get("score_0500")
    return pool


def _load_fullpool_file(today, suffix, fetch_fn):
    """Load {date}{suffix} from local scores dir; fetch remote if missing.
    Returns rows or None. Re-parses each call (ST has no per-date cache)."""
    fpath = os.path.join(SCORE_DIR, today + suffix)
    if not os.path.exists(fpath):
        fetch_fn(today)
        if not os.path.exists(fpath):
            return None
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            d = json.load(f)
        rows = d.get("rows") or []
        if ST.get("last_pool_n") != len(rows):
            ST["last_pool_n"] = len(rows)
            log("[FULLPOOL] " + today + suffix + " n=" + str(len(rows)))
        return rows
    except Exception as e:
        log("[FULLPOOL] parse fail " + fpath + ": " + str(e)[:80])
        try:
            os.remove(fpath)
        except Exception:
            pass
        return None


# ================= POSITION STATE (persist across TDX restarts) =================
def _load_pos_state():
    """Load persisted sell-side metadata keyed by QMT symbol."""
    try:
        if os.path.exists(POS_STATE_FILE):
            with open(POS_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                pos = data.get("positions")
                if isinstance(pos, dict):
                    return pos
                return data
    except Exception:
        pass
    return {}


def _pos_snapshot(pos):
    out = {}
    for k in POS_STATE_PERSIST:
        if k in pos:
            out[k] = pos[k]
    return out


def _merge_pos_state(pos, saved):
    """Merge disk state into a broker-synced position (restart recovery)."""
    if not saved or not isinstance(saved, dict):
        return
    if saved.get("buy_date") and not str(pos.get("buy_date") or "").strip():
        pos["buy_date"] = str(saved["buy_date"])
    try:
        sp = float(saved.get("peak") or 0)
        if sp > float(pos.get("peak") or 0):
            pos["peak"] = sp
    except BaseException:
        pass
    try:
        pc = int(saved.get("peel_count") or 0)
        if pc > int(pos.get("peel_count") or 0):
            pos["peel_count"] = pc
    except BaseException:
        pass
    try:
        ps = float(saved.get("peel_peak_snapshot") or 0)
        if ps > float(pos.get("peel_peak_snapshot") or 0):
            pos["peel_peak_snapshot"] = ps
    except BaseException:
        pass
    for bk in ("t2_extended", "vwap_broken", "wy_bc_armed", "trail_armed",
               "awaiting_new_high"):
        if saved.get(bk):
            pos[bk] = True
    try:
        vr = float(saved.get("vwap_ref") or 0)
        if vr > 0:
            pos["vwap_ref"] = vr
    except BaseException:
        pass
    try:
        eh = int(saved.get("vwap_early_hits") or 0)
        if eh > int(pos.get("vwap_early_hits") or 0):
            pos["vwap_early_hits"] = eh
    except BaseException:
        pass
    try:
        em = int(saved.get("vwap_early_min") or 0)
        if em > 0 and int(pos.get("vwap_early_min") or 0) <= 0:
            pos["vwap_early_min"] = em
    except BaseException:
        pass
    try:
        cp = float(saved.get("cost") or saved.get("buy_price") or 0)
        if cp > 0 and float(pos.get("cost") or 0) <= 0:
            pos["cost"] = cp
    except BaseException:
        pass


def _save_pos_state():
    """Write sell-side metadata for all open holdings."""
    try:
        positions = {}
        for code, pos in (ST.get("positions") or {}).items():
            if int(pos.get("shares") or 0) <= 0:
                continue
            positions[code] = _pos_snapshot(pos)
        payload = {
            "version": 1,
            "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "positions": positions,
        }
        tmp = POS_STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        os.replace(tmp, POS_STATE_FILE)
        ST["pos_state"] = positions
    except Exception as e:
        log("[POS] save err: " + str(e)[:80])


def _fmt_buy_date(bd):
    s = str(bd or "").strip()
    if not s:
        return "?"
    if len(s) >= 8 and s[:8].isdigit():
        s8 = s[:8]
        return s8[0:4] + "-" + s8[4:6] + "-" + s8[6:8]
    return s


def _hold_days_short(pos, today):
    bd = str(pos.get("buy_date") or "")
    if not bd:
        return 999
    try:
        if len(bd) == 8 and bd.isdigit():
            b = datetime.strptime(bd, "%Y%m%d").date()
        else:
            b = datetime.strptime(bd[:10], "%Y-%m-%d").date()
        t = datetime.strptime(today, "%Y%m%d").date()
        return _trading_days_between(b, t)
    except BaseException:
        return 999


def _log_positions(tag):
    today = datetime.now().strftime("%Y%m%d")
    pm = ST.get("positions") or {}
    if not pm:
        log("[" + tag + "] positions: none")
        return
    log("[" + tag + "] positions n=" + str(len(pm)))
    for code in sorted(pm.keys()):
        pos = pm[code]
        hd = _hold_days_short(pos, today)
        hd_s = "?" if hd == 999 else str(hd)
        ext = " ext" if pos.get("t2_extended") else ""
        log("[" + tag + "]   " + code + " " + str(pos.get("name") or "") +
            " " + str(int(pos.get("shares") or 0)) + "sh" +
            " bd=" + _fmt_buy_date(pos.get("buy_date")) +
            " hold=" + hd_s +
            " peel=" + str(int(pos.get("peel_count") or 0)) + ext)


# ================= POSITIONS SYNC =================
def _recover_buy_date(code):
    """Restore buy_date from persisted pos state, then local trade log. TDX sim,
    like QMT, can be restarted after T+1 unlocks: TodayBuyPosition is then 0 and
    the in-memory old entry is gone, so buy_date would fall empty -> _hold_days
    returns 999 -> the 14:45 window force-sells a T+1 winner as if held past
    T2_EXTEND_MAX_DAYS (000651 QMT-SIM on 08-20). Returns %Y%m%d ('' when unknown)."""
    sym = qmt_code(code)
    try:
        saved = (ST.get("pos_state") or {}).get(sym)
        if not saved:
            saved = _load_pos_state().get(sym)
        bd = str((saved or {}).get("buy_date") or "").strip()
        if bd:
            if len(bd) >= 10 and "-" in bd[:10]:
                return bd[:10].replace("-", "")
            return bd
    except BaseException:
        pass
    try:
        for t in reversed(ST["trade_log"] or []):
            if t.get("action") != "BUY":
                continue
            if qmt_code(t.get("symbol")) != sym:
                continue
            ts = str(t.get("time") or "")
            if len(ts) >= 10:
                return ts[:10].replace("-", "")
    except BaseException:
        pass
    return ""


def _today_buy_date(d, old):
    try:
        if float(d.get("TodayBuyPosition") or 0) > 0:
            return datetime.now().strftime("%Y%m%d")
    except Exception:
        pass
    if old and old.get("buy_date"):
        return old.get("buy_date") or ""
    # v1.8 (2026-08-20): old entry missing/empty (restart, or T+1 already
    # unlocked so TodayBuyPosition is 0) -> recover from the trade log so
    # _hold_days never sees an empty date and force-sells a fresh winner.
    return _recover_buy_date(d.get("Code") or "")


def _sync_positions():
    """Refresh ST['positions'] from TDX account (authoritative)."""
    try:
        pos_data = tq.query_stock_positions(account_id=ST["account"])
    except BaseException as e:
        log("[SYNC] query_stock_positions fail: " + repr(e)[:100])
        return
    seen = set()
    new_pos = {}
    if pos_data:
        for item in pos_data:
            try:
                d = _dict_of(item)
                code = qmt_code(d.get("Code") or "")
                if not code:
                    continue
                vol = int(float(d.get("TotalVol") or 0))
                cost = float(d.get("Cbj") or 0)
                if vol <= 0:
                    continue
                seen.add(code)
                old = ST["positions"].get(code)
                saved = (ST.get("pos_state") or {}).get(code)
                if old is None:
                    log("[SYNC] +" + code + " " + str(vol) + "sh cost=" + str(cost) +
                        (" [state]" if saved else ""))
                elif old.get("shares") != vol or abs(old.get("cost", 0) - cost) > 0.001:
                    log("[SYNC] ~" + code + " " + str(vol) + "sh cost=" + str(cost))
                new_pos[code] = {
                    "shares": vol, "cost": cost,
                    "buy_date": _today_buy_date(d, old),
                    "peak": (old or {}).get("peak", cost),
                    "trail_armed": (old or {}).get("trail_armed", False),
                    "awaiting_new_high": (old or {}).get("awaiting_new_high", False),
                    "peel_peak_snapshot": (old or {}).get("peel_peak_snapshot", cost),
                    "peel_count": (old or {}).get("peel_count", 0),
                    "t2_extended": (old or {}).get("t2_extended", False),
                    "vwap_broken": (old or {}).get("vwap_broken", False),
                    "wy_bc_armed": (old or {}).get("wy_bc_armed", False),
                    "today_high": (old or {}).get("today_high", cost),
                    "name": (old or {}).get("name", bare_code(code)),
                }
                _merge_pos_state(new_pos[code], saved)
                if not new_pos[code].get("buy_date"):
                    new_pos[code]["buy_date"] = _recover_buy_date(code)
            except Exception:
                continue
    for code in list(ST["positions"].keys()):
        if code not in seen:
            log("[SYNC] -" + code + " closed")
            ST["positions"].pop(code, None)
    ST["positions"] = new_pos
    log("[SYNC] holdings=" + str(len(new_pos)))
    _save_pos_state()


# ================= Track B: AUCTION GATE =================
def _get_gap_pct(code):
    """Auction gap% = (Open/LastClose - 1)*100 via snapshot Open/LastClose.
    Same caliber as server compute_stock_signals (open/prev_close)."""
    pc = ST["prev_close"].get(code) or _prev_close(code)
    if not pc or pc <= 0:
        return None
    o, _ = _snap_open_high(code)
    if not o or o <= 0:
        return None
    return (o / pc - 1) * 100.0


def _is_sweet_zone(code):
    """True if this candidate's auction gap is in the P2 sweet zone (v1.15)."""
    if SWEET_ZONE_MODE <= 0:
        return False
    g = ST["gap_cache"].get(code)
    if g is None:
        g = _get_gap_pct(code)
    if g is None:
        return False
    return (SWEET_GAP_LO - 1e-9) <= g <= (SWEET_GAP_HI + 1e-9)


def _order_by_sweet(items):
    """Trigger-order preference (v1.15): sweet-zone candidates first within
    their tier (money_pass first / fallback). SWEET_ZONE_MODE=1 sorts (sweet
    first, others keep original order); =2 keeps only sweet-zone names."""
    if SWEET_ZONE_MODE <= 0:
        return items
    if SWEET_ZONE_MODE == 2:
        kept = [it for it in items if _is_sweet_zone(it["code"])]
        for it in items:
            if it["code"] not in [x["code"] for x in kept]:
                log("[SWEET] " + it["code"] + " not in sweet zone, skip (mode=2)")
        return kept
    tier = []
    rest = []
    for it in items:
        if _is_sweet_zone(it["code"]):
            tier.append(it)
        else:
            rest.append(it)
    return tier + rest


def _get_active_buy_ratio(code):
    """Active-buy ratio approx (TDX has no per-tick): snapshot order-book
    ratio Buy1Vol/(Buy1Vol+Sell1Vol). Field-name candidates checked because
    TDX snapshot keys vary across versions. Continuous-session only
    (after 09:30). Unavailable -> None (soft signal, never hard-block)."""
    s = _snap(code)
    if s is None:
        return None
    try:
        bv = None
        sv = None
        for k in ("Buy1Vol", "BuyVol", "Bid1Vol", "BidVol"):
            v = s.get(k)
            if v:
                bv = float(v)
                break
        for k in ("Sell1Vol", "SellVol", "Ask1Vol", "AskVol"):
            v = s.get(k)
            if v:
                sv = float(v)
                break
        if bv is None or sv is None:
            return None
        if bv <= 0 and sv <= 0:
            return None
        return bv / (bv + sv)
    except (TypeError, ValueError):
        return None


def _get_turnover(code):
    """Daily turnover % = today's cum volume / float shares. Fail -> None."""
    s = _snap(code)
    if s is not None:
        try:
            vol_hands = _f(s, "Volume", default=None)
            if vol_hands and vol_hands > 0:
                cum_vol = vol_hands * 100.0  # hands -> shares
                fs = _float_shares(code)
                if fs and fs > 0:
                    return cum_vol / fs * 100.0
        except BaseException:
            pass
    try:
        df = _get_md(["volume"], [code], "1d", 1)
        arr = _md_series(df, "volume", code)
        if arr is None or len(arr) == 0:
            return None
        cum_vol = float(arr.iloc[-1])
        if cum_vol <= 0:
            return None
        fs = _float_shares(code)
        if not fs or fs <= 0:
            return None
        return cum_vol / fs * 100.0
    except BaseException:
        return None


def _float_shares(code):
    try:
        info = _dict_of(tq.get_stock_info(stock_code=code))
    except BaseException:
        return None
    for k in ("ActiveCapital", "FloatShares", "FloatShare", "Ltgb", "Ltsz", "FloatCap"):
        v = info.get(k)
        if v:
            try:
                fs = float(v)
                if fs <= 0:
                    continue
                if fs < 1e7:
                    fs = fs * 1e4
                return fs
            except Exception:
                continue
    return None


def _get_volume_ratio(code):
    """Volume ratio = today cum vol (up to now) / prior 5d same-time cum vol
    mean. Same-time alignment avoids the 09:35 structural under-count of the
    old 'snapshot / prior 5d FULL-DAY mean' formula (which can never reach
    MIN_VOL_RATIO at 09:35). Groups 5m bars by real date via the pandas index.
    None on fail (P2 treats None as soft-skip)."""
    now = datetime.now()
    now_min = now.hour * 60 + now.minute
    today_str = now.strftime("%Y-%m-%d")
    try:
        df = _get_md(["volume"], [code], "5m", 288)
        arr = _md_series(df, "volume", code)
        if arr is None or len(arr) == 0:
            return None
        idx = arr.index
        day_bars = {}
        for i in range(len(arr)):
            t = idx[i]
            d = t.strftime("%Y-%m-%d")
            day_bars.setdefault(d, []).append(
                (int(t.hour) * 60 + int(t.minute), float(arr.iloc[i])))
        today = day_bars.pop(today_str, None)
        if today is None or not today:
            return None
        cur = sum(v for _tm, v in today)
        if cur <= 0:
            return None
        base_list = []
        for d, bars in sorted(day_bars.items())[-5:]:
            same = [v for tm, v in bars if tm <= now_min]
            s = sum(same)
            if s > 0:
                base_list.append(s)
        if not base_list:
            return None
        base = sum(base_list) / max(len(base_list), 1)
        if base <= 0:
            return None
        return cur / base
    except BaseException:
        return None


def _get_daily_change(code):
    """Daily change% = (Now/LastClose - 1)*100. None on fail."""
    pc = ST["prev_close"].get(code) or _prev_close(code)
    if not pc or pc <= 0:
        return None
    price = _last_price(code)
    if not price or price <= 0:
        return None
    return (price / pc - 1) * 100.0


def _aggregate_sector(pool, now_min=0):
    """Aggregate candidate gaps by industry_l1. TDX has no reliable sector
    member API, so aggregate within the pool itself (the pool spans many
    sectors, keeps full-pool sample avoiding n=1 distortion).
    gap results are cached into ST['gap_cache'] (honoring CALL_DATA_CUTOFF
    like _p1_gate) so repeated gate cycles never re-quote the same stock."""
    sector_gap = {}
    for it in pool:
        sec = it.get("industry_l1") or "Other"
        code = qmt_code(it.get("symbol"))
        if not code:
            continue
        g = ST["gap_cache"].get(code)
        if g is None:
            g = _get_gap_pct(code)
            if g is not None and now_min <= CALL_DATA_CUTOFF:
                ST["gap_cache"][code] = g
        if g is None:
            continue
        sector_gap.setdefault(sec, []).append(g)
    out = {}
    for sec, gaps in sector_gap.items():
        out[sec] = sum(gaps) / len(gaps)
    ST["sector_gap_mean"] = out
    return out


def _p1_gate(pool, now_min):
    """P1 auction gate (09:25-09:30). Aligns server pre_market_gate.py.
    Returns survivors, sorted by adj_score desc, capped P1_KEEP_TOP_N."""
    survivors = []
    sector_gap = _aggregate_sector(pool, now_min)
    for it in pool:
        sym = it.get("symbol")
        code = qmt_code(sym)
        if not code:
            continue
        if code in ST["positions"]:
            continue
        if not _board_allowed(code):
            continue
        if _is_st_name(it.get("name")):
            log("[ST] " + code + " " + str(it.get("name")) + " skip (risk-warning)")
            continue
        g = ST["gap_cache"].get(code)
        if g is None:
            g = _get_gap_pct(code)
            if g is not None and now_min <= CALL_DATA_CUTOFF:
                ST["gap_cache"][code] = g
        if g is None:
            base = float(it.get("score") if it.get("score") is not None
                         else it.get("score_0500") or 0)
            survivors.append({
                "code": code, "symbol": sym, "name": it.get("name") or "",
                "rank": int(it.get("rank") or 0),
                "industry_l1": it.get("industry_l1") or "Other",
                "score_0500": base, "gap_pct": None,
                "adj_score": round(base * 0.95, 4), "action": "no_data",
            })
            continue
        sec = it.get("industry_l1") or "Other"
        sector_weak = (sector_gap.get(sec, 0) < SECTOR_WEAK_THRESHOLD
                       if sec in sector_gap else False)
        base = float(it.get("score") if it.get("score") is not None
                     else it.get("score_0500") or 0)
        if g >= GAP_LIMIT_UP:
            continue
        if g < 0 and sector_weak:
            continue
        if g < GAP_DEMOTE:
            penalty = max(0.05, min(0.35, abs(g) * 0.13))
            adj = base * (1 - penalty)
            survivors.append({
                "code": code, "symbol": sym, "name": it.get("name") or "",
                "rank": int(it.get("rank") or 0),
                "industry_l1": sec, "score_0500": base,
                "gap_pct": round(g, 2),
                "adj_score": round(max(0, adj), 4), "action": "demoted",
            })
            continue
        if g >= 2.0:
            bonus = 0.06
        elif g >= 0.5:
            bonus = 0.03
        elif g >= 0:
            bonus = 0.01
        else:
            bonus = 0.0
        sector_penalty = 0.03 if sector_weak else 0.0
        total_adj = bonus - sector_penalty
        adj = base * (1 + total_adj)
        survivors.append({
            "code": code, "symbol": sym, "name": it.get("name") or "",
            "rank": int(it.get("rank") or 0),
            "industry_l1": sec, "score_0500": base,
            "gap_pct": round(g, 2),
            "adj_score": round(max(0, adj), 4), "action": "kept",
        })

    survivors.sort(key=lambda x: -x["adj_score"])
    kept = []
    cnt = {}
    for it in survivors:
        sec = it.get("industry_l1") or "Other"
        rank = len(kept) + 1
        if rank <= 10:
            limit = MAX_SAME_SECTOR_IN_TOP10
        elif rank <= 20:
            limit = MAX_SAME_SECTOR_IN_TOP20
        else:
            limit = MAX_SAME_SECTOR_IN_POOL
        if cnt.get(sec, 0) >= limit:
            continue
        kept.append(it)
        cnt[sec] = cnt.get(sec, 0) + 1
    kept = kept[:P1_KEEP_TOP_N]
    ST["p1_survivors"] = kept
    return kept


def _live_pool_survivors(pool):
    """Map server fullpool_live rows to Track B internal survivor items.

    Server already applied the full 106-d factor + money + research gates and
    sorted money_flow_pass first. We trust that ordering (plus sector
    diversity already applied server-side by live_momentum_scanner)."""
    out = []
    for it in pool:
        sym = it.get("symbol")
        code = qmt_code(sym)
        if not code:
            continue
        if not _board_allowed(code):
            continue
        if _is_st_name(it.get("name")):
            log("[ST] " + code + " " + str(it.get("name")) + " skip (risk-warning)")
            continue
        sc = it.get("score")
        if sc is None:
            sc = it.get("score_0500") or 0.0
        out.append({
            "code": code,
            "symbol": sym,
            "name": it.get("name") or "",
            "rank": int(it.get("rank") or 0),
            "industry_l1": it.get("industry_l1") or "Other",
            "score_0500": float(sc),
            "score": float(sc),
            "money_flow_pass": bool(it.get("money_flow_pass")),
            "research_tier": it.get("research_tier"),
            "main_net": float(it.get("main_net") or 0),
            "main_net_5d": float(it.get("main_net_5d") or 0),
            "main_net_3d": float(it.get("main_net_3d") or 0),
            "main_net_10d": float(it.get("main_net_10d") or 0),
            "super_large_net": float(it.get("super_large_net") or 0),
            "large_net": float(it.get("large_net") or 0),
            "mid_net": float(it.get("mid_net") or 0),
            "small_net": float(it.get("small_net") or 0),
            "fund_rank": float(it.get("fund_rank") or 0),
            "money_phase": it.get("money_phase"),
            "active_buy_ratio": it.get("active_buy_ratio"),
            "fund_hard_fail": bool(it.get("fund_hard_fail")),
            "action": "kept",
        })
    return out


def _fallback_buy_ok(it, now_min):
    """Fallback rank/quality gate. Returns (allowed, abandon_today)."""
    if it.get("money_pass"):
        return True, False
    rank = int(it.get("rank") or 0)
    if rank <= 0:
        return False, True
    if FALLBACK_SKIP_HARD_FAIL and it.get("fund_hard_fail"):
        return False, True
    if rank > FALLBACK_RANK_CAP_PM:
        return False, True
    cap = (FALLBACK_RANK_CAP_AM if now_min < FALLBACK_RANK_OPEN_MIN
           else FALLBACK_RANK_CAP_PM)
    if rank > cap:
        return False, False
    return True, False


def _p2_gate(survivors, now_min):
    """P2 money gate (09:30-09:35). Aligns server money_flow_gate.py.
    TDX snapshot-field approximation; metrics unavailable are skipped
    (soft gate). Returns sorted by (money_pass desc, score_0500 desc).

    Live-pool mode (ST.live_pool_active, 09:36 server rerank): each candidate
    carries the server-computed full 106-d factor + money + research gate
    result (money_flow_pass / research_tier / score = 0.6*pipeline + 0.4*
    live momentum z). We trust those gates directly (that is the point of the
    live pool - TDX-side can't re-run the 106-d pipeline) and only keep the
    TDX-side real-time ABR as a soft re-check. The P2 dynamic confirm
    (_p2_decide) still runs per-candidate in _check_buy as the final trigger.

    Classic-pool mode (pre-09:36 fallback): compute TDX-side gates as before.
    """
    out = []
    live_mode = bool(ST.get("live_pool_active")) and USE_SERVER_GATES
    for it in survivors:
        code = it["code"]
        is_live_row = "money_flow_pass" in it or it.get("score") is not None
        if live_mode and is_live_row:
            # server 106-d factor + money + research gates already applied
            money_pass = bool(it.get("money_flow_pass"))
            notes = []
            if money_pass:
                notes.append("srv_pass")
            else:
                notes.append("srv_fail")
            tier = it.get("research_tier")
            if tier:
                notes.append("tier=" + str(tier))
            # soft real-time ABR re-check (never a hard veto: server covered it)
            if now_min >= GATE_START_MIN:
                abr = _get_active_buy_ratio(code)
                if abr is not None:
                    it["active_buy_ratio"] = round(abr, 4)
                else:
                    it["active_buy_ratio"] = it.get("active_buy_ratio")
            # soft retail-chase / main-outflow flags (layered nets from server;
            # never a hard veto - only a sort penalty so honest money wins)
            mnet = float(it.get("main_net") or 0)
            snet = float(it.get("small_net") or 0)
            if mnet < -3e7:
                it["live_main_out"] = True
                notes.append("main_out")
            if mnet < 0 and snet > 0 and snet > abs(mnet) * 0.15:
                it["live_retail_chase"] = True
                notes.append("retail_chase")
            it["money_pass"] = bool(money_pass)
            it["gate_notes"] = ";".join(notes)
            out.append(it)
            continue
        money_pass = True
        notes = []
        if now_min >= GATE_START_MIN:
            abr = _get_active_buy_ratio(code)
            if abr is not None:
                it["active_buy_ratio"] = round(abr, 4)
                if abr < MIN_ACTIVE_BUY:
                    money_pass = False
                    notes.append("abr<%.2f" % MIN_ACTIVE_BUY)
            else:
                it["active_buy_ratio"] = None
        to = _get_turnover(code)
        if to is not None:
            it["turnover"] = round(to, 2)
            if not (MIN_TURNOVER <= to <= MAX_TURNOVER):
                money_pass = False
                notes.append("to=%s" % round(to, 2))
        vr = _get_volume_ratio(code)
        if vr is not None:
            it["volume_ratio"] = round(vr, 2)
            if vr < MIN_VOL_RATIO:
                money_pass = False
                notes.append("vr<%.2f" % MIN_VOL_RATIO)
        chg = _get_daily_change(code)
        if chg is not None:
            it["change_pct"] = round(chg, 2)
            if chg < MAX_DROP_PCT:
                money_pass = False
                notes.append("chg<%.1f" % MAX_DROP_PCT)
        m5 = float(it.get("main_net_5d") or 0)
        it["main_net_5d"] = round(m5, 2)
        it["money_pass"] = bool(money_pass)
        it["gate_notes"] = ";".join(notes)
        out.append(it)
    out.sort(key=lambda x: (not x.get("money_pass"), 1 if x.get("live_retail_chase") else 0, -x["score_0500"]))
    return out


def _dump_gate(today, pool, p1, p2):
    try:
        data = {
            "date": today,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "pool_n": len(pool),
            "p1_n": len(p1),
            "p2_top10": [{
                "code": x.get("code"), "name": x.get("name"),
                "score": x.get("score_0500"), "gap": x.get("gap_pct"),
                "action": x.get("action"), "pass": x.get("money_pass"),
                "notes": x.get("gate_notes"),
            } for x in p2[:10]],
        }
        with open(GATE_LOG, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        log("[GATE] dump " + today + " pool=" + str(len(pool)) +
            " p1=" + str(len(p1)) + " top=" + str(len(p2)))
    except BaseException:
        pass



def _vwap_clear_early(pos):
    pos["vwap_broken"] = False
    pos["vwap_ref"] = 0
    pos["vwap_early_hits"] = 0
    pos["vwap_early_min"] = 0


def _vwap_morning_decide(pos, price, now_min):
    """First still-below tick in 09:35-09:50 only arms. Later minute sells.

    Same-minute re-polls stay wait (QMT/TDX tick every few seconds).
    Price back at/above vwap_ref cancels the signal.
    """
    vref = float(pos.get("vwap_ref") or 0)
    if vref > 0 and price >= vref:
        _vwap_clear_early(pos)
        return "recover"
    hits = int(pos.get("vwap_early_hits") or 0)
    first_min = int(pos.get("vwap_early_min") or 0)
    if hits < 1:
        pos["vwap_early_hits"] = 1
        pos["vwap_early_min"] = int(now_min)
        return "wait1"
    if int(now_min) <= first_min:
        return "wait"
    return "sell"


# ================= SELL (same as Track A TDX v2.10) =================
def _is_limit_down(price, prev_close):
    if not prev_close or prev_close <= 0:
        return False
    chg = (price / prev_close - 1) * 100
    return chg <= LIMIT_DOWN_PCT


def _do_sell(code, pos, price, reason):
    vol = int(pos.get("shares") or 0)
    if vol <= 0 or vol > 999999:
        return
    today = datetime.now().strftime("%Y%m%d")
    lockk = _sell_lock_key(reason)
    if _order_locked(today, code, lockk):
        log("[LOCK] skip sell " + code + " " + lockk +
            " (already ordered today)")
        return
    log("[SELL] " + code + " " + reason + " all " + str(vol) +
        "sh @ " + str(round(price, 2)))
    try:
        tq.order_stock(
            account_id=ST["account"], stock_code=code,
            order_type=tqconst.STOCK_SELL, order_volume=vol,
            price_type=tqconst.PRICE_MY, price=price)
        _mark_order_locked(today, code, lockk)
    except BaseException as e:
        log("[SELL] order fail: " + repr(e)[:100])
    _log_trade("SELL", code, price, vol, reason)
    ST["positions"].pop(code, None)
    _save_pos_state()


def _do_sell_half(code, pos, price, reason):
    shares = int(pos.get("shares") or 0)
    half = max(100, (shares // 2 // 100) * 100)
    if half <= 0 or half >= shares:
        _do_sell(code, pos, price, reason + " (half>=all)")
        return
    today = datetime.now().strftime("%Y%m%d")
    lockk = _sell_lock_key(reason)
    if _order_locked(today, code, lockk):
        log("[LOCK] skip sell-half " + code + " " + lockk +
            " (already ordered today)")
        return
    log("[SELL] " + code + " " + reason + " half " + str(half) +
        "sh @ " + str(round(price, 2)))
    try:
        tq.order_stock(
            account_id=ST["account"], stock_code=code,
            order_type=tqconst.STOCK_SELL, order_volume=half,
            price_type=tqconst.PRICE_MY, price=price)
        _mark_order_locked(today, code, lockk)
    except BaseException as e:
        log("[SELL] order fail: " + repr(e)[:100])
    pos["shares"] = shares - half
    _log_trade("SELL_HALF", code, price, half, reason)
    _save_pos_state()


def _check_sell(now, now_min, today):
    for code, pos in list(ST["positions"].items()):
        shares = int(pos.get("shares") or 0)
        if shares <= 0:
            continue
        cost = float(pos.get("cost") or 0)
        if cost <= 0:
            continue
        price = _last_price(code)
        if not price or price <= 0:
            continue
        prev_close = ST["prev_close"].get(code) or _prev_close(code)
        if prev_close:
            ST["prev_close"][code] = prev_close

        if price > float(pos.get("today_high") or 0):
            pos["today_high"] = price
        if price > float(pos.get("peak") or cost):
            pos["peak"] = price

        ret = (price / cost - 1) * 100
        daily = (price / prev_close - 1) * 100 if prev_close and prev_close > 0 else 0.0

        if daily <= ANOMALY_PCT:
            log("[WARN] " + code + " daily=" + str(round(daily, 1)) +
                "% anomaly, hold")
            continue
        if daily <= LIMIT_DOWN_PCT:
            _do_sell(code, pos, price,
                     "limit_down daily=" + str(round(daily, 1)) + "%")
            continue

        bd = str(pos.get("buy_date") or "")
        is_today_buy = (bd == today)
        if is_today_buy:
            continue  # T+1

        if (not pos.get("wy_bc_armed") and now_min >= VWAP_CONFIRM_MIN and
                _wyckoff_holding_bc(code, pos.get("peak", cost))):
            pos["wy_bc_armed"] = True
            log("[BC] " + code + " holding buy-climax px=" +
                str(round(price, 2)) + " peak=" +
                str(round(pos.get("peak", 0), 2)))
        if pos.get("wy_bc_armed") and VWAP_SELL_START <= now_min <= VWAP_SELL_END:
            _do_sell(code, pos, price, "wyckoff_bc " +
                     str(round(ret, 1)) + "%")
            continue

        if not pos.get("vwap_broken") and now_min >= VWAP_CONFIRM_MIN:
            vw = _day_vwap(code)
            if vw and vw > 0 and price < vw:
                pos["vwap_broken"] = True
                pos["vwap_ref"] = vw
                log("[VWAP] " + code + " day-vwap broken px=" +
                    str(round(price, 2)) + " vwap=" + str(round(vw, 2)) +
                    " ret=" + str(round(ret, 1)) + "%")
        # v1.16: next-morning confirm. Unconditional next-open sell sold the
        # day's low on all 3 real triggers (QMT sim 08-31). Sell only if the
        # live price is still below the recorded reference; recover -> cancel.
        if pos.get("vwap_broken") and VWAP_SELL_START <= now_min <= VWAP_SELL_END:
            vref = float(pos.get("vwap_ref") or 0)
            decision = _vwap_morning_decide(pos, price, now_min)
            if decision == "recover":
                log("[VWAP] " + code + " recovered px=" +
                    str(round(price, 2)) + " ref=" + str(round(vref, 2)) +
                    " cancel weak-early")
            elif decision == "wait1":
                log("[VWAP] " + code + " first confirm wait 2nd px=" +
                    str(round(price, 2)) + " ref=" + str(round(vref, 2)))
            elif decision == "sell":
                _do_sell(code, pos, price, "vwap_weak_early " +
                         str(round(ret, 1)) + "%")
                continue

        hs, ta, pb = _adaptive_params(code)

        if now_min >= T2_FORCE_MIN and ret <= hs * 100:
            _do_sell(code, pos, price,
                     "hard_stop " + str(round(ret, 1)) + "% vs " +
                     str(round(hs * 100, 1)) + "%")
            continue

        if now_min >= T2_FORCE_MIN:
            hold_days = _hold_days(pos, today)
            if pos.get("t2_extended"):
                # already extended: force-sell at maturity (hold_days >= T2_EXTEND_MAX_DAYS)
                # only. v1.7 fix: the old code sold on the very next 14:45 pass, so
                # T2_EXTEND_MAX_DAYS=3 bought just 1 extra day instead of the intended
                # T+3. Inside the window the position keeps running with the trailing
                # peel / vwap_weak_early / wyckoff_bc exits still armed.
                # v1.8 (2026-08-20): hold_days == 999 (buy_date unknown) must not
                # be read as past maturity and force-sell a fresh winner.
                if hold_days != 999 and hold_days >= T2_EXTEND_MAX_DAYS:
                    _do_sell(code, pos, price,
                             "t2_force_after_extend " + str(round(ret, 1)) + "%")
                    continue
            else:
                # v1.6: dynamic floor instead of fixed 0%. A wide-amplitude / high-vol
                # name tolerates a deeper normal pullback (300591 08-19: filled 8.54
                # on a 7.88 trigger -> -8.7% vs cost but -1% from trigger; the fixed
                # 0% floor force-sold it next day at 14:45). Floor widens with the
                # day's range and annual vol; hard_stop (hs) still owns the tail.
                force_floor = _t2_force_floor(code) * 100
                if ret < force_floor:
                    # loss beyond the dynamic floor -> force sell
                    _do_sell(code, pos, price,
                             "t2_force " + str(round(ret, 1)) + "% floor=" +
                             str(round(force_floor, 1)) + "%")
                    continue
                # v1.7 (2026-08-19): do NOT let vwap_broken / wy_bc_armed short-circuit
                # the dynamic floor. Both are NEXT-MORNING (09:35-09:50) exit signals:
                # 300591 08-19 fair-cost -1.0% was force-sold only because vwap_broken
                # set in the same 14:45 pass (price 7.80 < vwap 8.05) hit this branch
                # before the floor (-4.45%) could hold it. After extension the T+3
                # morning window fires vwap_weak_early / wyckoff_bc. Only hold-cap and
                # hard-stop refuse to extend.
                # v1.8 (2026-08-20): hold_days == 999 (buy_date unknown) must not
                # be read as "past maturity" and force-sell a fresh winner; only
                # the true hold-cap or a hard-stop loss can end it.
                if ((hold_days != 999 and hold_days >= T2_EXTEND_MAX_DAYS)
                        or ret <= hs * 100):
                    _do_sell(code, pos, price,
                             "t2_force_after_extend " + str(round(ret, 1)) + "%")
                    continue
                pos["t2_extended"] = True
                log("[EXT] " + code + " extend px=" + str(round(price, 2)) +
                    " cost=" + str(round(cost, 2)) +
                    " ret=" + str(round(ret, 1)) + "% hold_days=" + str(hold_days))

        if ret >= ta * 100:
            pos["trail_armed"] = True
        elif ret < 0:
            pos["trail_armed"] = False
            pos["awaiting_new_high"] = False

        if (pos.get("trail_armed") and not pos.get("awaiting_new_high")
                and now_min >= 9 * 60 + 31):
            peak = float(pos.get("peak") or cost)
            pbk = (peak - price) / peak * 100 if peak > 0 else 0.0
            if pbk >= pb * 100:
                n = int(pos.get("peel_count") or 0)
                if n >= PEEL_MAX_STEPS or shares < 200:
                    _do_sell(code, pos, price,
                             "peel_clear pk=" + str(round(peak, 2)) +
                             " pb=" + str(round(pbk, 1)) + "%")
                    continue
                _do_sell_half(code, pos, price,
                              "peel_half" + str(n + 1) +
                              " pk=" + str(round(peak, 2)) +
                              " pb=" + str(round(pbk, 1)) + "%")
                pos["peel_count"] = n + 1
                pos["awaiting_new_high"] = True

        if (pos.get("awaiting_new_high") and
                pos.get("peak", 0) > pos.get("peel_peak_snapshot", 0) + 1e-9):
            pos["awaiting_new_high"] = False
    _save_pos_state()


# ============ Sell-side rework v1.5: T+2 conditional + dynamic weakness rotation (2026-08-18) ============
def _hold_days(pos, today):
    """Holding days from buy_date -> today (buy day excluded). buy_date is %Y%m%d
    (e.g. 20260818). Compatible with 'YYYY-MM-DD'. 999 on missing/unparseable.
    v1.17: counts TRADING days (weekends + 2026 A-share closures excluded),
    so a Friday buy is T+1 on Monday, not hold=3 (see _trading_days_between)."""
    bd = str(pos.get("buy_date") or "")
    if not bd:
        return 999
    try:
        if len(bd) == 8 and bd.isdigit():
            b = datetime.strptime(bd, "%Y%m%d").date()
        else:
            b = datetime.strptime(bd, "%Y-%m-%d").date()
        t = datetime.strptime(today, "%Y%m%d").date()
        return _trading_days_between(b, t)
    except BaseException:
        return 999


def _closed_5m_bars(now_min):
    """Number of 5m bars already closed today (A-share 09:30-11:30/13:00-15:00,
    bar time = closing minute, first bar 09:35). 0 before 09:35."""
    if now_min <= 9 * 60 + 30:
        return 0
    if now_min <= 11 * 60 + 30:          # 09:35..11:30
        return (now_min - (9 * 60 + 35)) // 5 + 1
    if now_min < 13 * 60 + 5:            # lunch -> full morning
        return 24
    if now_min <= 15 * 60:               # 13:05..15:00
        return 24 + (now_min - (13 * 60 + 5)) // 5 + 1
    return 48


def _weakness_score(today):
    """Weakness score 0~1 per holding, higher = more likely to sell. Only
    sellable positions are scored (not pending, held >= ROTATION_MIN_HOLD_DAYS).
    Relative-rank normalized (0~1) + momentum guard (daily > 3% and rising vol
    -> skip). Returns (all_cands_sorted, sellable)."""
    cands = []
    for c, p in list(ST["positions"].items()):
        if p.get("pending"):
            continue
        if _hold_days(p, today) < ROTATION_MIN_HOLD_DAYS:
            continue
        price = _last_price(c)
        if not price or price <= 0 or float(p.get("cost") or 0) <= 0:
            continue
        pc2 = ST["prev_close"].get(c) or _prev_close(c)
        pret = (price / float(p["cost"]) - 1) * 100
        pday = (price / pc2 - 1) * 100 if pc2 and pc2 > 0 else 0.0
        vw = _day_vwap(c)
        vwap_break = 1.0 if (vw and price < vw) else 0.0
        early = 1.0 if (p.get("wy_bc_armed") or p.get("vwap_broken")) else 0.0
        peel = 1.0 if (p.get("peel_count") or 0) > 0 else 0.0
        days = _hold_days(p, today)
        cands.append({
            "code": c, "pos": p, "ret": pret, "day": pday,
            "vwap_break": vwap_break, "early": early, "peel": peel,
            "days": days, "skip": False,
        })
    if not cands:
        return [], []
    # momentum guard: daily > ROTATION_MOMENTUM_DROP_PCT and vol-ratio above threshold -> skip
    for it in cands:
        vr = _get_volume_ratio(it["code"])
        if (it["day"] > ROTATION_MOMENTUM_DROP_PCT and
                (vr or 0) > ROTATION_MOMENTUM_VOL_RATIO):
            it["skip"] = True

    def _rank01(vals, invert=False):
        """Rank values ascending to 0~1; invert=True flips (big value = high weak score).
        Enumerate sorted positions, not the raw list order, so duplicate values
        do not get an arbitrary rank that could mis-score a strong name."""
        s = sorted(vals)
        n = len(s)
        out = {}
        for i, v in enumerate(s):
            r = i / (n - 1) if n > 1 else 0.5
            out[v] = r if not invert else 1.0 - r
        return out

    ret_map = _rank01([it["ret"] for it in cands], invert=True)
    day_map = _rank01([it["day"] for it in cands], invert=True)
    days_map = _rank01([it["days"] for it in cands])
    for it in cands:
        it["score"] = (
            W_WEAK_RET * ret_map[it["ret"]] +
            W_WEAK_VWAP * it["vwap_break"] +
            W_WEAK_DAY * day_map[it["day"]] +
            W_WEAK_EARLY * it["early"] +
            W_WEAK_PEEL * (1.0 - it["peel"]) +
            W_WEAK_DAYS * days_map[it["days"]]
        )
    cands.sort(key=lambda x: -x["score"])
    return cands, [it for it in cands if not it["skip"]]


def _rotation_sell(now, now_min, today, need_n):
    """When holdings are full (MAX_HOLDINGS) and a new candidate passed P2, sell the
    weakest position to free a slot. Prefers peel half (when profitable), else
    full sell. Returns the codes actually sold. _do_sell/_do_sell_half pop
    ST["positions"] on success, so the caller can buy immediately after."""
    if not ROTATION_ENABLE:
        return []
    if _order_locked(today, "__ROT__", "rot"):
        log("[ROT] daily cap " + str(ROTATION_DAILY_MAX) +
            " reached, skip")
        return []
    cands, sellable = _weakness_score(today)
    if not sellable:
        log("[ROT] no sellable holdings (min_hold=" +
            str(ROTATION_MIN_HOLD_DAYS) + ")")
        return []
    w = sellable[0]
    if (ROTATION_WEAK_GATE and not
            (w["day"] < 0 or w["vwap_break"] == 1.0
             or w["early"] == 1.0 or w["ret"] < 0)):
        log("[ROT] skip: weakest " + w["code"] +
            " still healthy (no weakness signal), no churn")
        return []
    sold = []
    for it in sellable[:need_n]:
        code = it["code"]
        if code in ST["positions"] and not ST["positions"][code].get("pending"):
            price = _last_price(code)
            pos = ST["positions"][code]
            ret = (price / float(pos["cost"]) - 1) * 100 if price else 0
            if (ret > 0 and (pos.get("peel_count") or 0) < PEEL_MAX_STEPS
                    and int(pos.get("shares") or 0) >= 400):
                _do_sell_half(code, pos, price,
                              "rotation_peel ret=" + str(round(ret, 1)) + "%")
            else:
                _do_sell(code, pos, price,
                         "rotation_sell ret=" + str(round(ret, 1)) + "%")
            sold.append(code)
            _mark_order_locked(today, "__ROT__", "rot")
            log("[ROT] sell " + code + " weakness=" +
                str(round(it.get("score", 0), 2)))
    return sold


# ================= BUY (Track B: 09:35 Top2 order) =================
def _is_limit_up(code, prev_close):
    if not prev_close or prev_close <= 0:
        return False
    price = _last_price(code)
    if not price:
        return False
    return (price / prev_close - 1) >= 0.095


def _board_allowed(code):
    """Board permission filter. Unknown prefixes allowed."""
    c = "".join(ch for ch in str(code or "").split(".")[0] if ch.isdigit())
    if not c:
        return True
    if c.startswith(("300", "301")):
        return ALLOW_CHINEXT
    if c.startswith(("688", "689")):
        return ALLOW_STAR
    if c.startswith(("8", "4", "920")):
        return ALLOW_BSE
    return True


def _is_st_name(name):
    """ST/退市风险警示判断（TDX 客户端二次防护，2026-08-25 事故）。
    ST / *ST / S*ST / 退市整理 一律视为禁止买入。名称缺失不误杀。"""
    n = str(name or "").strip().upper()
    if not n:
        return False
    return "ST" in n or n.startswith("退") or "退市" in n


def _p2_max_gap(code):
    """Board-aware no-chase: main 6%%, ChiNext/STAR 10%%, BSE 12%%."""
    raw = str(code or "").split(".")[0]
    c6 = "".join(ch for ch in raw if ch.isdigit()).zfill(6)
    if c6.startswith(("688", "689", "300", "301")):
        return 0.10
    if c6.startswith(("8", "4", "920")):
        return 0.12
    return 0.06


def _p2_day_high_ok(c, day_high, day_low):
    rng = day_high - day_low
    if rng <= 0:
        return True
    return (c - day_low) / rng <= CONF_DAY_HIGH_MAX


def _p2_decide(code, now_min):
    """P2 dynamic confirmation (same as TDX v2.10: 5m bars full version,
    snapshot fallback)."""
    prev_close = ST["prev_close"].get(code) or _prev_close(code)
    if not prev_close:
        ST["prev_close"][code] = prev_close or 0
        return None, "no_quote"
    price = _last_price(code)
    if not price or price <= 0:
        return None, "no_quote"

    if now_min > CONF_END_MIN:
        return None, "no_confirm_eod"
    if now_min < CONF_START_MIN:
        return None, "wait_confirm"

    _to = _get_turnover(code)
    if _to is not None and _to > CONF_MAX_TURNOVER:
        return None, "skip_high_turnover"

    bars = _get_m5_bars(code)
    if bars is not None:
        today_bars = [b for b in bars if b[0] >= CONF_START_MIN]
        if today_bars:
            amt_cum = 0.0
            vol_cum = 0.0
            vols = [b[5] for b in today_bars]
            day_high = float(today_bars[0][3])
            day_low = float(today_bars[0][4])
            trig_px = None
            gap_lim = _p2_max_gap(code)
            for i, (tmin, o, c, h, l, v) in enumerate(today_bars):
                is_last = (i == len(today_bars) - 1)
                if not is_last and tmin > now_min:
                    break
                if h > day_high:
                    day_high = h
                if l < day_low:
                    day_low = l
                amt_cum += (o + c) / 2.0 * v
                vol_cum += v
                vwap = (amt_cum / vol_cum) if vol_cum > 0 else 0.0
                # dynamic trend: climbing from rolling session low (not vs P935/open)
                if not (day_low > 0 and c > day_low and vwap > 0 and c > vwap):
                    continue
                vol_ok = False
                for j in range(max(0, i - 1), i + 1):
                    bv = float(today_bars[j][5])
                    bma = _vol_ma5(vols, j)
                    bret = float(today_bars[j][2] - today_bars[j][1])
                    if bma > 0 and bv > bma * CONF_VOL_RATIO and bret > 0:
                        vol_ok = True
                        break
                if not vol_ok:
                    continue
                if c > prev_close * (1 + gap_lim):
                    continue
                if not _p2_day_high_ok(c, day_high, day_low):
                    continue
                trig_px = c
                break
            if trig_px and trig_px > 0:
                return round(trig_px, 2), "dyn_confirm"
            if now_min >= CONF_END_MIN:
                return None, "no_confirm_eod"
            return None, "wait_confirm"

    s = _snap(code)
    if s is None:
        return None, "no_quote"
    avg = _f(s, "Average", "Avg", default=None)
    before5 = _f(s, "Before5MinNow", default=None)
    if not (price > prev_close and avg and price > avg):
        return None, "wait_confirm"
    if before5 and price < before5:
        return None, "wait_confirm"
    gap_lim = _p2_max_gap(code)
    if price > prev_close * (1 + gap_lim):
        return None, "no_chase"
    hi = _f(s, "High", default=None) or price
    lo = _f(s, "Low", default=None) or price
    if not _p2_day_high_ok(price, hi, lo):
        return None, "skip_day_high"
    return round(price, 2), "snap_confirm"


def _vol_ma5(vols, i):
    s = vols[max(0, i - 4):i + 1]
    return sum(s) / len(s) if s else 0.0


def _query_cash():
    """Return (cash, total_asset) from TDX query_stock_asset."""
    try:
        raw = tq.query_stock_asset(account_id=ST["account"])
        asset = _dict_of(raw)
        if "Value" in asset and isinstance(asset.get("Value"), dict):
            asset = dict(asset["Value"])
        cash = float(asset.get("Cash") or asset.get("Balance") or 0)
        total = float(asset.get("Asset") or asset.get("TotalAssets") or 0)
        if total <= 0:
            total = float(asset.get("MarketValue") or 0) + cash
        if not asset:
            log("[BUY] query_stock_asset returned empty (acct handle=" +
                str(ST["account"]) + ") raw=" + str(raw)[:100])
        return cash, total
    except BaseException as e:
        log("[BUY] query_stock_asset fail: " + repr(e)[:100])
        return 0.0, 0.0


def _check_buy(now, now_min, today, pool):
    if len(ST["positions"]) >= MAX_HOLDINGS:
        return
    cash, total_asset = _query_cash()
    if cash <= 0:
        log("[BUY] skip: cash=" + str(cash))
        return
    if total_asset <= 0:
        total_asset = cash

    today_bought = 0
    try:
        locks = _load_order_locks()
        day = locks.get(today, {})
        today_bought = sum(1 for k, v in day.items() if "BUY" in v)
    except Exception:
        today_bought = 0
    if today_bought >= MAX_DAILY_BUY:
        log("[BUY] today_bought=" + str(today_bought) +
            " >= MAX_DAILY_BUY=" + str(MAX_DAILY_BUY) + " skip all")
        return

    # ---- Track B gate flow ----
    if now_min < AUCTION_START_MIN:
        return
    if ST["top2_fired"]:
        return

    if now_min < CALL_DATA_CUTOFF:
        _p1_gate(pool, now_min)
        return

    # 09:30-09:35: money gate usable but decision happens once at 09:35
    # Live mode (USE_SERVER_GATES): wait until LIVE_FULLPOOL_MIN (09:36) so
    # the server rerank pool has time to publish; classic 09:35 is the
    # pre-09:36 fallback when live mode is off.
    eff_decide = LIVE_FULLPOOL_MIN if USE_SERVER_GATES else DECIDE_MIN
    if now_min < eff_decide:
        return

    # v1.1 (2026-08-17): two intraday buy windows replace the old 09:40 hard
    # cutoff (backtest evidence in CONFIG comment). Before 11:30 and between
    # 13:00-14:00 the buy loop re-runs on every bar; after 14:00 the day is
    # closed for buying (tail triggers have the worst T+1).
    if not (now_min <= BUY_AM_END_MIN or
            (BUY_PM_START_MIN <= now_min < BUY_PM_END_MIN)):
        if not ST["top2_fired"]:
            log("[BUY] skip: outside buy window (am 09:36-11:30 / pm 13:00-14:00)" +
                " now=" + str(now_min))
        ST["top2_fired"] = True
        return

    if not ST["p1_survivors"]:
        _p1_gate(pool, now_min)

    # live pool (server 09:36 rerank) overrides the classic P1 survivors
    if ST.get("live_pool_active") and USE_SERVER_GATES:
        live_surv = _live_pool_survivors(pool)
        if live_surv:
            ST["p1_survivors"] = live_surv
            ST["live_surv_ready"] = True
            log("[LIVE] server rerank pool n=" + str(len(live_surv)) +
                " money_pass=" +
                str(sum(1 for x in live_surv if x.get("money_flow_pass"))))

    p2 = _p2_gate(ST["p1_survivors"], now_min)
    if not ST["gate_dump_done"]:
        _dump_gate(today, pool, ST["p1_survivors"], p2)
        ST["gate_dump_done"] = True

    # Walk ranked candidates high->low: money_pass first, then the rest by
    # score_0500 desc (already sorted by _p2_gate). Buy every stock that
    # passes the P2 dynamic confirm until MAX_DAILY_BUY is filled or the
    # candidate list is exhausted. This "rolls forward" to the next passing
    # name when the top pick's money gate / P2 confirm fails.
    picked = (_order_by_sweet([it for it in p2 if it.get("money_pass")]) +
              _order_by_sweet([it for it in p2 if not it.get("money_pass")]))
    _pick_primary = set(it["code"] for it in p2 if it.get("money_pass"))
    for it in picked:
        if today_bought >= MAX_DAILY_BUY:
            break
        code = it["code"]
        if code in ST["positions"] or code in ST["sent_today"]:
            continue
        if _order_locked(today, code, "BUY"):
            log("[LOCK] " + code + " BUY skip (already ordered today)")
            continue
        if not _board_allowed(code):
            log("[SKIP] " + code + " board not allowed")
            ST["sent_today"].add(code)
            continue
        if _is_st_name(it.get("name")):
            log("[ST] " + code + " " + str(it.get("name")) + " skip (risk-warning)")
            ST["sent_today"].add(code)
            continue
        fb_ok, fb_abandon = _fallback_buy_ok(it, now_min)
        if not fb_ok:
            if fb_abandon:
                rk = int(it.get("rank") or 0)
                if it.get("fund_hard_fail"):
                    log("[FALLBACK] " + code + " fund_hard_fail skip")
                elif rk > FALLBACK_RANK_CAP_PM:
                    log("[FALLBACK] " + code + " rank=" + str(rk) +
                        " > " + str(FALLBACK_RANK_CAP_PM) + " skip")
                ST["sent_today"].add(code)
            continue
        prev_close = ST["prev_close"].get(code) or _prev_close(code)
        if prev_close:
            ST["prev_close"][code] = prev_close
        if _is_limit_up(code, prev_close):
            log("[WAIT] " + code + " limit-up skip today")
            ST["sent_today"].add(code)
            continue
        if _wyckoff_distribution(code):
            log("[WYCKOFF] " + code + " distribution skip today")
            ST["sent_today"].add(code)
            continue

        fill, reason = _p2_decide(code, now_min)
        if fill is None:
            if reason in ("no_confirm_eod", "skip_high_turnover"):
                log("[WAIT] " + code + " P2=" + reason + " abandon today")
                ST["sent_today"].add(code)
            # else wait_confirm / no_quote / no_m5: transient -> silent retry
            # on a later bar (v1.1 widened windows; no 40-80 line/bar spam)
            continue

        # v1.6 slip guard (2026-08-19): the P2 trigger is a 5m bar close that
        # can lag the live tape on a fast move; a market order then fills far
        # above the trigger (300591 08-18: trig 7.88 filled 8.54, +8.4%), and
        # the inflated cost turns a normal next-day pullback into a deep loss
        # the old fixed 0% t2_force floor force-sold. Hold off instead of
        # buying at a blown cost; the candidate stays pending for a later bar.
        try:
            _live = _last_price(code)
            if _live and _live > fill * (1 + MAX_BUY_SLIP_PCT):
                log("[BUY] " + code + " slip guard: live " +
                    str(round(_live, 2)) + " > trig " + str(round(fill, 2)) +
                    " +" + str(round((_live / fill - 1) * 100, 1)) +
                    "% hold off")
                continue
        except BaseException:
            pass

        # v1.5 rotation (P1): holdings full and this candidate passed P2 ->
        # first sell the weakest position to free a slot, then buy on the same
        # bar (A-share T+0 recycle). P2 gating precedes rotation so we never
        # sell a position for a weak name.
        if len(ST["positions"]) >= MAX_HOLDINGS:
            sold = _rotation_sell(now, now_min, today, ROTATION_SELL_N)
            if not sold:
                log("[BUY] skip: holdings full & rotation sold nothing (" +
                    code + ")")
                continue
            # re-query cash: the rotation frees available funds immediately
            try:
                cash, total_asset = _query_cash()
            except BaseException:
                pass

        shares = int(total_asset * POSITION_PCT / fill / 100) * 100
        if shares < 100:
            log("[SKIP] " + code + " insufficient cash")
            continue
        max_cash_shares = int(cash / fill / 100) * 100
        if max_cash_shares < 100:
            log("[SKIP] " + code + " insufficient cash")
            continue
        shares = min(shares, max_cash_shares)
        try:
            ret = tq.order_stock(
                account_id=ST["account"], stock_code=code,
                order_type=tqconst.STOCK_BUY, order_volume=shares,
                price_type=tqconst.PRICE_MY, price=fill)
            if isinstance(ret, int) and ret < 0:
                log("[BUY] " + code + " order REJECTED ret=" + str(ret) +
                    " (no lock written)")
                ST["sent_today"].add(code)
                continue
            if isinstance(ret, dict) and str(ret.get("ErrorId", "0")) != "0":
                log("[BUY] " + code + " order REJECTED ErrorId=" +
                    str(ret.get("ErrorId")) + " (no lock written)")
                ST["sent_today"].add(code)
                continue
            ST["sent_today"].add(code)
            _mark_order_locked(today, code, "BUY")
            ST["positions"][code] = {
                "shares": shares, "cost": fill,
                "name": it.get("name") or bare_code(code),
                "buy_date": today, "peak": fill,
                "trail_armed": False, "awaiting_new_high": False,
                "peel_peak_snapshot": fill, "peel_count": 0,
                "t2_extended": False, "vwap_broken": False,
                "wy_bc_armed": False,
                "today_high": fill,
            }
            today_bought += 1
            tag = "dyn_confirm" if reason == "dyn_confirm" else "snap_confirm"
            sweet_tag = " SWEET" if _is_sweet_zone(code) else ""
            log("[BUY] " + code + " x" + str(shares) + " @ " +
                str(round(fill, 2)) + " track-B P2=" + tag +
                " rank=" + str(it.get("rank")) +
                (" primary" if code in _pick_primary else " fallback") +
                sweet_tag)
            _log_trade("BUY", code, fill, shares, "track_b_" + tag)
            _save_pos_state()
        except BaseException as e:
            log("[BUY] order fail: " + repr(e)[:100])
            ST["sent_today"].add(code)
    # v1.1 (2026-08-17): only close the day's buying when the daily budget is
    # full. Otherwise keep retrying on later bars within the widened windows
    # (candidates that print wait_confirm are retried, not abandoned).
    if today_bought >= MAX_DAILY_BUY and not ST["top2_fired"]:
        ST["top2_fired"] = True
        log("[BUY] top2 fired | bought=" + str(today_bought) +
            " scanned=" + str([x.get("code") for x in picked])[:180])


# ================= MAIN LOOP =================
def is_trading_time(m):
    return (9 * 60 + 25 <= m <= 11 * 60 + 30) or (13 * 60 <= m <= 15 * 60)


def _get_account_handle():
    """Get TDX account handle. Explicit ACCOUNT first, fall back to the
    client's default logged-in account."""
    if ACCOUNT:
        h = tq.stock_account(account=ACCOUNT, account_type="STOCK")
        try:
            if h is not None and int(h or -1) >= 0:
                return h, ACCOUNT
        except BaseException:
            pass
        log("[WARN] account " + ACCOUNT + " handle fail, use default logged-in")
    h = tq.stock_account(account="", account_type="STOCK")
    return h, "(default)"


def main():
    try:
        tq.initialize(__file__)
    except BaseException as e:
        log("[FATAL] tq.initialize fail: " + repr(e)[:120])
        log("       please start TongDaXin quant terminal and login SIM account")
        sys.exit(1)
    handle, used_acct = _get_account_handle()
    try:
        if handle is None or int(handle or -1) < 0:
            log("[FATAL] cannot get account handle: please login SIM account")
            sys.exit(1)
    except BaseException:
        log("[FATAL] cannot get account handle: " + repr(handle))
        sys.exit(1)
    ST["account"] = handle
    log("[INIT] track-B tdx v1.18 (auction-select, vwap 2nd) | acct=" +
        used_acct + " | handle=" + str(handle) +
        " | pos_state=" + str(len(ST.get("pos_state") or {})))
    try:
        _locks = _load_order_locks()
        _day = _locks.get(datetime.now().strftime("%Y%m%d"), {})
        log("[LOCK] today BUY locks=" + str(
            sum(1 for k, v in _day.items() if "BUY" in v)) +
            " detail=" + str({k: sorted(v.keys()) for k, v in _day.items()})[:160])
    except BaseException:
        pass
    _load_ledger()
    _sync_positions()
    _log_positions("INIT")

    while True:
        try:
            now = datetime.now()
            now_min = now.hour * 60 + now.minute
            today = now.strftime("%Y%m%d")
            if today != ST["current_date"]:
                ST["current_date"] = today
                ST["sent_today"] = set()
                ST["gap_cache"] = {}
                ST["sector_gap_mean"] = {}
                ST["p1_survivors"] = []
                ST["top2_fired"] = False
                ST["gate_dump_done"] = False
                ST["live_pool_active"] = False
                ST["live_surv_ready"] = False
                ST["last_pool_n"] = None

            if int(time.time()) % 60 < POLL_SEC:
                _sync_positions()

            if not is_trading_time(now_min):
                time.sleep(POLL_SEC)
                continue

            pool = _load_fullpool(today)
            if pool is None:
                time.sleep(POLL_SEC)
                continue

            # bar-level guard (same as TDX v2.10)
            try:
                _check_sell(now, now_min, today)
            except BaseException as e:
                log("[SELL-ERR] " + repr(e)[:120])

            try:
                _check_buy(now, now_min, today, pool)
            except BaseException as e:
                log("[BUY-ERR] " + repr(e)[:120])

            if now_min >= LEDGER_SNAP_MIN and ST["snap_day"] != today:
                ST["snap_day"] = today
                _snap_daily(today, now)

            time.sleep(POLL_SEC)
        except KeyboardInterrupt:
            log("[STOP] bye")
            break
        except BaseException as e:
            log("[ERR] " + repr(e)[:160])
            time.sleep(POLL_SEC * 3)


if __name__ == "__main__":
    main()
