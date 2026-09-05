# coding:utf-8
# AlphaPilot -- Track B QMT LIVE strategy TEMPLATE v2.6-tpl (trading-day hold)
# =========================================================
# v2.6-tpl (2026-08-31): _hold_days counts TRADING days, not calendar days.
# (today - buy_date).days counted weekends/holidays, so a Friday buy read as
# hold=3 on the following Monday (real T+1) and wrongly hit t2_force_after_extend
# (002466 08-31) / rotation_sell (002058 08-31). New _ASHARE_CLOSED_2026 set +
# _trading_days_between(); only weekend + 2026 official closures excluded.
# v2.5-tpl (2026-08-31): vwap_weak_early next-morning confirm -- same as sim
# v2.5. Sell at next open only if the live price is still BELOW the day-VWAP
# reference recorded when the signal armed (price < vwap_ref); if the price has
# recovered above the reference, cancel the signal and keep holding. Evidence
# (QMT sim 08-31, n=3): unconditional next-open sell hit the day's low and all
# three rallied +3.5%/+3.8%/+7.0%. New persisted field vwap_ref.
# v2.4-tpl (2026-08-29): P2 sweet-zone trigger priority -- same as sim v2.4
# (SWEET_ZONE_MODE / SWEET_GAP_LO / SWEET_GAP_HI; _order_by_sweet reorders
# candidates within each tier before the daily buy-slot race; BUY logs tagged
# [SWEET]). Trigger order preference only, no scoring change. Aligned with
# Track A v2.25 (QMT live v2.25-tpl / QMT sim v2.25 / TDX sim v2.24).
# v2.3-tpl (2026-08-27): persist sell-side metadata to b_pos_state.json (sim v2.3).
# v2.2-tpl (2026-08-26): fallback rank window 10/15 + fund_hard_fail skip (sim v2.2).
# v2.1-tpl (2026-08-26): P2 trend c>day_low, drop p935/prev_close guards (sim v2.1).
# v2.0 (2026-08-26): P2 board-aware gap + day-high guard (same as sim v2.0).
# v1.9 (2026-08-22, stop hard-kicking gap<-2%): same as sim -- a stock
# gapping below -2% is demoted, not eliminated. Weak-sector + negative gap
# still eliminated.
# v1.8 (2026-08-20, T+1 winner force-sell fix): same as sim -- _sync_holdings
# recovers buy_date from the trade log when m_strOpenDate is empty after a
# restart (000651 08-20: +1.5% T+1 wrongly sold as t2_force_after_extend);
# _check_sell T+2 maturity check guards hold_days != 999.
# v1.7 changes vs v1.6 (2026-08-19, Kimi 3 cross-validation fixes):
#   * P0-A: _day_vwap docstrings made pure ASCII (QMT deploy hard rule).
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
# v1.4 changes vs v1.3 (2026-08-18, DHS sell-side eval P0+P1, aligned with Track A v2.15):
#   * T+2 force-close is now conditional: loss (ret<0) force-sell; profit without
#     an early-exit signal extends to T+3 (T2_EXTEND_MAX_DAYS, peel stays armed).
#   * Dynamic weakness rotation (P1): when holdings are full (MAX_HOLDINGS) and a
#     candidate passed P2, first sell the weakest position to free a slot, then
#     buy on the same bar. Weakness score = ret30% + vwap20% + day20% + early15%
#     + peel10% + days5%, relative-rank normalized, momentum guard (day>3% and
#     vol-ratio>1.3 -> skip).
# v1.3 changes vs v1.2 (2026-08-18):
#   P2 5m confirm now only uses TODAY's 5m bars. Old code called
#   get_market_data_ex(count=48, end_time=today) and reverse-engineered the
#   bar time via CONF_START_MIN + i*5 without filtering by date, so early in
#   the session the 5m series could contain previous days' bars. P2's p935 /
#   VWAP / volume-MA5 were then computed on stale bars, which let a
#   money_flow_pass=false, down-on-the-day name (08-18 Xidian 301130, buy log
#   "@30.6" -- a price that never traded today, real fill 29.23) pass the
#   "5m volume-backed up-move" check. Now start_time=today pins the range and _bar_times()
#   keeps real timestamps only.
#   _p2_decide filters today_bars = [b for b in bars if b[0] >= CONF_START_MIN]
#   before computing p935 / VWAP / vol-MA5 (same as the TDX client), and adds a
#   day-trend guard (c >= prev_close) so it never confirms a stock that is
#   down on the day.
#   _day_vwap also restricted to today's bars.
#   _log_trade now updates C.trade_log in memory (ledger overwrite bug).
# v1.2 changes vs v1.1 (2026-08-17):
#   fullpool_live (server 09:36 rerank pool) synced from the QMT SIM version:
#   after LIVE_FULLPOOL_MIN (09:36) Track B uses {date}.fullpool_live.json
#   (server-applied 106-d factor + money + research gates, score = 0.6*pipeline
#   + 0.4*live momentum z) instead of the 05:00 classic fullpool. Client keeps
#   only real-time ABR soft re-check + P2 dynamic confirm (_p2_decide) as the
#   final trigger. Also fixed a missing CALL_DATA_CUTOFF definition.
# v1.1 changes vs v1.0 (2026-08-17):
#   Buy window widened from a 09:40 hard cutoff to two intraday windows
#   (morning 09:36-11:30 + afternoon 13:00-14:00). Real Top10-pool backtest
#   (07-20..07-31, 50 P2 triggers): first-trigger 09:35-10:00 2% / 10:00-10:30
#   28% / 10:30-11:30 44% / 13:00-14:00 20% / 14:00+ 6%; old 09:40 cutoff
#   caught 0/50 (0%). Afternoon 13:00-14:00 best T+1 (+1.80%); tail 14:00+
#   worst (-3.66%) -> closed. _top2_fired only closes when the daily budget is
#   full or the window closes (wait_confirm candidates retried every bar).
#   no_confirm_eod / skip_high_turnover now abandon via sent_today.
#   wait_confirm logs silenced (would spam 40-80 lines/bar on the widened pool).
#
# TEMPLATE: deploy one copy per LIVE account. Edit ONLY the CONFIG block
# (ACCOUNT_ID, ACCOUNT_TAG, board access, position size) -- everything else
# is shared strategy logic. See README at the bottom of the file.
#
# Track B (NEW): QMT-side 09:25-09:35 full-pool gate + auction select.
# This is the LIVE template. Same logic as TrackB_track_b_qmt_auction_sim.py;
# ONLY the CONFIG block differs (live account id + board permissions).
#
# Key differences vs Track A (TrackA_track_a_qmt_full_chain_live.py):
#   [A] Track A reads {date}.candidates.json (Top10, server pre-picked)
#       -> P2 dynamic confirm -> Top2 buy.
#   [B] Track B reads {date}.fullpool.json (05:00 full candidate pool,
#       server only exports, no selection) and runs 09:25-09:35 gates on
#       ALL candidates inside QMT:
#           P0 hard filter (board permission / limit-up / suspended / no auction vol)
#           P1 auction gate (aligns server pre_market_gate.py:
#              near-limit-up / hard-drop / double-weak / demote / keep)
#              + sector diversity (Top10<=2, Top20<=3, pool<=5)
#           P2 money gate (aligns server money_flow_gate.py:
#              active buy ratio / turnover / volume ratio / daily drop / main 5d)
#       -> sort -> Top2 (money_pass first, then score_0500 desc)
#       -> passorder quickTrade=1 buy
#   Sell logic identical to Track A v2.12 (T+1 / limit-down / Wyckoff / VWAP /
#   adaptive stop / T+2 force close / dynamic peel).
#
# Cross-validation conclusions implemented (DUAL_TRACK_BRIEFING.md sec 6):
#   * Performance: 1-minute handlebar granularity; tick only for holding
#     monitoring (no tick full-pool scan).
#   * tick-approx active-buy-ratio only valid in continuous session (after
#     09:30); not used during call auction (09:25-09:30, distorted).
#   * P1 late-data cutoff CALL_DATA_CUTOFF=09:30 (later gaps update only,
#     never re-decide the locked Top2).
#   * score_0500 = icir_raw_score -> score_raw -> ml_score (server fallback).
#   * main_net_5d pre-filled by server; ==0 means missing -> skip hard gate.
#   * Sector aggregation: QMT local get_stock_list_in_sector on all
#     constituents of candidate sectors (wider sample, avoids n=1 distortion).
#
# Naming convention (instantly distinguishable from Track A):
#   Track A: TrackA_track_a_qmt_full_chain_sim.py  (QMT SIM)
#            TrackA_track_a_qmt_full_chain_live.py (QMT LIVE template)
#            TrackA_track_a_tdx_full_chain_sim.py  (TDX SIM)
#   Track B: TrackB_track_b_qmt_auction_sim.py   (QMT SIM account)
#            TrackB_track_b_qmt_auction_live.py  (QMT LIVE template, one copy per account)
#            TrackB_track_b_tdx_auction_sim.py   (TDX SIM account)
#
# Deploy: copy plaintext into <your QMT>\python\  (QMT python dir). Never save
# through the QMT editor (it re-encodes UTF-8 to GBK + encrypts); keep plaintext.
# Per-account: edit CONFIG block at the top (ACCOUNT_ID / ACCOUNT_TAG / board
# access / position size), then deploy one copy per LIVE account.
# Pure ASCII (QMT-safe encoding).
#
import os
import json
import time
import math
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

# =========================================================
# >>> CONFIG  (edit this block per LIVE account, then deploy) <<<
# =========================================================
# Account that runs this copy. QMT LIVE trading end.
ACCOUNT_ID = "8886269286"

# Short account tag used ONLY for local file names (ledger / lock / trade log)
# so two accounts on the same machine never share files. Keep it ASCII,
# no spaces. e.g. "alice" / "bob" / "my_live".
ACCOUNT_TAG = "b_live"

# Board permission for THIS account (v2.4). False = this account cannot
# trade that board -> candidates on that board are skipped, no rejected order.
# STAR = 688/689, ChiNext = 300/301, BSE = 8xx/4xx/920.
ALLOW_STAR = False            # (live default: no STAR access)
ALLOW_CHINEXT = True         # (live default: no ChiNext access)
ALLOW_BSE = False             # (live default: no BSE access)

# --- paths (defaults are account-independent server score source + per-account files) ---
SCORE_DIR = r"C:\alphapilot\scores"
REMOTE_SCORE_BASE = "http://150.158.100.236/qmt_scores"  # server nginx static dir
REMOTE_FETCH_SEC = 60         # min interval between remote fetch attempts
REMOTE_TIMEOUT = 8            # seconds per remote fetch
REMOTE_FETCH_START_MIN = 6 * 60 + 30  # fullpool ready 06:30; fetch after 07:00
TRADE_LOG = "C:/alphapilot/" + ACCOUNT_TAG + "_trades_fullchain.json"
LEDGER_DAILY = "C:/alphapilot/" + ACCOUNT_TAG + "_ledger_daily.json"
LEDGER_DUP_SEC = 300
LEDGER_SNAP_MIN = 15 * 60 + 5
ORDER_LOCK_FILE = "C:/alphapilot/" + ACCOUNT_TAG + "_order_locks.json"
POS_STATE_FILE = "C:/alphapilot/" + ACCOUNT_TAG + "_pos_state.json"
GATE_LOG = "C:/alphapilot/" + ACCOUNT_TAG + "_auction_gate.json"   # gate detail (debug)

# sell-side metadata persisted across QMT restarts (v2.3; +vwap_ref v2.5-tpl)
POS_STATE_PERSIST = (
    "buy_date", "buy_price", "peak", "peel_count", "peel_peak_snapshot",
    "t2_extended", "vwap_broken", "vwap_ref", "wy_bc_armed", "trail_armed",
    "awaiting_new_high",
)

# --- position sizing (sized on TOTAL ASSETS via m_dBalance) ---
MAX_HOLDINGS = 4
MAX_DAILY_BUY = 2
POSITION_PCT = 0.20            # each buy = 20% of total assets

# --- Track B time windows ---
# Call auction starts 09:25, final decision 09:35. 1-minute handlebar.
AUCTION_START_MIN = 9 * 60 + 25   # auction gate begins
AUCTION_SNAP_MIN = 9 * 60 + 30    # auction snapshot cutoff (P1 uses gaps before this)
GATE_START_MIN = 9 * 60 + 30      # money gate begins (continuous session, tick approx valid)
DECIDE_MIN = 9 * 60 + 35          # 09:35 pick Top2 and order (classic fallback)
CALL_DATA_CUTOFF = 9 * 60 + 30    # late auction data cutoff (later gap updates only)

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

# --- Track B LIVE pool (09:36 server rerank, added 2026-08-17) ---
# Server runs live_momentum_scanner (09:35) + morning_live_fund_select then
# export_qmt_scores.py --fullpool-live at 09:36, producing
# {date}.fullpool_live.json with per-stock server-computed fields:
#   score(=0.6*pipeline106d + 0.4*live momentum z), money_flow_pass,
#   research_tier, live_momentum_z, main_net, main_net_5d, active_buy_ratio,
#   turnover, volume_ratio, change_pct, pre_market_gap_pct, pre_market_action.
# Track B switches to this live pool after LIVE_FULLPOOL_MIN: rank by server
# score, gate by server money_flow_pass/research_tier (106-d factor + money +
# research gates all already applied server-side), keep QMT-side P2 dynamic
# confirm (_p2_decide: price>VWAP, no-chase, 5m vol burst) as the final buy
# trigger. Before 09:36 (or when the live file is missing) the classic
# 09:25-09:35 P1/P2 auction flow is used as fallback.
LIVE_FULLPOOL_MIN = 9 * 60 + 36   # switch to server live pool at/after 09:36
USE_SERVER_GATES = True           # use server money_flow_pass/research_tier/score

# --- P1 auction gate params (aligns server pre_market_gate.py) ---
GAP_LIMIT_UP = 9.0                # gap >= 9% near limit-up -> eliminate
GAP_DEMOTE = -0.5                 # gap < -0.5% -> demote (includes former -2% kick band)
SECTOR_WEAK_THRESHOLD = -1.5      # sector gap_mean < -1.5% is weak
MAX_SAME_SECTOR_IN_TOP10 = 2
MAX_SAME_SECTOR_IN_TOP20 = 3
MAX_SAME_SECTOR_IN_POOL = 5
P1_KEEP_TOP_N = 50                # keep top N after auction gate (perf: 1-min)
SECTOR_AGG_MAX_MEMBERS = 30       # cap constituents sampled per sector (perf)

# --- P2 money gate params (aligns server money_flow_gate.py) ---
MIN_ACTIVE_BUY = 0.52             # active buy ratio floor
MIN_TURNOVER = 2.0                # turnover floor %
MAX_TURNOVER = 35.0               # turnover ceiling %
MIN_VOL_RATIO = 0.8               # volume ratio floor
MAX_DROP_PCT = -5.0               # max daily drop %
MIN_MAIN_NET_5D = 0.0             # main 5d net inflow >= 0 (==0 missing -> skip)

# --- mootdx tick feed (free L2-like active buy, bypasses paid QMT L2) ---
# mootdx_feed.py runs as a separate process and writes {date}.json into
# MOOTDX_FEED_DIR. If a fresh entry exists for the code, use its real
# active-buy ratio; otherwise fall back to the L1 tick approximation.
MOOTDX_FEED_DIR = r"C:\alphapilot\l2_feed"
MOOTDX_FEED_MAX_AGE_SEC = 60     # feed older than this -> stale, ignore
USE_MOOTDX_ACTIVE_BUY = True     # master switch; False = keep old L1 approx only

# --- P2 dynamic confirm (same as Track A v2.12, for post-09:35 buys) ---
CONF_VOL_RATIO = 1.3
CONF_MAX_GAP = 0.08           # legacy uniform cap (superseded by _p2_max_gap)
CONF_DAY_HIGH_MAX = 0.85      # skip if (c-low)/(high-low) > 0.85 (top 15% of range)
CONF_START_MIN = 9 * 60 + 35
CONF_END_MIN = 14 * 60 + 57
CONF_MAX_TURNOVER = 5.0
P2_MODE = True

# --- P2 sweet-zone priority (v2.4-tpl, 2026-08-29, aligned with sim v2.4) ---
# P2 triggers with auction gap in [-1.5%, 0] (slight low-open) show upward-bias
# T+1 vs the rest (BT 2026-04~07 + real 07~08). Trigger-order preference only:
# sweet-zone candidates get priority when racing for the daily buy slots.
#   SWEET_ZONE_MODE 0 = off (status quo)
#                    1 = priority (sweet first, non-sweet still fill)
#                    2 = only (strictly sweet-zone, fewer trades)
SWEET_ZONE_MODE = 1
SWEET_GAP_LO = -1.5               # sweet zone = gap% in [LO, HI]
SWEET_GAP_HI = 0.0

# --- fallback buy rank window (v2.2, 2026-08-26) ---
FALLBACK_RANK_OPEN_MIN = 10 * 60
FALLBACK_RANK_CAP_AM = 10
FALLBACK_RANK_CAP_PM = 15
FALLBACK_SKIP_HARD_FAIL = True

# --- adaptive exit defaults ---
DEF_HARD_STOP = -0.10
DEF_TRAIL_ARM = 0.03
DEF_PEEL_PB = 0.015
PEEL_MAX_STEPS = 2
VOL_BASELINE = 0.30

# --- T+2 force close ---
T2_FORCE_HHMM = 14 * 60 + 45
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
VWAP_CONFIRM_MIN = T2_FORCE_HHMM
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

# --- safety ---
LIMIT_DOWN_PCT = -9.7
ANOMALY_PCT = -21.0
RESYNC_SEC = 300
UNIV_SEC = 60

# =========================================================
# >>> SHARED STRATEGY LOGIC (do not edit below this line) <<<
# =========================================================
def init(C):
    C.scores_cache = {}
    C.cand_cache = {}
    C.fullpool_cache = {}
    C.current_date = ""
    C.position_map = {}
    C.stop_watch = {}
    C.sent_today = set()
    C._last_resync = 0
    C._last_univ = 0
    C._last_remote_fetch = 0
    C._last_pos_count = -1
    C._univ_codes = []
    C._univ_dirty = True
    C.run_count = 0
    # Track B gate state
    C._gap_cache = {}            # code -> gap_pct (auction gap, late updates ok)
    C._sector_gap_mean = {}      # industry_l1 -> gap_mean (sector aggregation)
    C._sector_stock_cnt = {}     # industry_l1 -> constituent count used
    C._p1_survivors = []         # P1 survivors list
    C._top2_fired = False        # Top2 ordered flag
    C._auction_done = False
    C._gate_dump_done = False
    C.live_pool_active = False   # True when {date}.fullpool_live.json in use
    C._live_surv_ready = False
    C._sector_members_cache = {} # industry_l1 -> constituent list (fetched once)
    try:
        if os.path.exists(TRADE_LOG):
            with open(TRADE_LOG, "r", encoding="utf-8") as f:
                C.trade_log = json.load(f)
        else:
            C.trade_log = []
    except Exception:
        C.trade_log = []
    C.pos_state = _load_pos_state()
    found = _find_score_dir()
    C.score_dir = found if found else SCORE_DIR
    _sync_holdings(C)
    _log_positions(C, "INIT")
    codes = list(C.position_map.keys())
    try:
        C.set_universe(codes or ["600519.SH"])
        print("[INIT] universe=" + str(codes or ["600519.SH"]))
    except BaseException as e:
        print("[INIT] set_universe fail: " + str(e))
    print("[INIT] track-B v2.6-tpl (auction-select fullpool gate) | acct=" +
          ACCOUNT_ID + " | holdings=" + str(len(codes)) +
          " | score_dir=" + str(C.score_dir) +
          " | pos_state=" + str(len(getattr(C, "pos_state", {}) or {})))
    try:
        _locks = _load_order_locks()
        _day = _locks.get(datetime.now().strftime("%Y%m%d"), {})
        print("[LOCK] today BUY locks=" + str(
            sum(1 for k, v in _day.items() if "BUY" in v)) +
            " detail=" + str({k: sorted(v.keys()) for k, v in _day.items()})[:160])
    except BaseException:
        pass


# ================= HANDLEBAR =================
def handlebar(C):
    if getattr(C, 'do_back_test', False):
        return
    C.run_count += 1
    now = datetime.now()
    now_min = now.hour * 60 + now.minute
    today = now.strftime("%Y%m%d")

    if today != C.current_date:
        C.current_date = today
        C.sent_today = set()
        C.scores_cache.pop(today, None)
        C.cand_cache.pop(today, None)
        C.fullpool_cache.pop(today, None)
        C._univ_dirty = True
        C._gap_cache = {}
        C._sector_gap_mean = {}
        C._sector_stock_cnt = {}
        C._p1_survivors = []
        C._top2_fired = False
        C._auction_done = False
        C._gate_dump_done = False
        C._live_surv_ready = False
        C._sector_members_cache = {}

    ts = time.time()
    if ts - C._last_resync >= RESYNC_SEC:
        C._last_resync = ts
        _sync_holdings(C)

    pool = _load_fullpool(C, today)
    if pool is None:
        return

    # subscribe: holdings + candidates (holdings tick, candidates batch quotes)
    if (getattr(C, '_univ_dirty', True) or
            ts - C._last_univ >= UNIV_SEC):
        C._last_univ = ts
        C._univ_dirty = False
        try:
            cand = [_qmt_code(x["symbol"]) for x in pool]
            C.set_universe(list(C.position_map.keys()) + cand[:200])
        except BaseException:
            pass

    if not _is_trading_time(now_min):
        return

    # bar-level guard (same as Track A v2.12): sell error never blocks buy
    try:
        _check_sell(C, now, now_min, today)
    except BaseException as e:
        print("[SELL-ERR] " + repr(e)[:120])

    try:
        _check_buy(C, now, now_min, today, pool)
    except BaseException as e:
        print("[BUY-ERR] " + repr(e)[:120])

    if now_min >= LEDGER_SNAP_MIN and getattr(C, "_snap_day", "") != today:
        C._snap_day = today
        _snap_daily(C, today, now)


def _is_trading_time(m):
    return (9 * 60 + 25 <= m <= 11 * 60 + 30) or (13 * 60 <= m <= 15 * 60)


# ================= FULLPOOL LOAD =================
def _find_score_dir():
    for p in (SCORE_DIR, r"D:\alphapilot\scores",
              r"E:\alphapilot\scores",
              os.path.join(os.getcwd(), "scores"), r".\scores"):
        if os.path.exists(p):
            return p
    return SCORE_DIR


def _fetch_remote_fullpool(C, date_str):
    """Fetch {date}.fullpool.json from server nginx if local file missing.
    Throttled, silent-fail, retry next bar. fullpool generated 06:30."""
    now = datetime.now()
    if now.hour * 60 + now.minute < REMOTE_FETCH_START_MIN:
        return
    ts = time.time()
    if ts - C._last_remote_fetch < REMOTE_FETCH_SEC:
        return
    C._last_remote_fetch = ts
    try:
        import urllib.request
    except Exception:
        return
    if not os.path.isdir(C.score_dir):
        try:
            os.makedirs(C.score_dir)
        except Exception:
            return
    fpath = os.path.join(C.score_dir, date_str + ".fullpool.json")
    if os.path.exists(fpath) and os.path.getsize(fpath) > 0:
        return
    url = REMOTE_SCORE_BASE + "/" + date_str + ".fullpool.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "QMT/2.2"})
        with urllib.request.urlopen(req, timeout=REMOTE_TIMEOUT) as resp:
            body = resp.read()
            if not body:
                print("[FETCH] " + url + " empty")
                return
            with open(fpath, "wb") as f:
                f.write(body)
            print("[FETCH] fullpool <- " + url + " (" + str(len(body)) + "b)")
    except Exception as e:
        print("[FETCH] fullpool fail: " + str(e)[:90])


def _fetch_remote_fullpool_live(C, date_str):
    """Fetch {date}.fullpool_live.json from server nginx (09:36 rerank).
    Throttled (shared with classic fetch), silent-fail. Only after
    LIVE_FULLPOOL_MIN; classic fullpool is the pre-09:36 fallback."""
    now = datetime.now()
    now_min = now.hour * 60 + now.minute
    if now_min < LIVE_FULLPOOL_MIN:
        return
    ts = time.time()
    if ts - C._last_remote_fetch < REMOTE_FETCH_SEC:
        return
    C._last_remote_fetch = ts
    try:
        import urllib.request
    except Exception:
        return
    if not os.path.isdir(C.score_dir):
        try:
            os.makedirs(C.score_dir)
        except Exception:
            return
    fpath = os.path.join(C.score_dir, date_str + ".fullpool_live.json")
    if os.path.exists(fpath) and os.path.getsize(fpath) > 0:
        return
    url = REMOTE_SCORE_BASE + "/" + date_str + ".fullpool_live.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "QMT/2.2"})
        with urllib.request.urlopen(req, timeout=REMOTE_TIMEOUT) as resp:
            body = resp.read()
            if not body:
                print("[FETCH] live empty")
                return
            with open(fpath, "wb") as f:
                f.write(body)
            print("[FETCH] fullpool_live <- " + url + " (" + str(len(body)) + "b)")
    except Exception as e:
        print("[FETCH] fullpool_live fail: " + str(e)[:90])


def _load_fullpool(C, date_str):
    """Track B candidate source:
      < LIVE_FULLPOOL_MIN: {date}.fullpool.json (05:00 full pool).
      >= LIVE_FULLPOOL_MIN: {date}.fullpool_live.json (09:35 server rerank,
      106-d factor + money + research gates), fallback to classic if missing.
    Returns [{"symbol","name","rank","industry_l1","score_0500",
    "main_net_5d", +live: score/money_flow_pass/research_tier/...}, ...]
    Fail -> None (skip this bar, retry next)."""
    now = datetime.now()
    now_min = now.hour * 60 + now.minute
    live_mode = USE_SERVER_GATES and now_min >= LIVE_FULLPOOL_MIN
    if not live_mode:
        return _load_fullpool_classic(C, date_str)

    # live pool first, classic fallback
    live = _load_fullpool_file(C, date_str, ".fullpool_live.json",
                               _fetch_remote_fullpool_live)
    if live is not None:
        C.live_pool_active = True
        print("[FULLPOOL] LIVE mode n=" + str(len(live)))
        return live
    C.live_pool_active = False
    return _load_fullpool_classic(C, date_str)


def _load_fullpool_classic(C, date_str):
    """Classic 05:00 fullpool (pre-09:36 fallback path).

    score normalization: prefer server A-arm final score (includes pattern
    breakout and other soft boosts; fullpool.json "score" field since 08-19),
    fall back to raw score_0500 when missing.
    """
    pool = _load_fullpool_file(C, date_str, ".fullpool.json",
                               _fetch_remote_fullpool)
    if pool is not None:
        C.live_pool_active = False
        for _it in pool:
            if _it.get("score") is None:
                _it["score"] = _it.get("score_0500")
    return pool


def _load_fullpool_file(C, date_str, suffix, fetch_fn):
    """Load {date}{suffix} from local scores dir; fetch remote if missing.
    Returns rows or None. Caches into C.fullpool_cache keyed by suffix."""
    cache_key = date_str + suffix
    if cache_key in C.fullpool_cache:
        return C.fullpool_cache[cache_key]
    fpath = os.path.join(C.score_dir, date_str + suffix)
    if not os.path.exists(fpath):
        fetch_fn(C, date_str)
        if not os.path.exists(fpath):
            return None
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            d = json.load(f)
        rows = d.get("rows") or []
        C.fullpool_cache[cache_key] = rows
        print("[FULLPOOL] " + date_str + suffix + " n=" + str(len(rows)))
        return rows
    except Exception as e:
        print("[FULLPOOL] err: " + str(e))
        return None


# ================= POSITION STATE (persist across QMT restarts, v2.3) =================
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
        bp = float(saved.get("buy_price") or 0)
        if bp > 0 and float(pos.get("buy_price") or 0) <= 0:
            pos["buy_price"] = bp
    except BaseException:
        pass


def _save_pos_state(C):
    """Write sell-side metadata for all open holdings."""
    try:
        positions = {}
        for code, pos in (getattr(C, "position_map", None) or {}).items():
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
        C.pos_state = positions
    except Exception as e:
        if getattr(C, "run_count", 0) % 60 == 0:
            print("[POS] save err: " + str(e)[:80])


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


def _log_positions(C, tag):
    """Startup/resync summary: code, shares, buy_date, hold days, peel."""
    today = datetime.now().strftime("%Y%m%d")
    pm = getattr(C, "position_map", None) or {}
    if not pm:
        print("[" + tag + "] positions: none")
        return
    print("[" + tag + "] positions n=" + str(len(pm)))
    for code in sorted(pm.keys()):
        pos = pm[code]
        hd = _hold_days_short(pos, today)
        hd_s = "?" if hd == 999 else str(hd)
        ext = " ext" if pos.get("t2_extended") else ""
        print("[" + tag + "]   " + code + " " + str(pos.get("name") or "") +
              " " + str(int(pos.get("shares") or 0)) + "sh" +
              " bd=" + _fmt_buy_date(pos.get("buy_date")) +
              " hold=" + hd_s +
              " peel=" + str(int(pos.get("peel_count") or 0)) + ext)


# ================= POSITION SYNC (real QMT account) =================
def _recover_buy_date(C, code):
    """Restore buy_date from persisted pos state, then local trade log. QMT sim
    leaves m_strOpenDate empty on restarts and, once T+1 unlocks (can_use == vol),
    the old can_use<vol inference stops firing: buy_date falls empty -> _hold_days
    returns 999 -> the 14:45 window force-sells a T+1 winner as if held past
    T2_EXTEND_MAX_DAYS (000651 on 08-20). Returns %Y%m%d ('' when unknown)."""
    sym = _qmt_code(code)
    try:
        saved = (getattr(C, "pos_state", None) or {}).get(sym)
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
        for t in reversed(C.trade_log or []):
            if t.get("action") != "BUY":
                continue
            if _qmt_code(t.get("symbol")) != sym:
                continue
            ts = str(t.get("time") or "")
            if len(ts) >= 10:
                return ts[:10].replace("-", "")
    except BaseException:
        pass
    return ""


def _qmt_code(code, exchange=""):
    """Convert bare code to QMT format (300308.SZ / 600519.SH)."""
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


def _diag_today_orders():
    try:
        today = datetime.now().strftime("%Y%m%d")
        objs = get_trade_detail_data(ACCOUNT_ID, "STOCK", "ORDER") or []
        mine = [o for o in objs
                if str(getattr(o, "m_strInsertDate", "") or "") == today]
        os_map = {48: "NotReported", 49: "Pending", 50: "Reported", 51: "Canceling",
                  52: "PartFillCanceling", 53: "PartCanceled", 54: "Canceled", 55: "PartFilled",
                  56: "Filled", 57: "Invalid"}
        print("[DIAG] today broker orders n=" + str(len(mine)))
        for o in mine[-8:]:
            print("[DIAG]   " + str(getattr(o, "m_strInstrumentID", "?")) +
                  " vol=" + str(getattr(o, "m_nVolumeTotalOriginal", 0)) +
                  " px=" + str(getattr(o, "m_dOrderPrice", 0)) +
                  " st=" + str(os_map.get(
                      getattr(o, "m_nOrderStatus", None),
                      getattr(o, "m_nOrderStatus", "?"))) +
                  " t=" + str(getattr(o, "m_strInsertTime", "")))
    except BaseException as e:
        print("[DIAG] order query fail: " + str(e)[:80])


def _sync_holdings(C):
    try:
        objs = get_trade_detail_data(ACCOUNT_ID, "STOCK", "POSITION") or []
        live = {}
        if C.run_count == 0:
            print("[SYNC] acct=" + ACCOUNT_ID + " pos_n=" + str(len(objs)))
            _diag_today_orders()
        today = datetime.now().strftime("%Y%m%d")
        for obj in objs:
            code = _qmt_code(obj.m_strInstrumentID,
                             getattr(obj, "m_strExchangeID", ""))
            vol = obj.m_nVolume
            if vol <= 0:
                continue
            cost = float(obj.m_dOpenPrice or 0)
            bd = str(getattr(obj, "m_strOpenDate", "") or "").strip()
            can_use = int(getattr(obj, "m_nCanUseVolume", 0) or
                          getattr(obj, "m_nCanUseVol", 0) or 0)
            # v1.8 (2026-08-20): QMT sim leaves m_strOpenDate empty for both
            # same-day and older positions. The old `can_use < vol` inference
            # only fires while the T+1 lock still blocks part of the position;
            # once fully tradable (can_use == vol) buy_date falls empty, which
            # makes _hold_days return 999 and force-sells a T+1 winner at 14:45
            # (000651 08-20: +1.5%, sold as t2_force_after_extend). Recover the
            # true buy date from the local trade log before any inference.
            if not bd:
                bd = _recover_buy_date(C, code)
            if not bd and can_use < vol:
                bd = today
            name = getattr(obj, "m_strInstrumentName", "") or code
            live[code] = True
            saved = (getattr(C, "pos_state", None) or {}).get(code)
            if code not in C.position_map:
                C.position_map[code] = {
                    "shares": vol,
                    "can_use": can_use,
                    "buy_price": cost,
                    "name": name,
                    "buy_date": bd,
                    "peak": cost,
                    "trail_armed": False,
                    "awaiting_new_high": False,
                    "peel_peak_snapshot": cost,
                    "peel_count": 0,
                    "t2_extended": False,
                    "vwap_broken": False,
                    "wy_bc_armed": False,
                    "pending": False,
                    "today_high": cost,
                }
                _merge_pos_state(C.position_map[code], saved)
                if not C.position_map[code].get("buy_date"):
                    C.position_map[code]["buy_date"] = _recover_buy_date(C, code)
                C.stop_watch[code] = 0
                _bd = C.position_map[code].get("buy_date") or bd
                print("[SYNC] +" + code + " " + name + " " + str(vol) +
                      "sh cost=" + str(round(cost, 3)) + " bd=" + str(_bd) +
                      " can_use=" + str(can_use) +
                      (" [state]" if saved else ""))
            else:
                C.position_map[code]["shares"] = vol
                C.position_map[code]["can_use"] = can_use
                C.position_map[code]["buy_price"] = cost
                C.position_map[code]["pending"] = False
                if not C.position_map[code].get("buy_date") and bd:
                    C.position_map[code]["buy_date"] = bd
                _merge_pos_state(C.position_map[code], saved)
                if not C.position_map[code].get("buy_date"):
                    C.position_map[code]["buy_date"] = _recover_buy_date(C, code)
        for code in list(C.position_map.keys()):
            if code not in live:
                if _order_locked(today, code, "BUY"):
                    C.position_map[code]["pending"] = True
                    if C.run_count % 12 == 0:
                        print("[SYNC] ~" + code + " BUY pending (keep slot)")
                    continue
                print("[SYNC] -" + code + " closed")
                C.position_map.pop(code, None)
                C.stop_watch.pop(code, None)
        if len(objs) != C._last_pos_count:
            print("[SYNC] holdings=" + str(len(C.position_map)))
            C._last_pos_count = len(objs)
        _save_pos_state(C)
    except BaseException as e:
        if C.run_count % 60 == 0:
            print("[SYNC] err: " + str(e)[:80])


# ================= QUOTE HELPERS =================
def _col(df, name):
    if df is None:
        return []
    try:
        return [float(x) for x in df[name].values.tolist()]
    except (AttributeError, KeyError, TypeError):
        try:
            return [float(df[name][i]) for i in range(len(df[name]))]
        except Exception:
            return []


def _get_quote(C, code):
    """Return (last_daily_close, prev_close, open, high)."""
    today = datetime.now().strftime("%Y%m%d")
    for period in ("1d", "1m"):
        try:
            data = C.get_market_data_ex(
                ["close", "open", "high"], [code], period=period,
                count=2, end_time=today, subscribe=True)
            if data and isinstance(data, dict) and code in data:
                closes = _col(data[code], "close")
                if closes:
                    price = closes[-1]
                    prev = closes[-2] if len(closes) >= 2 else price
                    opens = _col(data[code], "open")
                    highs = _col(data[code], "high")
                    open_ = opens[-1] if opens else price
                    high = highs[-1] if highs else price
                    return price, prev, open_, high
        except BaseException:
            pass
    return None, None, None, None


def _get_turnover(C, code):
    """Daily turnover % = today's cumulative volume / float shares."""
    today = datetime.now().strftime("%Y%m%d")
    try:
        detail = C.get_instrument_detail(code)
        if not detail or not isinstance(detail, dict):
            return None
        float_shares = float(detail.get("FloatShares", 0) or 0)
        if float_shares <= 0:
            return None
        data = C.get_market_data_ex(
            ["volume"], [code], period="1d", count=1,
            end_time=today, subscribe=True)
        if not data or not isinstance(data, dict) or code not in data:
            return None
        vols = _col(data[code], "volume")
        if not vols:
            return None
        cum_vol = vols[-1]
        if cum_vol <= 0:
            return None
        return cum_vol / float_shares * 100.0
    except BaseException:
        return None


def _closed_5m_bars(now_min):
    """Number of 5m bars already closed today (A-share 09:30-11:30/13:00-15:00,
    bar time = closing minute, first bar 09:35). 0 before 09:35."""
    if now_min <= 9 * 60 + 30:
        return 0
    if now_min <= 11 * 60 + 30:          # 09:35..11:30
        return (now_min - (9 * 60 + 35)) // 5 + 1
    if now_min < 13 * 60 + 5:            # lunch break -> full morning
        return 24
    if now_min <= 15 * 60:               # 13:05..15:00
        return 24 + (now_min - (13 * 60 + 5)) // 5 + 1
    return 48


def _get_volume_ratio(C, code):
    """Volume ratio = today cum vol (up to now) / prior 5d same-time cum vol
    mean. Same-time alignment avoids the 09:35 structural under-count of the
    old 'today realtime / prior 5d FULL-DAY mean' formula (which can never
    reach MIN_VOL_RATIO at 09:35). Uses 5m bars; needs ~6 trading days of
    local 5m history. None on fail (P2 treats None as soft-skip)."""
    now = datetime.now()
    now_min = now.hour * 60 + now.minute
    today = now.strftime("%Y%m%d")
    try:
        k = _closed_5m_bars(now_min)
        if k <= 0:
            return None
        data = C.get_market_data_ex(
            ["volume"], [code], period="5m", count=6 * 48, end_time=today,
            subscribe=True)
        if not data or not isinstance(data, dict) or code not in data:
            return None
        vols = _col(data[code], "volume")
        if not vols:
            return None
        n = len(vols)
        if n < k:
            return None
        cur = sum(float(v) for v in vols[n - k:n] if v == v)  # skip NaN
        if cur <= 0:
            return None
        base_list = []
        for d in range(1, 6):            # 1..5 days back, 48 bars per day
            seg = vols[n - k - 48 * d:n - k - 48 * d + k]
            if len(seg) == k and any(float(v) == v for v in seg):
                s = sum(float(v) for v in seg if v == v)
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


def _get_daily_change(C, code):
    """Daily drop % = (price/PreClose - 1)*100. None on fail."""
    try:
        detail = C.get_instrument_detail(code)
        if not detail or not isinstance(detail, dict):
            return None
        pc = float(detail.get("PreClose", 0) or 0)
        if pc <= 0:
            return None
        price, _, _, _ = _get_quote(C, code)
        if price is None or price <= 0:
            return None
        return (price / pc - 1) * 100.0
    except BaseException:
        return None


def _get_active_buy_from_mootdx(code):
    """Read active-buy ratio from mootdx_feed local JSON.

    Returns (abr, age_sec) or (None, None) when no fresh entry.
    Falls back naturally: caller uses L1 tick approximation if None.
    """
    if not USE_MOOTDX_ACTIVE_BUY:
        return None, None
    try:
        today = datetime.now().strftime("%Y%m%d")
        p = os.path.join(MOOTDX_FEED_DIR, today + ".json")
        if not os.path.exists(p):
            return None, None
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        rec = data.get(code)
        if not rec:
            return None, None
        ts = rec.get("ts", 0)
        age = time.time() - ts
        if age > MOOTDX_FEED_MAX_AGE_SEC:
            return None, age
        abr = rec.get("abr")
        if abr is None:
            return None, age
        return float(abr), age
    except BaseException:
        return None, None


def _get_active_buy_ratio(C, code):
    """active buy ratio: mootdx real ticks first, then L1 tick approx.

    mootdx feed (free TDX transaction ticks) gives real per-tick buy/sell
    direction; prefer it when fresh. Fall back to QMT L1 tick approximation
    (trade price >= ask1 -> buy; <= bid1 -> sell) when feed missing/stale.
    """
    abr, age = _get_active_buy_from_mootdx(code)
    if abr is not None:
        return abr
    today = datetime.now().strftime("%Y%m%d")
    try:
        data = C.get_market_data_ex(
            ["lastPrice", "askPrice1", "bidPrice1", "volume"], [code],
            period="tick", count=120, subscribe=True)
        if not data or not isinstance(data, dict) or code not in data:
            return None
        df = data[code]
        lp = _col(df, "lastPrice")
        ap = _col(df, "askPrice1")
        bp = _col(df, "bidPrice1")
        vol = _col(df, "volume")
        n = min(len(lp), len(ap), len(bp), len(vol))
        if n < 2:
            return None
        buy = 0.0
        tot = 0.0
        for i in range(n):
            a, b, p, v = ap[i], bp[i], lp[i], vol[i]
            if v <= 0 or p <= 0:
                continue
            if a > 0 and p >= a:
                buy += v
                tot += v
            elif b > 0 and p <= b:
                tot += v
        if tot <= 0:
            return None
        return buy / tot
    except BaseException:
        return None


def _is_limit_up(C, code):
    """True if current price is sealed at the limit-up price."""
    try:
        detail = C.get_instrument_detail(code)
        if not detail or not isinstance(detail, dict):
            return False
        up = float(detail.get("UpStopPrice", 0) or 0)
        if up <= 0:
            return False
        price, prev, open_, high = _get_quote(C, code)
        if price is None or price <= 0:
            return False
        return price >= up - 0.001
    except BaseException:
        return False


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
    """ST/risk-warning guard (QMT live client, 2026-08-25). Missing name -> False."""
    n = str(name or "").strip().upper()
    if not n:
        return False
    # ASCII-only source: unicode escapes for delist name chars
    _dl = "\u9000"
    _dl2 = "\u9000\u5e02"
    return "ST" in n or n.startswith(_dl) or _dl2 in n


def _get_last(C, code):
    """Latest 1m close (real-time)."""
    today = datetime.now().strftime("%Y%m%d")
    for period in ("1m", "tick"):
        try:
            if period == "tick":
                data = C.get_market_data_ex(
                    ["lastPrice"], [code], period="tick",
                    count=1, subscribe=True)
                if data and isinstance(data, dict) and code in data:
                    arr = _col(data[code], "lastPrice")
                    if arr:
                        return float(arr[-1])
            else:
                data = C.get_market_data_ex(
                    ["close"], [code], period="1m",
                    count=1, end_time=today, subscribe=True)
                if data and isinstance(data, dict) and code in data:
                    arr = _col(data[code], "close")
                    if arr:
                        return float(arr[-1])
        except BaseException:
            pass
    return None


def _get_prev_close(C, code):
    try:
        detail = C.get_instrument_detail(code)
        if detail and isinstance(detail, dict):
            pc = detail.get("PreClose")
            if pc:
                return float(pc)
    except BaseException:
        pass
    return None


def _bar_times(df, n):
    """Parse real (date_str, tmin) per bar from a QMT 5m DataFrame index.
    tmin = minutes since midnight (e.g. 09:35 -> 575). Returns a list of
    (date_str, tmin) tuples, or None when the index is not parseable.
    QMT's get_market_data_ex(count=48) can return previous days' bars early in
    the session; the old code reverse-engineered times via CONF_START_MIN + i*5
    and never filtered by date, so P2's p935/VWAP/vol-MA5 were computed on stale
    bars (e.g. the 08-18 09:40 301130 buy fired on a historical bar's close 30.6
    instead of today's tape). QMT indexes are time strings, e.g. '20260818',
    '20260818093500' or '2026-08-18 09:35:00'."""
    import re
    try:
        idx = df.index
        out = []
        for i in range(n):
            t = idx[i]
            if hasattr(t, "strftime"):
                out.append((t.strftime("%Y-%m-%d"),
                            int(t.hour) * 60 + int(t.minute)))
                continue
            s = str(t).strip()
            m = re.match(r"(\d{4})[-/](\d{2})[-/](\d{2})[ T](\d{2}):(\d{2})", s)
            if m:
                y, mo, d, h, mi = m.groups()
                out.append(("%s-%s-%s" % (y, mo, d),
                            int(h) * 60 + int(mi)))
                continue
            m = re.match(r"^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})", s)
            if m:
                y, mo, d, h, mi = m.groups()
                out.append(("%s-%s-%s" % (y, mo, d),
                            int(h) * 60 + int(mi)))
                continue
            m = re.match(r"^(\d{4})(\d{2})(\d{2})$", s)
            if m:
                y, mo, d = m.groups()
                out.append(("%s-%s-%s" % (y, mo, d), None))
                continue
            return None
        return out
    except BaseException:
        return None


def _get_m5_bars(C, code):
    """Today's 5m K-lines from QMT. Return [(tmin, open, close, high, low, vol), ...].
    tmin = real bar time (minutes since midnight). Only today's bars are kept.
    (v1.3-tpl, 2026-08-18) QMT get_market_data_ex(count=48) without start_time
    can return previous days' 5m bars early in the session. The old code
    reverse-engineered the bar time via CONF_START_MIN + i*5 and never filtered
    by date, so P2's p935 / VWAP / volume-MA5 were computed on stale bars (e.g.
    the 08-18 09:40 301130 buy fired on a historical bar's close 30.6 instead
    of today's tape). Now start_time pins today and real timestamps are kept."""
    today = datetime.now().strftime("%Y%m%d")
    today_str = datetime.now().strftime("%Y-%m-%d")
    try:
        data = C.get_market_data_ex(
            ["open", "close", "high", "low", "volume"], [code], period="5m",
            start_time=today, end_time=today, count=48, subscribe=True)
        if not data or not isinstance(data, dict) or code not in data:
            return None
        df = data[code]
        opens = _col(df, "open")
        closes = _col(df, "close")
        highs = _col(df, "high")
        lows = _col(df, "low")
        vols = _col(df, "volume")
        n = min(len(closes), len(opens), len(highs), len(lows), len(vols))
        if n < 2:
            return None
        times = _bar_times(df, n)
        if not times:
            return None
        out = []
        for i in range(n):
            ds, tmin = times[i]
            if ds != today_str or tmin is None:
                continue
            out.append((tmin, float(opens[i]), float(closes[i]),
                        float(highs[i]), float(lows[i]), float(vols[i])))
        if len(out) < 2:
            return None
        return out
    except BaseException:
        return None


def _day_vwap(C, code):
    """Today's day VWAP (intraday avg price, CNY/share).

    Primary: QMT's own real-time tick (get_full_tick). `amount` (cumulative CNY
    turnover today) and `pvolume` (cumulative shares today) are both
    day-cumulative at the latest
    tick, so amount/pvolume IS the authoritative per-share day VWAP with no
    hand/share unit conversion. A plausibility guard (0.5x..2x of lastPrice)
    rejects any residual unit mismatch, else it falls back to the 5m bars.

    Fallback: 5m bars. QMT 5m `volume` is in HANDS (100 shares) while `amount`
    is in CNY, so a raw amount/volume ratio is 100x the real per-share VWAP
    (observed 300591: vwap=806.98 when the tape was ~8.07 -> unit bug in the
    calc, NOT a QMT data fetch error; QMT's 5m K-line itself was correct).
    Volume is therefore x100 (hand->share) so the ratio is a true CNY/share VWAP.
    """
    try:
        ticks = C.get_full_tick([code])
        if ticks and isinstance(ticks, dict):
            t = ticks.get(code)
            if t and isinstance(t, dict):
                amt = float(t.get("amount") or 0)
                pv = float(t.get("pvolume") or 0)
                lp = float(t.get("lastPrice") or 0)
                if amt > 0 and pv > 0 and lp > 0:
                    v = amt / pv
                    if 0.5 * lp <= v <= 2.0 * lp:
                        return v
    except BaseException:
        pass
    today = datetime.now().strftime("%Y%m%d")
    try:
        data = C.get_market_data_ex(
            ["close", "volume", "amount"], [code], period="5m",
            start_time=today, end_time=today, count=48, subscribe=True)
        if not data or not isinstance(data, dict) or code not in data:
            return None
        df = data[code]
        closes = _col(df, "close")
        vols = _col(df, "volume")
        amts = _col(df, "amount")
        n = min(len(closes), len(vols), len(amts))
        if n < 2:
            return None
        times = _bar_times(df, n)
        if not times:
            return None
        today_str = datetime.now().strftime("%Y-%m-%d")
        tv = 0.0
        ta = 0.0
        for i in range(n):
            if times[i][0] != today_str:
                continue
            tv += float(vols[i]) * 100.0     # hand -> share
            ta += float(amts[i])             # CNY
        if tv <= 0:
            return None
        if ta <= 0:
            ta = sum(float(closes[i]) * float(vols[i]) * 100.0
                     for i in range(n) if times[i][0] == today_str)
        return ta / tv
    except BaseException:
        return None


# ================= ADAPTIVE EXIT PARAMS =================
def _annual_vol(C, code):
    """20-day annualized volatility (0.10~0.80). Pure python."""
    today = datetime.now().strftime("%Y%m%d")
    for subscribe in (True, False):
        try:
            data = C.get_market_data_ex(
                ["close"], [code], period="1d", count=22,
                end_time=today, subscribe=subscribe)
            if data and isinstance(data, dict) and code in data:
                arr = _col(data[code], "close")
                if len(arr) >= 3:
                    lr = [math.log(arr[i] / arr[i - 1])
                          for i in range(1, len(arr))
                          if arr[i - 1] > 0 and arr[i] > 0]
                    if len(lr) >= 2:
                        m = sum(lr) / len(lr)
                        var = sum((x - m) ** 2 for x in lr) / (len(lr) - 1)
                        dv = math.sqrt(var)
                        av = dv * math.sqrt(252)
                        return max(0.10, min(0.80, av))
        except BaseException:
            pass
    return None


def _adaptive_params(C, code):
    """Return (hard_stop_pct, trail_arm, peel_pullback) adaptive."""
    vol = _annual_vol(C, code)
    if vol is None:
        return DEF_HARD_STOP, DEF_TRAIL_ARM, DEF_PEEL_PB
    dev = vol - VOL_BASELINE
    hs = round(DEF_HARD_STOP - dev * 0.10, 3)
    ta = round(max(0.01, DEF_TRAIL_ARM - dev * 0.05), 3)
    pb = round(min(0.05, DEF_PEEL_PB + dev * 0.03), 3)
    return hs, ta, pb


def _day_amplitude_pct(C, code):
    """Today's intraday amplitude in % of prev close (high-low)/prev*100.
    0.0 when data is unavailable. Uses today's 5m bars high/low."""
    try:
        pc = _get_prev_close(C, code)
        if not pc or pc <= 0:
            return 0.0
        bars = _get_m5_bars(C, code)
        if not bars:
            return 0.0
        hi = max(b[3] for b in bars)
        lo = min(b[4] for b in bars)
        if hi <= 0 or lo <= 0:
            return 0.0
        return max(0.0, (hi - lo) / pc * 100.0)
    except BaseException:
        return 0.0


def _t2_force_floor(C, code):
    """Dynamic T+2 force-close floor (negative %). A fixed 0% floor force-sold
    every loser at 14:45 regardless of how wide the name's normal range is;
    on a wide-amplitude / high-vol day that is just noise, not weakness
    (300591 08-19: bought 7.88 P2 but the tape filled 8.54, next day -8.7%
    vs cost yet only -1% from the trigger -> the 0% floor was the aggressor).
    The floor now widens (more negative) with the day's amplitude and the
    stock's annual vol, so a normal pullback inside the day's range survives
    to T+3. Capped at T2_FORCE_FLOOR_MAX so hard_stop (hs) still owns the tail."""
    amp = _day_amplitude_pct(C, code)
    vol = _annual_vol(C, code) or VOL_BASELINE
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


# ================= WYCKOFF DISTRIBUTION (same as Track A v2.10) =================
def _wyckoff_distribution(C, code):
    try:
        data = C.get_market_data_ex(
            ["open", "high", "low", "close", "amount"], [code], period="1d",
            count=80, subscribe=True)
        if not data or not isinstance(data, dict) or code not in data:
            return False
        df = data[code]
        op = _col(df, "open")
        hi = _col(df, "high")
        lo = _col(df, "low")
        cl = _col(df, "close")
        vo = _col(df, "amount")
        n = min(len(op), len(hi), len(lo), len(cl), len(vo))
        if n < 62:
            return False
        hi = hi[: n - 1]
        lo = lo[: n - 1]
        cl = cl[: n - 1]
        op = op[: n - 1]
        vo = vo[: n - 1]
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
                    if cl[k] < op[k] or tail > (hi[k] - lo[k]) * WY_BC_SHADOW_FRAC:
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


def _wyckoff_holding_bc(C, code, peak):
    if peak <= 0:
        return False
    try:
        data = C.get_market_data_ex(
            ["volume"], [code], period="1d", count=22, subscribe=True)
        if not data or not isinstance(data, dict) or code not in data:
            return False
        vols = _col(data[code], "volume")
        if len(vols) < 6:
            return False
        vols = vols[:-1]
        if len(vols) < 5:
            return False
        vma20 = float(sum(vols[-20:]) / min(20, len(vols)))
        if vma20 <= 0:
            return False
    except BaseException:
        return False
    bars = _get_m5_bars(C, code)
    if not bars or len(bars) < 2:
        return False
    today_v = sum(b[5] for b in bars)
    if today_v <= vma20 * WY_BC_SELL_VOL_RATIO:
        return False
    for b in bars:
        _, o, c, h, l, _ = b
        if h >= peak * WY_BC_SELL_NEAR_PEAK:
            body_top = max(o, c)
            tail = h - body_top
            rng = h - l
            if (c < o or (rng > 0 and tail > rng * WY_BC_SELL_SHADOW_FRAC)):
                return True
    return False


# ================= P2 DYNAMIC CONFIRM (same as Track A v2.12) =================
def _vol_ma5(vols, i):
    s = vols[max(0, i - 4):i + 1]
    return sum(s) / len(s) if s else 0.0


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


def _p2_decide(C, code, now_min):
    price, prev, open_, high = _get_quote(C, code)
    last = _get_last(C, code) or price
    if not price or price <= 0:
        return None, "no_quote"
    pc = _get_prev_close(C, code)
    if pc:
        prev = pc
    if not prev or prev <= 0:
        return None, "no_quote"
    if now_min > CONF_END_MIN:
        return None, "no_confirm_eod"
    if now_min < CONF_START_MIN:
        return None, "wait_confirm"
    _to = _get_turnover(C, code)
    if _to is not None and _to > CONF_MAX_TURNOVER:
        return None, "skip_high_turnover"
    bars = _get_m5_bars(C, code)
    if bars is None:
        return None, "no_m5"
    today_bars = [b for b in bars if b[0] >= CONF_START_MIN]
    if not today_bars:
        return None, "wait_confirm"
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
        if c > prev * (1 + gap_lim):
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


# ================= Track B: AUCTION GATE (09:25-09:30) =================
def _get_gap_pct(C, code):
    """Call auction gap% = (open/PreClose - 1)*100. Uses 1m bar open as the
    auction price (server compute_stock_signals uses open/prev_close)."""
    try:
        pc = _get_prev_close(C, code)
        if not pc or pc <= 0:
            return None
        price, prev, open_, high = _get_quote(C, code)
        if open_ is None or open_ <= 0:
            return None
        return (open_ / pc - 1) * 100.0
    except BaseException:
        return None


def _is_sweet_zone(C, code):
    """True if this candidate's auction gap is in the P2 sweet zone (v2.4-tpl)."""
    if SWEET_ZONE_MODE <= 0:
        return False
    g = C._gap_cache.get(code)
    if g is None:
        g = _get_gap_pct(C, code)
    if g is None:
        return False
    return (SWEET_GAP_LO - 1e-9) <= g <= (SWEET_GAP_HI + 1e-9)


def _order_by_sweet(C, items):
    """Trigger-order preference (v2.4-tpl): sweet-zone candidates first within
    their tier (money_pass first / fallback). SWEET_ZONE_MODE=1 sorts (sweet
    first, others keep original order); =2 keeps only sweet-zone names."""
    if SWEET_ZONE_MODE <= 0:
        return items
    if SWEET_ZONE_MODE == 2:
        kept = [it for it in items if _is_sweet_zone(C, it["code"])]
        for it in items:
            if it["code"] not in [x["code"] for x in kept]:
                print("[SWEET] " + it["code"] + " not in sweet zone, skip (mode=2)")
        return kept
    tier = []
    rest = []
    for it in items:
        if _is_sweet_zone(C, it["code"]):
            tier.append(it)
        else:
            rest.append(it)
    return tier + rest


def _get_call_volume(C, code):
    """Auction volume (lots): first 1m bar volume. 0/None -> no valid auction."""
    today = datetime.now().strftime("%Y%m%d")
    try:
        data = C.get_market_data_ex(
            ["volume"], [code], period="1m", count=1, end_time=today,
            subscribe=True)
        if not data or not isinstance(data, dict) or code not in data:
            return None
        vols = _col(data[code], "volume")
        if not vols:
            return None
        return float(vols[0])
    except BaseException:
        return None


def _update_auction_state(C, pool, now_min):
    """Pull auction quotes for all candidates, update C._gap_cache.
    Late data (now > CALL_DATA_CUTOFF and code already has gap) updates only,
    never affects the locked _p1_survivors (decision fixed at 09:35)."""
    for it in pool:
        code = _qmt_code(it.get("symbol"))
        if not code:
            continue
        if code in C.position_map:
            continue
        g = _get_gap_pct(C, code)
        if g is not None:
            if now_min <= CALL_DATA_CUTOFF or code not in C._gap_cache:
                C._gap_cache[code] = g


def _aggregate_sector(C, pool, now_min):
    """Aggregate candidates' gaps by industry_l1, compute sector_weak.
    Cross-validation sec 6-5: aggregate on ALL constituents of candidate
    sectors (QMT local get_stock_list_in_sector) for a wider sample.
    Perf guard: constituents list cached (once per day), sampled to
    SECTOR_AGG_MAX_MEMBERS, and per-stock gap is cached in _gap_cache so a
    repeated handlebar only re-quotes stocks never seen before."""
    sym_to_sector = {}
    sectors = set()
    for it in pool:
        sym = it.get("symbol")
        sec = it.get("industry_l1") or "Other"
        if sym:
            sym_to_sector[sym] = sec
            sectors.add(sec)
    sector_gap = {}
    sector_cnt = {}
    for sec in sectors:
        if not sec:
            continue
        sec_syms = _sector_constituents(C, sec)
        if not sec_syms:
            sec_syms = [s for s in sym_to_sector if sym_to_sector[s] == sec]
        # perf: sample cap per sector (enough for a gap mean estimate)
        if len(sec_syms) > SECTOR_AGG_MAX_MEMBERS:
            sec_syms = sec_syms[:SECTOR_AGG_MAX_MEMBERS]
        gaps = []
        for s in sec_syms:
            code = _qmt_code(s)
            if not code:
                continue
            g = C._gap_cache.get(code)
            if g is None:
                g = _get_gap_pct(C, code)
                if g is not None and now_min <= CALL_DATA_CUTOFF:
                    C._gap_cache[code] = g
            if g is not None:
                gaps.append(g)
        if gaps:
            sector_gap[sec] = sum(gaps) / len(gaps)
            sector_cnt[sec] = len(gaps)
    C._sector_gap_mean = sector_gap
    C._sector_stock_cnt = sector_cnt
    return sector_gap


def _sector_constituents(C, industry_l1):
    """QMT local sector constituents. industry_l1 is the server industry name;
    try direct get_stock_list_in_sector, empty on fail (fallback to candidates).
    Result cached in C._sector_members_cache (sector membership is static
    intraday, no need to re-fetch every minute)."""
    cached = C._sector_members_cache.get(industry_l1)
    if cached is not None:
        return cached
    try:
        lst = C.get_stock_list_in_sector(industry_l1)
        if lst and isinstance(lst, (list, tuple)):
            C._sector_members_cache[industry_l1] = list(lst)
            return C._sector_members_cache[industry_l1]
    except BaseException:
        pass
    C._sector_members_cache[industry_l1] = []
    return []


def _p1_gate(C, pool, now_min):
    """P1 auction gate (09:25-09:30). Aligns server pre_market_gate.py.
    Returns survivors [{code, symbol, name, rank, industry_l1, score_0500,
    gap_pct, adj_score, action}], sorted by adj_score desc, capped P1_KEEP_TOP_N."""
    survivors = []
    sector_gap = _aggregate_sector(C, pool, now_min)
    for it in pool:
        sym = it.get("symbol")
        code = _qmt_code(sym)
        if not code:
            continue
        if code in C.position_map:
            continue
        if not _board_allowed(code):
            continue
        if _is_st_name(it.get("name")):
            print("[ST] " + code + " " + str(it.get("name")) + " skip (risk-warning)", flush=True)
            continue
        g = C._gap_cache.get(code)
        if g is None:
            g = _get_gap_pct(C, code)
            if g is not None and now_min <= CALL_DATA_CUTOFF:
                C._gap_cache[code] = g
        if g is None:
            # no auction data: keep but demote 5% (aligns server no_data rule)
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
        # rule1: near limit-up
        if g >= GAP_LIMIT_UP:
            continue
        # rule2: do not hard-kick individual gap<-2%; demote via rule4
        # rule3: gap<0 and weak sector
        if g < 0 and sector_weak:
            continue
        # rule4: demote
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
        # rule5: keep + bonus
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

    # sector diversity (Top10<=2, Top20<=3, pool<=5)
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
    C._p1_survivors = kept
    return kept


def _live_pool_survivors(C, pool):
    """Map server fullpool_live rows to Track B internal survivor items.

    Server already applied the full 106-d factor + money + research gates and
    sorted money_flow_pass first. We trust that ordering (plus sector
    diversity already applied server-side by live_momentum_scanner)."""
    out = []
    for it in pool:
        sym = it.get("symbol")
        code = _qmt_code(sym)
        if not code:
            continue
        if not _board_allowed(code):
            continue
        if _is_st_name(it.get("name")):
            print("[ST] " + code + " " + str(it.get("name")) + " skip (risk-warning)", flush=True)
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


def _p2_gate(C, survivors, now_min):
    """P2 money gate (09:30-09:35). Aligns server money_flow_gate.py.
    Returns survivors sorted (money_pass desc, score desc).

    Live-pool mode (C.live_pool_active, 09:36 server rerank): each candidate
    carries the server-computed full 106-d factor + money + research gate
    result (money_flow_pass / research_tier / score = 0.6*pipeline + 0.4*
    live momentum z). We trust those gates directly (that is the point of the
    live pool - QMT-side can't re-run the 106-d pipeline) and only keep the
    QMT-side real-time ABR as a soft re-check. The P2 dynamic confirm
    (_p2_decide) still runs per-candidate in _check_buy as the final trigger.

    Classic-pool mode (pre-09:36 fallback): compute QMT-side gates as before.
    """
    out = []
    live_mode = bool(getattr(C, "live_pool_active", False)) and USE_SERVER_GATES
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
                abr = _get_active_buy_ratio(C, code)
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
        # active buy ratio (only continuous session, 09:30+)
        if now_min >= GATE_START_MIN:
            abr = _get_active_buy_ratio(C, code)
            if abr is not None:
                it["active_buy_ratio"] = round(abr, 4)
                if abr < MIN_ACTIVE_BUY:
                    money_pass = False
                    notes.append("abr<%.2f" % MIN_ACTIVE_BUY)
            else:
                it["active_buy_ratio"] = None
            src, _age = _get_active_buy_from_mootdx(code)
            it["abr_src"] = "mootdx" if src is not None else "l1"
        # turnover
        to = _get_turnover(C, code)
        if to is not None:
            it["turnover"] = round(to, 2)
            if not (MIN_TURNOVER <= to <= MAX_TURNOVER):
                money_pass = False
                notes.append("to=%s" % round(to, 2))
        # volume ratio
        vr = _get_volume_ratio(C, code)
        if vr is not None:
            it["volume_ratio"] = round(vr, 2)
            if vr < MIN_VOL_RATIO:
                money_pass = False
                notes.append("vr<%.2f" % MIN_VOL_RATIO)
        # daily drop
        chg = _get_daily_change(C, code)
        if chg is not None:
            it["change_pct"] = round(chg, 2)
            if chg < MAX_DROP_PCT:
                money_pass = False
                notes.append("chg<%.1f" % MAX_DROP_PCT)
        # main 5d net inflow (fullpool pre-filled; ==0 missing -> skip hard gate)
        m5 = float(it.get("main_net_5d") or 0)
        it["main_net_5d"] = round(m5, 2)
        it["money_pass"] = bool(money_pass)
        it["gate_notes"] = ";".join(notes)
        out.append(it)
    # sort: money_pass first, then score_0500 desc (aligns select_top_by_score)
    out.sort(key=lambda x: (not x.get("money_pass"), 1 if x.get("live_retail_chase") else 0, -x["score_0500"]))
    return out


def _dump_gate(C, today, pool, p1, p2):
    """Persist gate detail (debug)."""
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
        print("[GATE] dump " + today + " pool=" + str(len(pool)) +
              " p1=" + str(len(p1)) + " top=" + str(len(p2)))
    except BaseException:
        pass


# ================= SELL (same as Track A v2.12) =================
def _check_sell(C, now, now_min, today):
    for code, pos in list(C.position_map.items()):
        if pos.get("pending"):
            continue
        price, prev, open_, high = _get_quote(C, code)
        if price is None or price <= 0 or pos.get("buy_price", 0) <= 0:
            continue
        pc = _get_prev_close(C, code)
        if pc:
            prev = pc
        cost = pos["buy_price"]
        ret = (price / cost - 1) * 100
        daily = (price / prev - 1) * 100 if prev and prev > 0 else 0.0
        if price > pos.get("today_high", 0):
            pos["today_high"] = price
        if price > pos.get("peak", cost):
            pos["peak"] = price

        if daily <= ANOMALY_PCT:
            print("[WARN] " + code + " daily=" + str(round(daily, 1)) +
                  "% anomaly, hold")
            continue
        if daily <= LIMIT_DOWN_PCT:
            _do_sell(C, code, pos, price,
                     "limit_down daily=" + str(round(daily, 1)) + "%")
            continue

        bd = pos.get("buy_date", "")
        is_today_buy = (bd == today)
        if is_today_buy:
            continue  # T+1

        if (not pos.get("wy_bc_armed") and now_min >= VWAP_CONFIRM_MIN and
                _wyckoff_holding_bc(C, code, pos.get("peak", cost))):
            pos["wy_bc_armed"] = True
            print("[BC] " + code + " holding buy-climax px=" +
                  str(round(price, 2)) + " peak=" + str(round(pos.get("peak", 0), 2)))
        if pos.get("wy_bc_armed") and VWAP_SELL_START <= now_min <= VWAP_SELL_END:
            _do_sell(C, code, pos, price, "wyckoff_bc " +
                     str(round(ret, 1)) + "%")
            continue

        if not pos.get("vwap_broken") and now_min >= VWAP_CONFIRM_MIN:
            vw = _day_vwap(C, code)
            if vw and vw > 0 and price < vw:
                pos["vwap_broken"] = True
                pos["vwap_ref"] = vw
                print("[VWAP] " + code + " day-vwap broken px=" +
                      str(round(price, 2)) + " vwap=" + str(round(vw, 2)) +
                      " ret=" + str(round(ret, 1)) + "%")
        # v2.5-tpl: next-morning confirm. Unconditional next-open sell sold the
        # day's low on all 3 real triggers (QMT sim 08-31). Sell only if the
        # live price is still below the recorded reference; recover -> cancel.
        if pos.get("vwap_broken") and VWAP_SELL_START <= now_min <= VWAP_SELL_END:
            vref = float(pos.get("vwap_ref") or 0)
            if vref > 0 and price >= vref:
                pos["vwap_broken"] = False
                pos["vwap_ref"] = 0
                print("[VWAP] " + code + " recovered px=" +
                      str(round(price, 2)) + " ref=" + str(round(vref, 2)) +
                      " cancel weak-early")
            else:
                _do_sell(C, code, pos, price, "vwap_weak_early " +
                         str(round(ret, 1)) + "%")
                continue

        hs, ta, pb = _adaptive_params(C, code)
        if now_min >= T2_FORCE_HHMM and ret <= hs * 100:
            _do_sell(C, code, pos, price,
                     "hard_stop " + str(round(ret, 1)) + "% vs " +
                     str(round(hs * 100, 1)) + "%")
            continue
        if now_min >= T2_FORCE_HHMM:
            hold_days = _hold_days(pos, today)
            if pos.get("t2_extended"):
                # already extended: force-sell at maturity (hold_days >= T2_EXTEND_MAX_DAYS)
                # only. v1.7 fix: the old code sold on the very next 14:45 pass, so
                # T2_EXTEND_MAX_DAYS=3 bought just 1 extra day instead of the intended
                # T+3. Inside the window the position keeps running with the trailing
                # peel / vwap_weak_early / wyckoff_bc exits still armed.
                # v1.8: hold_days == 999 means buy_date is unknown (never extended
                # without one), so never treat it as past maturity.
                if hold_days != 999 and hold_days >= T2_EXTEND_MAX_DAYS:
                    _do_sell(C, code, pos, price,
                             "t2_force_after_extend " + str(round(ret, 1)) + "%")
                    continue
            else:
                # v1.6: dynamic floor instead of fixed 0%. A wide-amplitude / high-vol
                # name tolerates a deeper normal pullback (300591 08-19: filled 8.54
                # on a 7.88 trigger -> -8.7% vs cost but -1% from trigger; the fixed
                # 0% floor force-sold it next day at 14:45). Floor widens with the
                # day's range and annual vol; hard_stop (hs) still owns the tail.
                force_floor = _t2_force_floor(C, code) * 100
                if ret < force_floor:
                    # loss beyond the dynamic floor -> force sell
                    _do_sell(C, code, pos, price,
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
                # v1.8: hold_days == 999 (buy_date unknown) must not be read as
                # "past maturity" and force-sell a fresh winner; only the true
                # hold-cap or a hard-stop loss can end it.
                if ((hold_days != 999 and hold_days >= T2_EXTEND_MAX_DAYS)
                        or ret <= hs * 100):
                    _do_sell(C, code, pos, price,
                             "t2_force_after_extend " + str(round(ret, 1)) + "%")
                    continue
                pos["t2_extended"] = True
                print("[EXT] " + code + " extend px=" + str(round(price, 2)) +
                      " cost=" + str(round(cost, 2)) +
                      " ret=" + str(round(ret, 1)) + "% hold_days=" + str(hold_days))

        if ret >= ta * 100:
            pos["trail_armed"] = True
        elif ret < 0:
            pos["trail_armed"] = False
            pos["awaiting_new_high"] = False

        if (pos.get("trail_armed") and not pos.get("awaiting_new_high")
                and now_min >= 9 * 60 + 31):
            peak = pos["peak"]
            pbk = (peak - price) / peak * 100 if peak > 0 else 0.0
            if pbk >= pb * 100:
                n = pos.get("peel_count", 0)
                if n >= PEEL_MAX_STEPS or pos["shares"] < 200:
                    _do_sell(C, code, pos, price,
                             "peel_clear pk=" + str(round(peak, 2)) +
                             " pb=" + str(round(pbk, 1)) + "%")
                    continue
                _do_sell_half(C, code, pos, price,
                              "peel_half" + str(n + 1) +
                              " pk=" + str(round(peak, 2)) +
                              " pb=" + str(round(pbk, 1)) + "%")
                pos["peel_count"] = n + 1
                pos["awaiting_new_high"] = True
                pos["peel_peak_snapshot"] = peak

        if (pos.get("awaiting_new_high") and
                pos.get("peak", 0) > pos.get("peel_peak_snapshot", 0) + 1e-9):
            pos["awaiting_new_high"] = False
    _save_pos_state(C)


# ============ Sell-side rework v1.5: T+2 conditional + dynamic weakness rotation (2026-08-18) ============
def _hold_days(pos, today):
    """Holding days from buy_date -> today (buy day excluded). buy_date is %Y%m%d
    (e.g. 20260818). Compatible with 'YYYY-MM-DD'. 999 on missing/unparseable.
    v2.6-tpl: counts TRADING days (weekends + 2026 A-share closures excluded),
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


def _weakness_score(C, today):
    """Weakness score 0~1 per holding, higher = more likely to sell. Only
    sellable positions are scored (not pending, held >= ROTATION_MIN_HOLD_DAYS).
    Relative-rank normalized (0~1) + momentum guard (daily > 3% and rising vol
    -> skip). Returns (all_cands_sorted, sellable)."""
    cands = []
    for code, p in list(C.position_map.items()):
        if p.get("pending"):
            continue
        if _hold_days(p, today) < ROTATION_MIN_HOLD_DAYS:
            continue
        price, prev, open_, high = _get_quote(C, code)
        if price is None or price <= 0 or float(p.get("buy_price") or 0) <= 0:
            continue
        pc = _get_prev_close(C, code)
        if pc:
            prev = pc
        pret = (price / float(p["buy_price"]) - 1) * 100
        pday = (price / prev - 1) * 100 if prev and prev > 0 else 0.0
        vw = _day_vwap(C, code)
        vwap_break = 1.0 if (vw and price < vw) else 0.0
        early = 1.0 if (p.get("wy_bc_armed") or p.get("vwap_broken")) else 0.0
        peel = 1.0 if (p.get("peel_count") or 0) > 0 else 0.0
        days = _hold_days(p, today)
        cands.append({
            "code": code, "pos": p, "ret": pret, "day": pday,
            "vwap_break": vwap_break, "early": early, "peel": peel,
            "days": days, "skip": False,
        })
    if not cands:
        return [], []
    # momentum guard: daily > ROTATION_MOMENTUM_DROP_PCT and vol-ratio above threshold -> skip
    for it in cands:
        vr = _get_volume_ratio(C, it["code"])
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


def _rotation_sell(C, now, now_min, today, need_n):
    """When holdings are full (MAX_HOLDINGS) and a new candidate passed P2, sell the
    weakest position to free a slot. Prefers peel half (when profitable), else
    full sell. Returns the codes actually sold. _do_sell/_do_sell_half pop
    C.position_map on success, so the caller can buy immediately after."""
    if not ROTATION_ENABLE:
        return []
    if _order_locked(today, "__ROT__", "rot"):
        print("[ROT] daily cap " + str(ROTATION_DAILY_MAX) +
              " reached, skip")
        return []
    cands, sellable = _weakness_score(C, today)
    if not sellable:
        print("[ROT] no sellable holdings (min_hold=" +
              str(ROTATION_MIN_HOLD_DAYS) + ")")
        return []
    w = sellable[0]
    if (ROTATION_WEAK_GATE and not
            (w["day"] < 0 or w["vwap_break"] == 1.0
             or w["early"] == 1.0 or w["ret"] < 0)):
        print("[ROT] skip: weakest " + w["code"] +
              " still healthy (no weakness signal), no churn")
        return []
    sold = []
    for it in sellable[:need_n]:
        code = it["code"]
        if code in C.position_map and not C.position_map[code].get("pending"):
            price, prev, open_, high = _get_quote(C, code)
            pos = C.position_map[code]
            ret = (price / float(pos["buy_price"]) - 1) * 100 if price else 0
            if (ret > 0 and (pos.get("peel_count") or 0) < PEEL_MAX_STEPS
                    and int(pos.get("shares") or 0) >= 400):
                _do_sell_half(C, code, pos, price,
                              "rotation_peel ret=" + str(round(ret, 1)) + "%")
            else:
                _do_sell(C, code, pos, price,
                         "rotation_sell ret=" + str(round(ret, 1)) + "%")
            sold.append(code)
            _mark_order_locked(today, "__ROT__", "rot")
            print("[ROT] sell " + code + " weakness=" +
                  str(round(it.get("score", 0), 2)))
    return sold


def _sell_lock_key(reason):
    if not reason:
        return "SELL"
    tok = str(reason).split(" ")[0]
    if tok.startswith("t2_force"):
        return "t2_force"
    return tok


def _do_sell(C, code, pos, price, reason):
    vol = pos.get("shares", 0)
    can_use = pos.get("can_use", vol)
    if can_use < vol:
        print("[SELL] " + code + " cap " + str(vol) + " -> " + str(can_use) +
              " (can_use, T+1)")
        vol = can_use
    if vol <= 0 or vol > 999999:
        return
    today = datetime.now().strftime("%Y%m%d")
    lockk = _sell_lock_key(reason)
    if _order_locked(today, code, lockk):
        print("[LOCK] skip sell " + code + " " + lockk +
              " (already ordered today)")
        return
    print("[SELL] " + code + " " + reason + " all " + str(vol) +
          "sh @ " + str(round(price, 2)))
    try:
        ret = passorder(24, 1101, ACCOUNT_ID, code, 5, -1, vol,
                        "auction_b", 1, "", C)
        if ret != 0:
            print("[SELL] " + code + " " + reason + " all " + str(vol) +
                  "sh order REJECTED ret=" + str(ret) + " (no lock, retry)")
            return
        _mark_order_locked(today, code, lockk)
    except BaseException as e:
        print("[SELL] order fail: " + str(e))
        return
    _log_trade(C, "SELL", code, price, vol, reason)
    C.position_map.pop(code, None)
    C.stop_watch.pop(code, None)
    _save_pos_state(C)


def _do_sell_half(C, code, pos, price, reason):
    shares = pos.get("shares", 0)
    can_use = pos.get("can_use", shares)
    if can_use < shares:
        print("[SELL] " + code + " cap " + str(shares) + " -> " + str(can_use) +
              " (can_use, T+1)")
        shares = can_use
    if shares <= 0:
        print("[SELL] " + code + " skip " + reason + " no tradable shares (T+1)")
        return
    half = max(100, (shares // 2 // 100) * 100)
    if half <= 0 or half >= shares:
        _do_sell(C, code, pos, price, reason + " (half>=all)")
        return
    today = datetime.now().strftime("%Y%m%d")
    lockk = _sell_lock_key(reason)
    if _order_locked(today, code, lockk):
        print("[LOCK] skip sell-half " + code + " " + lockk +
              " (already ordered today)")
        return
    print("[SELL] " + code + " " + reason + " half " + str(half) +
          "sh @ " + str(round(price, 2)))
    try:
        ret = passorder(24, 1101, ACCOUNT_ID, code, 5, -1, half,
                        "auction_b", 1, "", C)
        if ret != 0:
            print("[SELL] " + code + " " + reason + " half " + str(half) +
                  "sh order REJECTED ret=" + str(ret) + " (no lock, retry)")
            return
        _mark_order_locked(today, code, lockk)
    except BaseException as e:
        print("[SELL] order fail: " + str(e))
        return
    pos["shares"] = shares - half
    pos["can_use"] = max(0, can_use - half)
    _log_trade(C, "SELL_HALF", code, price, half, reason)
    _save_pos_state(C)


# ================= BUY (Track B: 09:35 Top2 order) =================
def _check_buy(C, now, now_min, today, pool):
    if len(C.position_map) >= MAX_HOLDINGS:
        return
    acct = None
    cash = 0.0
    total_asset = 0.0
    try:
        acct = get_trade_detail_data(ACCOUNT_ID, "STOCK", "ACCOUNT") or []
        if acct:
            cash = float(getattr(acct[0], "m_dAvailable", 0) or 0)
            total_asset = float(getattr(acct[0], "m_dBalance", 0) or 0)
    except BaseException as e:
        cash = 0.0
        print("[CASH] acct query fail acct=" + ACCOUNT_ID +
              " err=" + str(e)[:80])
    if cash <= 0:
        if C.run_count % 60 == 0:
            print("[CASH] cash=" + str(cash) + " acct=" + ACCOUNT_ID)
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
        return

    # ---- Track B gate flow ----
    # 09:25-09:30: P1 auction gate (update gap / sector / survivors)
    # 09:30-09:35: P2 money gate
    # 09:35:       pick Top2 and order
    if now_min < AUCTION_START_MIN:
        return
    if C._top2_fired:
        return

    if now_min < CALL_DATA_CUTOFF:
        _update_auction_state(C, pool, now_min)
        _p1_gate(C, pool, now_min)
        if not C._auction_done:
            print("[AUCTION] " + today + " gap_cache=" +
                  str(len(C._gap_cache)) + " p1_survivors=" +
                  str(len(C._p1_survivors)))
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
        if not C._top2_fired:
            print("[BUY] skip: outside buy window (am 09:36-11:30 / pm 13:00-14:00)" +
                  " now=" + str(now_min))
        C._top2_fired = True
        return

    # decision: if P1 survivors not fixed yet (e.g. no data before 09:30), re-run
    if not C._p1_survivors:
        _update_auction_state(C, pool, now_min)
        _p1_gate(C, pool, now_min)

    # live pool (server 09:36 rerank) overrides the classic P1 survivors
    if getattr(C, "live_pool_active", False) and USE_SERVER_GATES:
        live_surv = _live_pool_survivors(C, pool)
        if live_surv:
            C._p1_survivors = live_surv
            C._live_surv_ready = True
            print("[LIVE] server rerank pool n=" + str(len(live_surv)) +
                  " money_pass=" +
                  str(sum(1 for x in live_surv if x.get("money_flow_pass"))))

    p2 = _p2_gate(C, C._p1_survivors, now_min)
    if not C._gate_dump_done:
        _dump_gate(C, today, pool, C._p1_survivors, p2)
        C._gate_dump_done = True

    # Walk ranked candidates high->low: money_pass first, then the rest by
    # score_0500 desc (already sorted by _p2_gate). Buy every stock that
    # passes the P2 dynamic confirm until MAX_DAILY_BUY is filled or the
    # candidate list is exhausted. This "rolls forward" to the next passing
    # name when the top pick's money gate / P2 confirm fails.
    picked = ([it for it in p2 if it.get("money_pass")] +
              [it for it in p2 if not it.get("money_pass")])
    # v2.4-tpl: sweet-zone trigger priority within each tier
    picked = (_order_by_sweet(C, [it for it in p2 if it.get("money_pass")]) +
              _order_by_sweet(C, [it for it in p2 if not it.get("money_pass")]))
    _pick_primary = set(it["code"] for it in p2 if it.get("money_pass"))
    for it in picked:
        if today_bought >= MAX_DAILY_BUY:
            break
        code = it["code"]
        if code in C.position_map or code in C.sent_today:
            continue
        if _order_locked(today, code, "BUY"):
            continue
        if not _board_allowed(code):
            continue
        if _is_st_name(it.get("name")):
            print("[ST] " + code + " " + str(it.get("name")) + " skip (risk-warning)", flush=True)
            C.sent_today.add(code)
            continue
        fb_ok, fb_abandon = _fallback_buy_ok(it, now_min)
        if not fb_ok:
            if fb_abandon:
                rk = int(it.get("rank") or 0)
                if it.get("fund_hard_fail"):
                    print("[FALLBACK] " + code + " fund_hard_fail skip", flush=True)
                elif rk > FALLBACK_RANK_CAP_PM:
                    print("[FALLBACK] " + code + " rank=" + str(rk) +
                          " > " + str(FALLBACK_RANK_CAP_PM) + " skip", flush=True)
                C.sent_today.add(code)
            continue
        if _is_limit_up(C, code):
            print("[WAIT] " + code + " limit-up skip")
            continue
        if _wyckoff_distribution(C, code):
            print("[WYCKOFF] " + code + " distribution skip")
            continue
        # P2 dynamic confirm (post 09:35, same as Track A)
        fill, reason = _p2_decide(C, code, now_min)
        if fill is None:
            if reason in ("no_confirm_eod", "skip_high_turnover"):
                # permanent abandon: past the eod window, or turnover only
                # climbs intraday so it will never fall back under the cap.
                print("[WAIT] " + code + " P2=" + reason + " abandon")
                C.sent_today.add(code)
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
            _live = _get_last(C, code)
            if _live and _live > fill * (1 + MAX_BUY_SLIP_PCT):
                print("[BUY] " + code + " slip guard: live " +
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
        if len(C.position_map) >= MAX_HOLDINGS:
            sold = _rotation_sell(C, now, now_min, today, ROTATION_SELL_N)
            if not sold:
                print("[BUY] skip: holdings full & rotation sold nothing (" +
                      code + ")")
                continue
            # re-query cash: the rotation frees available funds immediately
            try:
                acct = get_trade_detail_data(ACCOUNT_ID, "STOCK", "ACCOUNT") or []
                if acct:
                    cash = float(getattr(acct[0], "m_dAvailable", 0) or 0)
            except BaseException:
                pass
        shares = int(total_asset * POSITION_PCT / fill / 100) * 100
        if shares < 100:
            continue
        max_cash_shares = int(cash / fill / 100) * 100
        if max_cash_shares < 100:
            continue
        shares = min(shares, max_cash_shares)
        try:
            ret = passorder(23, 1101, ACCOUNT_ID, code, 5, -1, shares,
                            "auction_b", 1, "", C)
            if ret != 0:
                print("[BUY] " + code + " x" + str(shares) +
                      " order REJECTED ret=" + str(ret) +
                      " (no lock written)")
                C.sent_today.add(code)
                continue
            C.sent_today.add(code)
            _mark_order_locked(today, code, "BUY")
            C.position_map[code] = {
                "shares": shares,
                "buy_price": fill,
                "name": it.get("name") or code,
                "buy_date": today,
                "peak": fill,
                "trail_armed": False,
                "awaiting_new_high": False,
                "peel_peak_snapshot": fill,
                "peel_count": 0,
                "t2_extended": False,
                "vwap_broken": False,
                "wy_bc_armed": False,
                "pending": False,
                "today_high": fill,
            }
            today_bought += 1
            sweet_tag = " SWEET" if _is_sweet_zone(C, code) else ""
            print("[BUY] " + code + " x" + str(shares) + " @ " +
                  str(round(fill, 2)) + " track-B auction rank=" +
                  str(it.get("rank")) +
                  (" primary" if code in _pick_primary else " fallback") +
                  sweet_tag)
            _log_trade(C, "BUY", code, fill, shares, "track_b_auction")
            _save_pos_state(C)
        except BaseException as e:
            print("[BUY] order fail: " + str(e))
            C.sent_today.add(code)
    # v1.1 (2026-08-17): only close the day's buying when the daily budget is
    # full. Otherwise keep retrying on later bars within the widened windows
    # (candidates that print wait_confirm are retried, not abandoned).
    if today_bought >= MAX_DAILY_BUY and not C._top2_fired:
        C._top2_fired = True
        print("[BUY] top2 fired | bought=" + str(today_bought) +
              " scanned=" + str([x.get("code") for x in picked])[:180])


# ================= LEDGER (same as Track A) =================
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


def _log_trade(C, action, code, price, vol, reason):
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
        if getattr(C, "_ledger_sig_ts", None) is None:
            C._ledger_sig_ts = {}
        last = C._ledger_sig_ts.get(sig, 0.0)
        if now - last < LEDGER_DUP_SEC:
            return
        C._ledger_sig_ts[sig] = now
        ledger = list(C.trade_log) + [rec]
        C.trade_log = ledger
        with open(TRADE_LOG, "w", encoding="utf-8") as f:
            json.dump(ledger, f, ensure_ascii=False)
    except Exception:
        pass


def _snap_daily(C, today, now):
    try:
        pos_list = []
        for code, pos in C.position_map.items():
            shares = int(pos.get("shares") or 0)
            cost = float(pos.get("buy_price") or pos.get("cost") or 0)
            if shares <= 0:
                continue
            px = cost
            try:
                q = _get_quote(C, code)
                if q:
                    px = float(q[0] or cost)
            except Exception:
                pass
            pl = (px - cost) * shares
            pct = (px / cost - 1) * 100 if cost > 0 else 0.0
            pos_list.append({
                "code": code, "shares": shares, "cost": round(cost, 3),
                "price": round(px, 3), "pl": round(pl, 2),
                "pl_pct": round(pct, 2),
            })
        realized = 0.0
        for tr in C.trade_log:
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
        if os.path.exists(LEDGER_DAILY):
            try:
                with open(LEDGER_DAILY, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        else:
            data = {}
        data[today] = day
        with open(LEDGER_DAILY, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        print("[LEDGER] snapshot " + today + " pos=" + str(len(pos_list)) +
              " unreal=" + str(day["unrealized_pl"]))
    except Exception:
        pass


# =========================================================
# >>> HOW TO USE THIS TEMPLATE (one copy per LIVE account) <<<
# =========================================================
# 1) Copy this file for each live account you manage.
# 2) In the CONFIG block at the top, set:
#      ACCOUNT_ID   -> that account's fund account id (as shown in QMT)
#      ACCOUNT_TAG  -> short ASCII tag, e.g. "alice"; used ONLY in local
#                      file names so accounts never share ledger/lock files
#      ALLOW_STAR / ALLOW_CHINEXT / ALLOW_BSE -> board access for that account
#      POSITION_PCT / MAX_HOLDINGS / MAX_DAILY_BUY -> per-account risk
# 3) Deploy the PLAINTEXT file into that account's QMT python dir:
#      <QMT install>\python\<strategy file name>.py
#    IMPORTANT: never open/save it in the QMT editor (it re-encodes to GBK
#    and encrypts the file, which can corrupt UTF-8 and raise SyntaxError).
#    Keep it plaintext on disk; QMT runs plaintext files fine.
# 4) In QMT, create a strategy pointing at that python file and start it.
# 5) Check the log prints "[INIT] track-B v1.9-tpl ... acct=<ACCOUNT_ID>".
#
# Per-account local files (auto-created):
#   C:\alphapilot\<ACCOUNT_TAG>_trades_fullchain.json  - trade journal
#   C:\alphapilot\<ACCOUNT_TAG>_ledger_daily.json      - end-of-day snapshots
#   C:\alphapilot\<ACCOUNT_TAG>_order_locks.json       - daily order locks
#   C:\alphapilot\<ACCOUNT_TAG>_auction_gate.json      - gate detail (debug)
#
# fullpool is shared from the server: SCORE_DIR (local copy) or
# REMOTE_SCORE_BASE (nginx) -- no per-account setup needed.
#
