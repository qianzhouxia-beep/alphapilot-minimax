# -*- coding: utf-8 -*-
# AlphaPilot full-chain strategy - Track A TDX sim (TongDaXin TdxQuant port)
# File: TrackA_track_a_tdx_full_chain_sim.py
# v2.29 2026-09-02 (vwap 2nd confirm, aligned with QMT v2.30):
#   * vwap_weak_early needs TWO still-below minutes in 09:35-09:50.
#     First tick only arms; later minute still below vwap_ref sells.
# v2.28 2026-09-01 (rotation off, aligned with QMT v2.29):
#   * ROTATION_ENABLE=False. rank<=2 buys ~1/day so the weakest-name kick-out
#     is no longer needed and caused white-sells. Helpers kept; switch off.
# v2.27 2026-09-01 (rank<=2 P2 gate, aligned with QMT v2.28):
#   * MAX_CAND_RANK=2: only 09:35 candidates.json rank 1-2 may enter P2
#     (incl. rotation worth_buy). Rank 3+ never race. Missing rank skipped.
#     P2 itself unchanged. Evidence: 22 settled days 2026-07-27~08-31,
#     rank<=2 T+1 +1.62% t=2.14 vs rank<=10 +0.67%.
# v2.26 2026-08-31 (trading-day hold fix, aligned with QMT v2.27):
#   * _hold_days counts TRADING days, not calendar days. The old
#     (today - buy_date).days counted weekends/holidays, so a Friday buy read
#     as hold=3 on the following Monday (real T+1) and wrongly hit
#     t2_force_after_extend / rotation_sell. New _ASHARE_CLOSED_2026 set +
#     _trading_days_between(); only weekend + 2026 official closures excluded.
# v2.25 2026-08-31 (vwap_weak_early next-morning confirm, aligned with QMT v2.26):
#   * Sell at next open only if the live price is still BELOW the day-VWAP
#     reference recorded when the signal armed (price < vwap_ref). If the price
#     has recovered above the reference, cancel the signal and keep holding.
#     Evidence (QMT sim 08-31, n=3): unconditional next-open sell hit the day's
#     low and all three rallied +3.5%/+3.8%/+7.0%. New persisted field vwap_ref.
# v2.24 2026-08-29 (P2 sweet-zone trigger priority, aligned with QMT v2.25)
# v2.22 2026-08-27 (pos state persistence across TDX restarts, aligned with QMT v2.23)
# v2.23 2026-08-28 sell jsonl falls back to {buy_date}.candidates.json
# v2.22+ 2026-08-28 stamp fusion_scores on buy; append IC closed-trade on sell
# v2.21 2026-08-26 (fund_hard_fail client buy guard, aligned with QMT v2.22)
# v2.20 2026-08-26 (P2 dynamic session-low trend: c>day_low, drop p935/prev_close guards)
# v2.19 2026-08-26 (P2 board-aware gap + day-high guard, aligned with QMT v2.20)
# v2.18 2026-08-21 (TDX 5m field-name fix: get_market_data uses lowercase
# open/close/high/low/volume; empty 5m replies are cached so tqcenter does
# not spam 'field Open not in result' every bar)
# v2.17 2026-08-20 (T+1 winner force-sell fix: _today_buy_date recovers buy_date
# from the trade log after a restart; _check_sell T+2 maturity guards 999.
# Head changelog rewritten pure ASCII for the deploy hard rule)
# v2.16 2026-08-19 (Kimi 3 cross-validation fixes: t2_force floor no longer
# short-circuited by vwap_broken/wy_bc_armed; t2_extended held to T2_EXTEND_MAX_DAYS)
# v2.15 2026-08-19 (dynamic t2_force floor + buy slip guard, aligned with QMT v2.17)
# v2.14 2026-08-18 (DHS review: rotation protection + daily cap + hysteresis, aligned with QMT v2.16)
# =========================================================
# TongDaXin TdxQuant (TQ) full-chain strategy:
#   - reads C:\alphapilot\scores\{YYYYMMDD}.json server picks
#   - falls back to direct fetch from server nginx when local file missing
#     (Plan A, same as QMT v2.2)
#   - P2 dynamic confirm buy of top candidates (full: p935+VWAP trend /
#     vol-ratio / no-chase / turnover gate); auto-degrades to snapshot confirm
#     when minute bars are unavailable (live > prev close & > vwap & 5min up)
#   - adaptive stop-loss / peel scale-out / T+2 force-close / VWAP weak early
#     exit / limit-down protection sells (same as QMT v2.3)
#   - auto ledger (per-trade + daily snapshot) + file-level order locks
#   - board permission filter (ALLOW_STAR / ALLOW_CHINEXT / ALLOW_BSE per acct)
#
# v2.14 changes vs v2.13 (2026-08-18, DSH sell-side review landed):
#   * Rotation protection period: T+0/T+1 holdings are immune to rotation
#     (ROTATION_MIN_HOLD_DAYS 1 -> 2); only T+2+ positions may be rotated out.
#   * Daily rotation cap ROTATION_DAILY_MAX=1 (limit churn & fees).
#   * Hysteresis (ROTATION_WEAK_GATE): only rotate when the weakest holding shows
#     a concrete weakness signal (day down / below day-VWAP / early-exit / underwater);
#     do not churn healthy positions.
# v2.13 changes vs v2.12 (2026-08-18, DHS sell-side eval P0+P1, aligned with QMT v2.15):
#   * T+2 force-close is now conditional: loss (ret<0) force-sell; profit without
#     an early-exit signal extends to T+3 (T2_EXTEND_MAX_DAYS), replacing the old
#     blanket price>=cost*0.95 extension. peel stays armed as a backstop.
#   * Dynamic weakness rotation (P1): when holdings are full (MAX_HOLDINGS) and a
#     candidate passed P2, first evaluate the candidate (P2 gated first, never sell
#     a good old position for a weak one), then sell the weakest 1 to free a slot,
#     buy the new name on the same bar. Weakness score = ret30% + vwap20% + day20%
#     + early15% + peel10% + days-to-T2 5%, relative-rank normalized, momentum
#     guard (day>3% and vol-ratio>1.3 -> skip).
#   * New helpers: _hold_days/_closed_5m_bars/_volume_ratio_of/_weakness_score/_rotation_sell.
# v2.12 changes vs v2.11 (2026-08-18, P2 day-trend guard):
#   * _p2_decide bars main path adds a day-trend guard: c < prev_close is skipped
#     directly, matching the snapshot fallback path (price > prev_close), aligned
#     with QMT v2.14 / TrackB. Avoids buying a falling stock on polluted history
#     or an intraday rebound.
# v2.11 changes vs v2.10 (2026-08-16, ABR gate aligned with QMT v2.13):
#   * ABR (active-buy ratio) gate: after P2 fires, during continuous auction
#     (>=09:30) check the bid1/ask1 depth volume ratio (TDX has no tick data, so
#     snapshot approximation, same as Track B TDX). Backtest (2026-08, 114 cands):
#     cumulative ABR>=0.52 lifts T+1 win rate 42.3% -> 54.2%, T+1 avg return
#     -0.46% -> +0.36%.
#   * Soft gate: ABR data unavailable (snapshot depth missing / outside trading)
#     -> do not block. ABR below MIN_ACTIVE_BUY -> P2 returns skip_low_abr, the
#     candidate is dropped for the day.
# v2.10 changes vs v2.9 (2026-08-13, silent no-buy ROOT CAUSE):
#   * order_stock return-value check: TDX order_stock returns -1 (int) or a dict
#     with ErrorId != 0 when rejected, it does not raise. Old code ignored the
#     return value and wrote the BUY lock anyway, so today_bought was consumed by
#     a fake lock and _check_buy silently broke (today_bought >= MAX_DAILY_BUY)
#     before iterating candidates -> no buys all day. Now rejected orders write no
#     lock, log [BUY] REJECTED, mark sent_today and continue.
#   * today_bought >= MAX_DAILY_BUY now logs ([BUY] today_bought=.. skip all)
#     instead of staying silent.
#   * INIT prints that day's order_locks summary ([LOCK] today BUY locks=.. detail=..)
#     so leftover locks blocking buys are easy to find.
# v2.9 changes vs v2.8 (2026-08-13, TDX no-buy ROOT CAUSE fixed):
#   * _check_buy today_bought now counts real BUY orders from order_locks (aligned
#     with QMT v2.9) instead of counting buy_date entries in position_map.
#   * _sync_positions no longer fills old positions' buy_date with today by default:
#     only when TDX TodayBuyPosition>0 (real same-day fills) is buy_date=today set,
#     otherwise keep the in-memory value or leave blank. (Old bug: at startup 2 old
#     positions were counted as bought today, today_bought=2 hit MAX_DAILY_BUY=2,
#     _check_buy silently broke, never ordered again)
#   * New helper: _today_buy_date.
# v2.8 changes vs v2.7 (2026-08-13, TDX no-buy diagnosis):
#   * _fetch_remote_scores: makedirs / urllib import failures no longer silent, log.
#   * _load_scores / _load_candidates: when a local file exists but fails to parse
#     (0 bytes / corrupt / GBK garbage), delete the bad file and force re-fetch
#     (self-heal) so a bad file cannot stall buys.
#   * _build_cands: log on both success and failure ([CAND] n= / [CAND] none).
#   * _query_cash: tolerate TDX return shapes (Cash|Balance / Asset|TotalAssets /
#     Value nesting), log on empty result / exception; no longer silently returns 0.
#   * _check_buy: log when cash<=0 ([BUY] skip: cash=) instead of silent.
# v2.7 2026-08-12 (aligned with QMT full-chain v2.10)
# v2.6 changes vs v2.5 (2026-08-12, sync QMT v2.6-v2.8):
#   * Main loop adds bar-level protection: _check_sell / _check_buy each wrapped in
#     its own try/except BaseException; a sell-side error no longer blocks buys in
#     the same cycle (aligned with QMT v2.6).
#   * All tq.* data/order calls wrapped in BaseException guards so a non-standard
#     data-layer exception cannot crash the whole loop (aligned with QMT v2.7).
# v2.5 changes vs v2.4 (2026-08-11, sync QMT v2.4):
#   * Board permission filter: accounts without STAR/CHINEXT/BSE permission skip the
#     corresponding candidates and take the next one, avoiding wasted orders eating
#     buy slots.
# v2.4 changes vs v2.3 (2026-08-11, sync QMT v2.3):
#   * CONF_MAX_GAP 0.05 -> 0.08 (no-chase relaxed, validated in QMT v2.3 backtest)
#   * VWAP weak-early exit: day2 close (>=14:45) below the day VWAP flags it, day3
#     open (09:35-09:50) sells. Backtest maxDD -29.6% -> -21.8%. Day VWAP prefers
#     snapshot Average (intraday available), falls back to 5m-bar computation.
#   * File-level order locks (tdx_order_locks.json): prevent duplicate orders after
#     process restart / multiple instances.
# v2.3 changes vs v2.2 (2026-08-11):
#   * Live price / prev close now prefer get_market_snapshot (Now/LastClose) instead
#     of relying on 1m K-lines -> fixes P2=no_quote when the client has no minute bars.
#   * P2 confirm: full path when 5m bars are available; snapshot fallback (Now>prev,
#     Now>avg, 5-min strength, no-chase, turnover gate) when the client lacks minute data.
#   * Turnover gate prefers snapshot Volume(hand)*100 / circulating shares.
#
# How to run:
#   1) Start TongDaXin "Financial Terminal (quant sim)" and log into the sim account
#   2) Strongly recommended: System - After-hours data download, check 1min/5min bars
#      (needed for full P2 confirmation)
#   3) Set ACCOUNT below to your TDX sim capital account (blank auto-uses logged-in)
#   4) python TrackA_track_a_tdx_full_chain_sim.py
# =========================================================
from __future__ import print_function

import os
import sys

# ---- tqcenter auto-locate (2026-08-12) -----------------------------
# The TdxQuant library lives under the TDX install dir's PYPlugins\user.
# Before importing tqcenter, probe the usual install locations so the
# script runs no matter how Python is launched (cmd, IDE, scheduler, or
# another machine with a different TDX root).
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
    # also scan drives' first-level dirs for *PYPlugins\user
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
    sys.stderr.write("  run the script from inside the TDX quant PYPlugins\\user dir\n")
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
ACCOUNT = "1190388433"  # TDX SIM capital account (empty = auto use logged-in)
SCORE_DIR = r"C:\alphapilot\scores"
REMOTE_SCORE_BASE = "http://150.158.100.236/qmt_scores"  # server nginx static dir
REMOTE_FETCH_SEC = 60         # min interval between remote fetch attempts
REMOTE_TIMEOUT = 8            # seconds per remote fetch
REMOTE_FETCH_START_MIN = 9 * 60  # don't try remote before 09:00 (server not ready)
TRADE_LOG = r"C:\alphapilot\tdx_trades.json"
LEDGER_DAILY = r"C:\alphapilot\tdx_ledger_daily.json"
LOG_FILE = r"C:\alphapilot\tdx_full_chain.log"

MAX_HOLDINGS = 4
MAX_DAILY_BUY = 2
MAX_CAND_RANK = 2              # only 09:35 candidates.json rank 1-2 may enter P2; 0=off
POSITION_PCT = 0.22

# --- P2 dynamic confirm params (aligned with QMT v2.3) ---
CONF_VOL_RATIO = 1.3          # 5m volume ratio threshold
CONF_MAX_GAP = 0.08           # legacy uniform cap (superseded by _p2_max_gap)
CONF_DAY_HIGH_MAX = 0.85      # skip if (c-low)/(high-low) > 0.85 (top 15% of range)
                              # (QMT v2.3: 2026-04~07 P2 stats, 8% blocks
                              #  extremes without killing the 5-6% band)
CONF_START_MIN = 9 * 60 + 35  # observation window start 09:35
CONF_END_MIN = 14 * 60 + 57   # observation window end 14:57
CONF_MAX_TURNOVER = 5.0       # max daily turnover % (backtest: >5% weakens)

# --- P2 sweet-zone priority (v2.24, 2026-08-29, aligned with QMT v2.25) ---
# P2 triggers with open gap in [-1.5%, 0] (slight low-open) show upward-bias
# T+1 vs the rest (BT 2026-04~07 + real 07~08). Trigger-order preference only:
# sweet-zone candidates get priority when racing for the daily buy slots.
#   SWEET_ZONE_MODE 0 = off (status quo)
#                    1 = priority (sweet first, non-sweet still fill)
#                    2 = only (strictly sweet-zone, fewer trades)
SWEET_ZONE_MODE = 1
SWEET_GAP_LO = -1.5           # sweet zone = gap% in [LO, HI]
SWEET_GAP_HI = 0.0

# --- ABR (active-buy ratio) gate v2.11 (Level-2 style, TDX snapshot approx) ---
# Backtest 2026-08 (114 candidates / 20 days real Top10): cumulative ABR >=
# 0.52 at the P2 trigger lifts T+1 winrate 42.3% -> 54.2%, T+1 mean -0.46% ->
# +0.36%. TDX has no per-tick buy/sell direction, so use snapshot order-book
# ratio Buy1Vol/(Buy1Vol+Sell1Vol) (same approx as Track B TDX). SOFT gate:
# ABR unavailable -> pass, so a quote quirk never blocks buying.
USE_ABR_GATE = True
MIN_ACTIVE_BUY = 0.52
ABR_GATE_START_MIN = 9 * 60 + 30   # continuous session only

# --- board permission filter (v2.5): per-account board access ---
# Unified scheme: same code deployed to different accounts, set False for a
# board the account cannot trade. Disallowed boards are skipped and the next
# candidate is taken, so buy slots are not wasted on rejected orders.
ALLOW_STAR = True             # STAR board 688/689
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

# --- T+2 conditional force-close + dynamic weakness rotation (v2.14, 2026-08-18) ---
# Data basis (DHS eval + prod Top2 paired sample, 11 trading days):
#   T+2 profit group holding +1d: mean slightly up but only 44% keep rising,
#     must be backed by peel; T+2 loss group holding +1d: mean -0.82pp, force sell.
#   T+3 profit group holding to T+4: +1.71pp / 62.5% keep rising, but n=14 -> default T+3.
T2_EXTEND_MAX_DAYS = 3          # max hold days for a profitable position (T+3; try 4 for T+4)
T2_EXTEND_PROFIT_MIN = 0.0      # legacy: superseded by the dynamic t2_force floor (v2.17)
# Dynamic T+2 force-close floor (v2.15, 2026-08-19): a wide intraday amplitude
# and high vol name tolerates a deeper normal pullback. A fixed 0% floor
# force-sold healthy names on noise (300591 08-19: buy slip to 8.54 made the
# next day's -1% look like -8.7%; 301130 was force-sold at +33% only because
# the _day_vwap unit bug set vwap_broken). Now ret must fall below the dynamic
# floor to force-sell; hard_stop (hs) still catches the true tail risk.
T2_FORCE_AMP_FRAC = 0.50        # fraction of day amplitude (%) added to the floor
T2_FORCE_AMP_MIN = 4.0          # amplitude below this adds no extra tolerance
T2_FORCE_VOL_K = 0.10           # +0.10 annual vol -> -1pp more tolerance
T2_FORCE_FLOOR_MAX = -0.10      # absolute floor (never below hard_stop)

# Buy-side slip guard (v2.15, 2026-08-19): the P2 trigger is a 5m bar close that
# can lag the live tape on a fast move; a market order then fills far above the
# trigger (300591 08-18: trig 7.88 filled 8.54, +8.4%). The inflated cost turns
# a normal next-day pullback into a deep "loss" that the old fixed 0% t2_force
# floor force-sold. If the live price has already run > MAX_BUY_SLIP_PCT above
# the trigger, hold off (do not chase) instead of buying at a blown cost.
MAX_BUY_SLIP_PCT = 0.02
ROTATION_ENABLE = False         # v2.28: off (rank<=2 ~1 buy/day; no kick-out)
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

# --- VWAP weak-early exit (QMT v2.3) ---
# Backtest (383 P2 trades, 2026-04~07): maxDD -29.6% -> -21.8%, winrate
# 50.7% -> 52.5%, hold 4.0 -> 3.2d. Confirm on day2 close window (>=14:45),
# sell at day3 open (09:35-09:50).
VWAP_CONFIRM_MIN = T2_FORCE_MIN       # same window as T+2 force close
VWAP_SELL_START = 9 * 60 + 35
VWAP_SELL_END = 9 * 60 + 50

# --- Wyckoff distribution (v2.10, same as QMT v2.10) ---
# Buy gate: skip candidate when T-1 daily bars show wy_bc or wy_ut.
# Sell early: BC bar while held (peak * 0.98 + long upper shadow + 1.5x vol).
# Volume-vs-volume (backtest-validated in bt_wyckoff_sell): today's 5m volume
# sum vs prior 20d daily volume mean.
WY_BC_WIN = 10            # lookback window for buy climax detection
WY_BC_HI_LOOKBACK = 60    # near-60d high reference
WY_BC_VOL_RATIO = 1.5     # climax volume vs prior 20d avg
WY_BC_SHADOW_FRAC = 0.35  # upper shadow >= 35% of daily range
WY_UT_BOX_DAYS = 20       # box reference days for upthrust
WY_UT_BREAK_PCT = 0.01    # 5d high > box high * 1.01 then closed back inside
WY_BC_SELL_VOL_RATIO = 1.5
WY_BC_SELL_SHADOW_FRAC = 0.35
WY_BC_SELL_NEAR_PEAK = 0.98

# --- file-backed order lock (QMT v2.3): guard against duplicate orders
#     across process restarts / multi-instance. TDX is a single loop so
#     in-memory sent_today is reliable, but the lock adds a hard guarantee. ---
ORDER_LOCK_FILE = r"C:\alphapilot\tdx_order_locks.json"
POS_STATE_FILE = r"C:\alphapilot\tdx_pos_state.json"
POS_STATE_PERSIST = (
    "buy_date", "cost", "peak", "peel_count", "peel_peak_snapshot",
    "t2_extended", "vwap_broken", "vwap_ref", "vwap_early_hits", "vwap_early_min",
    "wy_bc_armed", "trail_armed",
    "awaiting_new_high", "fusion_scores",
)
FUSION_CLOSED_LOG = r"C:\alphapilot\fusion_closed_trades.jsonl"
FUSION_SOURCE = "tdx_sim"

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
    """Load file-backed order lock map: {date: {code: {reason: ts}}}."""
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
    """True if (date, symbol, reason) already fired an order today."""
    try:
        d = _load_order_locks()
        return bool(d.get(today, {}).get(code, {}).get(reason, False))
    except Exception:
        return False


def _mark_order_locked(today, code, reason):
    """Persist (date, symbol, reason) as fired; prune old dates."""
    try:
        d = _load_order_locks()
        d.setdefault(today, {}).setdefault(code, {})[reason] = time.time()
        for old in [k for k in d if k != today]:
            d.pop(old, None)
        _save_order_locks(d)
    except Exception:
        pass


def _sell_lock_key(reason):
    # derive a stable per-reason key (e.g. "peel_half1", "t2_force") so a
    # multi-step peel can fire once per step, but identical reasons dedup.
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
        else:
            ST["trade_log"] = []
    except Exception:
        ST["trade_log"] = []
    ST["pos_state"] = _load_pos_state()


def _fusion_from_item(item, cands):
    """Build {vm25, fund_flow, sector_heat} at buy. Prefer server stamp."""
    fs = None
    if isinstance(item, dict):
        fs = item.get("fusion_scores") or item.get("_fusion_scores")
    if isinstance(fs, dict) and fs.get("vm25") is not None:
        out = {}
        for k in ("vm25", "fund_flow", "sector_heat"):
            try:
                out[k] = round(float(fs.get(k, 0.5)), 4)
            except Exception:
                out[k] = 0.5
        return out
    scores = []
    for it in (cands or []):
        try:
            scores.append(float(it.get("score") or 0))
        except Exception:
            pass
    try:
        sc = float((item or {}).get("score") or 0)
    except Exception:
        sc = 0.0
    vm25 = 0.5
    if scores:
        lo = min(scores)
        hi = max(scores)
        span = (hi - lo) if (hi - lo) != 0 else 1.0
        vm25 = (sc - lo) / span
        if vm25 < 0.0:
            vm25 = 0.0
        if vm25 > 1.0:
            vm25 = 1.0
    raw = 0.0
    if isinstance(item, dict):
        raw = item.get("live_main_net") or item.get("main_net") or item.get("main_net_5d") or 0
    try:
        x = float(raw)
    except Exception:
        x = 0.0
    if x == 0:
        fund = 0.5
    else:
        t = math.tanh(x / 10000000.0)
        fund = (t + 1.0) / 2.0
        if fund < 0.0:
            fund = 0.0
        if fund > 1.0:
            fund = 1.0
    heat = 0.5
    try:
        if isinstance(item, dict) and item.get("sector_heat") is not None:
            heat = float(item.get("sector_heat"))
    except Exception:
        heat = 0.5
    return {"vm25": round(vm25, 4), "fund_flow": round(fund, 4),
            "sector_heat": round(heat, 4)}


def _fusion_scores_resolve(code, pos):
    """Prefer pos stamp; else rebuild from buy-date candidates.json."""
    fs = pos.get("fusion_scores") if isinstance(pos, dict) else None
    if isinstance(fs, dict) and fs.get("vm25") is not None:
        return fs
    ymd = str((pos or {}).get("buy_date") or "").replace("-", "")[:8]
    if len(ymd) != 8:
        return None
    fpath = os.path.join(SCORE_DIR, ymd + ".candidates.json")
    try:
        raw = json.loads(open(fpath, "r", encoding="utf-8").read())
        cands = raw.get("candidates") or []
    except Exception:
        return None
    item = None
    want = str(code or "").upper()
    for x in cands:
        if str((x or {}).get("symbol") or "").upper() == want:
            item = x
            break
    if not item:
        return None
    out = _fusion_from_item(item, cands)
    if isinstance(out, dict) and out.get("vm25") is not None:
        pos["fusion_scores"] = out
        return out
    return None


def _append_fusion_closed(action, code, price, vol, pos):
    if not str(action).startswith("SELL"):
        return
    if not pos or not isinstance(pos, dict):
        return
    fs = _fusion_scores_resolve(code, pos)
    if not isinstance(fs, dict) or fs.get("vm25") is None:
        return
    try:
        buy_px = float(pos.get("buy_price") or pos.get("cost") or 0)
        px = float(price or 0)
        n = int(vol or 0)
    except Exception:
        return
    if buy_px <= 0 or n <= 0:
        return
    rec = {
        "source": FUSION_SOURCE,
        "symbol": code,
        "action": action,
        "buy_date": str(pos.get("buy_date") or ""),
        "sell_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "buy_price": round(buy_px, 4),
        "sell_price": round(px, 4),
        "volume": n,
        "pnl": round((px - buy_px) * n, 2),
        "_fusion_scores": fs,
    }
    try:
        with open(FUSION_CLOSED_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=True) + "\n")
    except Exception:
        pass


def _log_trade(action, code, price, vol, reason, pos=None):
    try:
        rec = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "action": action,
            "symbol": code,
            "price": round(float(price or 0), 3),
            "volume": int(vol or 0),
            "reason": reason,
        }
        if pos and isinstance(pos, dict) and pos.get("fusion_scores"):
            rec["fusion_scores"] = pos.get("fusion_scores")
            try:
                rec["buy_price"] = round(float(pos.get("buy_price") or pos.get("cost") or 0), 4)
            except Exception:
                pass
        sig = (action, code, rec["price"], rec["volume"])
        now = time.time()
        if now - ST["last_sig"].get(sig, 0.0) < LEDGER_DUP_SEC:
            return
        ST["last_sig"][sig] = now
        ST["trade_log"] = list(ST["trade_log"]) + [rec]
        with open(TRADE_LOG, "w", encoding="utf-8") as f:
            json.dump(ST["trade_log"], f, ensure_ascii=False)
        _append_fusion_closed(action, code, price, vol, pos)
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
            if str(tr.get("action", "")).startswith("SELL"):
                realized += float(tr.get("price") or 0) * int(tr.get("volume") or 0)
        day = {
            "date": today, "time": now.strftime("%Y-%m-%d %H:%M:%S"),
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
    Fields (tqcenter / TDX): Now=last, LastClose=prev close, Open, Max(high),
    Min(low), Volume(hands), Amount, Average(avg price), Before5MinNow.
    Does NOT depend on downloaded minute-line files."""
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
    """Latest realtime price. Snapshot Now first (no minute-line dependency),
    fallback to 1m K-line. Fail -> None."""
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


def _get_active_buy_ratio(code):
    """Active-buy ratio approx (TDX has no per-tick): snapshot order-book
    ratio Buy1Vol/(Buy1Vol+Sell1Vol). Field-name candidates checked because
    TDX snapshot keys vary across versions. Continuous-session only (after
    09:30). Unavailable -> None (soft signal, never hard-block)."""
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


def _abr_pass(code, now_min):
    """ABR gate: True = allow buy. Soft: data unavailable -> allow."""
    if not USE_ABR_GATE or now_min < ABR_GATE_START_MIN:
        return True
    abr = _get_active_buy_ratio(code)
    if abr is None:
        return True
    return abr >= MIN_ACTIVE_BUY


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
    tmin = real bar time (minutes since midnight). Only today's bars are kept
    (TDX count=N pulls back across days; yesterday's tail bars would pollute
    the P2 window otherwise). Fail -> None."""
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
    """Day VWAP. Prefer snapshot Average (TDX day average price = VWAP, works
    even without downloaded minute-line files), fall back to computing from
    5m bars (amount/volume). Fail -> None."""
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
    (open, high, low, close, volume) oldest-first, or None on fail.
    volume = daily volume (shares). Used by Wyckoff distribution signals."""
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
        # drop the last element: today's (partial) bar. T-1 is index n-2.
        return out[:-1]
    except BaseException:
        return None


# ================= WYCKOFF DISTRIBUTION (v2.10) =================
def _wyckoff_distribution(code):
    """Buy gate: True if T-1 daily bars show wy_bc or wy_ut (distribution).

    Same logic as QMT v2.10 / bt_wyckoff_buy. As-of: uses daily bars strictly
    before today (last element dropped). Data failure -> False (never block
    a valid candidate on a data hiccup). Backtest: 40/386 skipped (10.4%),
    avg +3.10% -> +3.40%, skipped trades weak (avg +0.53%).
    """
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

        # --- wy_bc: buy climax in last 10 days ---
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

        # --- wy_ut: upthrust / false breakout of 20d box ---
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
    """Sell early: True if today's 5m bars print a buy-climax bar while held.

    Bar qualifies: high >= peak * 0.98 (near holding peak), today's cum
    volume > 20d avg daily volume * 1.5, and a long upper shadow or red
    close. volume-vs-volume (matches bt_wyckoff_sell; the QMT v2.10 first
    pass accidentally compared daily amount vs 5m volume, which never fired).
    """
    if peak <= 0:
        return False
    try:
        bars = _get_daily_bars(code, 22)
        if not bars or len(bars) < 5:
            return False
        vols = [b[4] for b in bars]
        # last element may be today's partial bar; use prior 20
        vma20 = float(sum(vols[-20:]) / min(20, len(vols)))
        if vma20 <= 0:
            return False
    except BaseException:
        return False

    m5 = _get_m5_bars(code)
    if not m5 or len(m5) < 2:
        return False
    # daily volume so far today (5m sum), compare to 20d avg
    today_v = sum(b[5] for b in m5)
    if today_v <= vma20 * WY_BC_SELL_VOL_RATIO:
        return False
    # find a BC bar: near holding peak + long upper shadow
    for b in m5:
        _, o, c, h, l, _ = b
        if h >= peak * WY_BC_SELL_NEAR_PEAK:
            body_top = max(o, c)
            tail = h - body_top
            rng = h - l
            if (c < o or (rng > 0 and tail > rng * WY_BC_SELL_SHADOW_FRAC)):
                return True
    return False


def _get_turnover(code):
    """Daily turnover % = today's cum volume / float shares. Fail -> None
    (never blocks a candidate on data hiccup, same as QMT).

    Prefers snapshot Volume (hands * 100 = shares) so it works even without
    downloaded minute-line files. Float shares from get_stock_info: TDX basic
    financial fields are J_zgb (total shares) / ActiveCapital (float shares)
    in 10k shares or shares depending on client version -- handle both.
    """
    # --- snapshot path (no K-line dependency) ---
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
    # --- fallback: 1d K-line volume ---
    # NOTE 2026-08-13: TDX 1d K-line Volume unit is shares, NOT hands.
    # (snapshot Volume is hands; 1d Volume is already shares. Verified:
    # 002580 snapshot 556261 hands x100 = 55626100 shares == 1d 55626188 shares.)
    # So no x100 here -- divide by float shares directly.
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
    """Float shares (in shares). get_stock_info basic-financial fields:
    ActiveCapital / J_zgb are 10k-share units in this client version.
    Accept both raw-share and 10k-share values by magnitude heuristic."""
    try:
        info = _dict_of(tq.get_stock_info(stock_code=code))
    except BaseException:
        return None
    for k in ("ActiveCapital", "FloatShares", "FloatShare", "Ltgb", "Ltsz"):
        v = info.get(k)
        if v:
            try:
                fs = float(v)
                if fs <= 0:
                    continue
                # 10k-share -> shares if magnitude suggests 10k-share unit
                if fs < 1e7:
                    fs = fs * 1e4
                return fs
            except Exception:
                continue
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
    if saved.get("fusion_scores") and not pos.get("fusion_scores"):
        pos["fusion_scores"] = saved["fusion_scores"]


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
    """Return today's date string if TDX says this position was filled today
    (TodayBuyPosition > 0). Otherwise preserve the in-memory buy_date, or ""
    if unknown. Never stamp unknown holdings as today's buy (v2.9 fix:
    old positions were counted against MAX_DAILY_BUY and blocked all buys).
    v2.17 (2026-08-20): when the in-memory date is missing/empty (restart after
    T+1 unlock) recover it from the local trade log so _hold_days never sees an
    empty date and force-sells a fresh winner at 14:45."""
    try:
        if float(d.get("TodayBuyPosition") or 0) > 0:
            return datetime.now().strftime("%Y%m%d")
    except Exception:
        pass
    if old and old.get("buy_date"):
        return old.get("buy_date") or ""
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
                    # v2.9: never stamp old positions as "bought today". Only
                    # mark buy_date=today when TDX reports TodayBuyPosition>0
                    # (real intraday fill). Otherwise keep the in-memory date
                    # or leave empty so today_bought stays correct.
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


# ================= SCORES / REMOTE FETCH =================
def _fetch_remote_scores(today):
    """Fetch {date}.json / {date}.candidates.json from server nginx if local
    file is missing (Plan A, same as QMT v2.2). Throttled + silent-fail.
    Only attempts after REMOTE_FETCH_START_MIN (server generates ~09:36)."""
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
    for suffix in (".json", ".candidates.json"):
        fpath = os.path.join(SCORE_DIR, today + suffix)
        if os.path.exists(fpath) and os.path.getsize(fpath) > 0:
            continue
        url = REMOTE_SCORE_BASE + "/" + today + suffix
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "TDX/2.2"})
            with urllib.request.urlopen(req, timeout=REMOTE_TIMEOUT) as resp:
                body = resp.read()
                if not body:
                    log("[FETCH] " + url + " empty")
                    continue
                with open(fpath, "wb") as f:
                    f.write(body)
                log("[FETCH] " + today + suffix + " <- " + url +
                    " (" + str(len(body)) + "b)")
        except Exception as e:
            log("[FETCH] " + url + " fail: " + str(e)[:90])


def _load_scores(today):
    """Full-score dict from {date}.json. Local-first, remote fallback.
    If a local file exists but fails to parse (0-byte / corrupted / GBK
    garbage), delete it and force a fresh fetch once so a bad local copy
    can never silently block the strategy (2026-08-13: TDX no-buy issue)."""
    fpath = os.path.join(SCORE_DIR, today + ".json")
    if not os.path.exists(fpath):
        _fetch_remote_scores(today)
        if not os.path.exists(fpath):
            return None
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log("[SCORES] parse fail " + fpath + ": " + str(e)[:80] +
            " -> delete + refetch")
        try:
            os.remove(fpath)
        except Exception:
            pass
        _fetch_remote_scores(today)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None


def _filter_st_cands(cands):
    """ST/退市风险警示硬过滤（2026-08-25 事故：*ST威领被 Track B 买入）。
    ST / *ST / S*ST / 退市整理 一律剔除，名称缺失不误杀。"""
    st = [it for it in (cands or [])
          if "ST" in str(it.get("name") or "").upper()
          or str(it.get("name") or "").startswith("退")
          or "退市" in str(it.get("name") or "")]
    if st:
        cands = [it for it in (cands or []) if it not in st]
        log("[CAND] ST/退市硬过滤剔除 " + str(len(st)) + ": "
            + ", ".join(str(it.get("name")) for it in st[:10]))
    return cands


def _load_candidates(today):
    """Top10 candidate pool from {date}.candidates.json (prefer this).
    Corrupted local file -> delete + refetch (same self-heal as _load_scores)."""
    fpath = os.path.join(SCORE_DIR, today + ".candidates.json")
    if not os.path.exists(fpath):
        _fetch_remote_scores(today)
        if not os.path.exists(fpath):
            return None
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            d = json.load(f)
        return _filter_st_cands(d.get("candidates") or [])
    except Exception as e:
        log("[CAND] parse fail " + fpath + ": " + str(e)[:80] +
            " -> delete + refetch")
        try:
            os.remove(fpath)
        except Exception:
            pass
        _fetch_remote_scores(today)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                d = json.load(f)
            return _filter_st_cands(d.get("candidates") or [])
        except Exception:
            return None


def _build_cands(today):
    """Return list of {symbol, name, rank}. Prefer candidates file."""
    cands = _load_candidates(today)
    if cands:
        log("[CAND] n=" + str(len(cands)) + " day=" + today)
        return cands
    scores = _load_scores(today)
    if not scores:
        log("[CAND] none day=" + today)
        return None
    return [{"symbol": c, "name": c, "score": s, "rank": i + 1}
            for i, (c, s) in enumerate(list(scores.items())[:10])]



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


# ================= SELL (same logic as QMT v2.2) =================
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
    log("[SELL] " + code + " " + reason + " all " + str(vol) + "sh @ " + str(round(price, 2)))
    try:
        tq.order_stock(
            account_id=ST["account"], stock_code=code,
            order_type=tqconst.STOCK_SELL, order_volume=vol,
            price_type=tqconst.PRICE_MY, price=price)
        _mark_order_locked(today, code, lockk)
    except BaseException as e:
        log("[SELL] order fail: " + repr(e)[:100])
    _log_trade("SELL", code, price, vol, reason, pos=pos)
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
    log("[SELL] " + code + " " + reason + " half " + str(half) + "sh @ " + str(round(price, 2)))
    try:
        tq.order_stock(
            account_id=ST["account"], stock_code=code,
            order_type=tqconst.STOCK_SELL, order_volume=half,
            price_type=tqconst.PRICE_MY, price=price)
        _mark_order_locked(today, code, lockk)
    except BaseException as e:
        log("[SELL] order fail: " + repr(e)[:100])
    pos["shares"] = shares - half
    _log_trade("SELL_HALF", code, price, half, reason, pos=pos)
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
        name = pos.get("name", code)

        if price > float(pos.get("today_high") or 0):
            pos["today_high"] = price
        if price > float(pos.get("peak") or cost):
            pos["peak"] = price

        ret = (price / cost - 1) * 100
        daily = (price / prev_close - 1) * 100 if prev_close and prev_close > 0 else 0.0

        # anomaly: warn + hold (same as QMT, do not panic-sell)
        if daily <= ANOMALY_PCT:
            log("[WARN] " + code + " daily=" + str(round(daily, 1)) +
                "% anomaly, hold")
            continue

        # limit-down: allowed even on T+1 buy day
        if daily <= LIMIT_DOWN_PCT:
            _do_sell(code, pos, price,
                     "limit_down daily=" + str(round(daily, 1)) + "%")
            continue

        bd = str(pos.get("buy_date") or "")
        is_today_buy = (bd == today)
        if is_today_buy:
            continue  # T+1: cannot sell today's buy (except limit-down)

        # Wyckoff buy-climax early exit (v2.10): if today's bars print a
        # climax bar near the holding peak (long upper shadow + 1.5x vol),
        # sell at next open. Confirmed only in the close window so the daily
        # volume comparison is meaningful; fires on the next day's open.
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

        # VWAP weak-early exit (v2.3): if day2 closes below day-VWAP, sell at
        # day3 open. In production the T+2 block below force-closes (<95% cost)
        # or extends (+1d) at 14:45 on day2, so this only matters for positions
        # that survive to day3 (extended). Confirm on the same window as T+2,
        # then fire on the next open.
        if not pos.get("vwap_broken") and now_min >= VWAP_CONFIRM_MIN:
            vw = _day_vwap(code)
            if vw and vw > 0 and price < vw:
                pos["vwap_broken"] = True
                pos["vwap_ref"] = vw
                log("[VWAP] " + code + " day-vwap broken px=" +
                    str(round(price, 2)) + " vwap=" + str(round(vw, 2)) +
                    " ret=" + str(round(ret, 1)) + "%")
        # v2.25: next-morning confirm. Unconditional next-open sell sold the
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

        # hard stop: close-confirm window only (>=14:45)
        if now_min >= T2_FORCE_MIN and ret <= hs * 100:
            _do_sell(code, pos, price,
                     "hard_stop " + str(round(ret, 1)) + "% vs " +
                     str(round(hs * 100, 1)) + "%")
            continue

        # T+2 conditional force-close (v2.17, 2026-08-19): dynamic floor force-sell + profit extend T+3 (peel guards)
        if now_min >= T2_FORCE_MIN:
            hold_days = _hold_days(pos, today)
            if pos.get("t2_extended"):
                # already extended: force-sell at maturity (hold_days >= T2_EXTEND_MAX_DAYS)
                # only. v2.17 fix: the old code sold on the very next 14:45 pass, so
                # T2_EXTEND_MAX_DAYS=3 bought just 1 extra day instead of the intended
                # T+3. Inside the window the position keeps running with the trailing
                # peel / vwap_weak_early / wyckoff_bc exits still armed.
                # v2.17 (2026-08-20): hold_days == 999 (buy_date unknown) must not
                # be read as past maturity and force-sell a fresh winner.
                if hold_days != 999 and hold_days >= T2_EXTEND_MAX_DAYS:
                    _do_sell(code, pos, price,
                             "t2_force_after_extend " + str(round(ret, 1)) + "%")
                    continue
            else:
                # v2.17: dynamic floor instead of fixed 0%. A wide-amplitude / high-vol
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
                # v2.17 (2026-08-19): do NOT let vwap_broken / wy_bc_armed short-circuit
                # the dynamic floor. Both are NEXT-MORNING (09:35-09:50) exit signals:
                # 300591 08-19 fair-cost -1.0% was force-sold only because vwap_broken
                # set in the same 14:45 pass (price 7.80 < vwap 8.05) hit this branch
                # before the floor (-4.45%) could hold it. After extension the T+3
                # morning window fires vwap_weak_early / wyckoff_bc. Only hold-cap and
                # hard-stop refuse to extend.
                # v2.17 (2026-08-20): hold_days == 999 (buy_date unknown) must not
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

        # dynamic peel (intraday, profit only)
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
                pos["peel_peak_snapshot"] = peak

        if (pos.get("awaiting_new_high") and
                float(pos.get("peak") or 0) > float(pos.get("peel_peak_snapshot") or 0) + 1e-9):
            pos["awaiting_new_high"] = False
    _save_pos_state()


# ============ Sell-side rework v2.14: T+2 conditional + dynamic weakness rotation (2026-08-18) ============
def _hold_days(pos, today):
    """Holding days from buy_date -> today (buy day excluded). buy_date is %Y%m%d
    (e.g. 20260818). Compatible with 'YYYY-MM-DD'. 999 on missing/unparseable.
    v2.26: counts TRADING days (weekends + 2026 A-share closures excluded),
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


def _volume_ratio_of(code):
    """Volume ratio = today cum vol / prior 5d same-time cum vol mean (aligned
    with Track B v1.1 same-time window to avoid 09:35 structural under-count).
    None on fail (momentum guard soft-skips)."""
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
        vr = _volume_ratio_of(it["code"])
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
    """When holdings are full (MAX_HOLDINGS) and a new Top2 passed P2, sell the
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


# ================= BUY (P2 first-come, same as QMT v2.2) =================
def _vol_ma5(vols, i):
    s = vols[max(0, i - 4):i + 1]
    return sum(s) / len(s) if s else 0.0


def _is_limit_up(code, prev_close):
    if not prev_close or prev_close <= 0:
        return False
    price = _last_price(code)
    if not price:
        return False
    return (price / prev_close - 1) >= 0.095


def _board_allowed(code):
    """Board permission filter (v2.5). True if this account can trade the
    board. Blocked boards -> candidate skipped, rank descends to next.
    Unknown prefixes are allowed (never block a valid candidate)."""
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


def _p2_max_gap(code):
    """Board-aware no-chase: main 6%%, ChiNext/STAR 10%%, BSE 12%%."""
    raw = str(code or "").split(".")[0]
    c6 = "".join(ch for ch in raw if ch.isdigit()).zfill(6)
    if c6.startswith(("688", "689", "300", "301")):
        return 0.10
    if c6.startswith(("8", "4", "920")):
        return 0.12
    return 0.06


def _sweet_gap_pct(code):
    """Open gap% = (open/prev_close - 1)*100 for sweet-zone check."""
    try:
        open_, _ = _snap_open_high(code)
        prev = ST["prev_close"].get(code) or _prev_close(code)
        if not prev or prev <= 0 or not open_ or open_ <= 0:
            return None
        return (open_ / prev - 1.0) * 100.0
    except BaseException:
        return None


def _is_sweet_zone(code):
    """True if this candidate's open gap is in the P2 sweet zone."""
    if SWEET_ZONE_MODE <= 0:
        return False
    g = _sweet_gap_pct(code)
    if g is None:
        return False
    return (SWEET_GAP_LO - 1e-9) <= g <= (SWEET_GAP_HI + 1e-9)


def _filter_cands_by_max_rank(cands):
    """Keep only 09:35 candidates.json rank 1-2. MAX_CAND_RANK<=0 = off."""
    if MAX_CAND_RANK <= 0:
        return list(cands or [])
    kept = []
    for it in (cands or []):
        r = int(it.get("rank") or 0)
        if 0 < r <= MAX_CAND_RANK:
            kept.append(it)
    return kept


def _order_cands_by_sweet(cands):
    """Trigger-order preference (v2.24): sweet-zone candidates first when they
    race for the daily buy slots. SWEET_ZONE_MODE=1 sorts (sweet first, others
    by rank); =2 keeps only sweet-zone names. Returns a new list."""
    if SWEET_ZONE_MODE <= 0:
        return cands
    out = []
    for item in cands:
        code = qmt_code(item.get("symbol"))
        if SWEET_ZONE_MODE == 2 and not _is_sweet_zone(code):
            log("[SWEET] " + code + " not in sweet zone, skip (mode=2)")
            continue
        out.append(item)
    if SWEET_ZONE_MODE == 1:
        out.sort(key=lambda it: (0 if _is_sweet_zone(qmt_code(it.get("symbol")))
                                 else 1, int(it.get("rank") or 0)))
    return out


def _p2_day_high_ok(c, day_high, day_low):
    rng = day_high - day_low
    if rng <= 0:
        return True
    return (c - day_low) / rng <= CONF_DAY_HIGH_MAX


def _p2_decide(code, now_min):
    """P2 dynamic confirmation. Full version when 5m K-lines are available
    (same as QMT: p935+VWAP trend / vol-ratio / no-chase), otherwise falls
    back to snapshot confirm (realtime > prev_close and > average, 5m strength,
    no-chase). This keeps the strategy usable even when the TQ client has no
    downloaded minute-line data.
    Returns (fill_price or None, reason).
    reason: dyn_confirm | snap_confirm | wait_confirm | no_confirm_eod |
            no_quote | no_m5 | skip_high_turnover
    """
    prev_close = ST["prev_close"].get(code) or _prev_close(code)
    if not prev_close:
        ST["prev_close"][code] = prev_close or 0
        return None, "no_quote"
    price = _last_price(code)
    if not price or price <= 0:
        return None, "no_quote"

    # observation window
    if now_min > CONF_END_MIN:
        return None, "no_confirm_eod"
    if now_min < CONF_START_MIN:
        return None, "wait_confirm"

    # turnover gate (data unavailable -> do not block)
    _to = _get_turnover(code)
    if _to is not None and _to > CONF_MAX_TURNOVER:
        return None, "skip_high_turnover"

    bars = _get_m5_bars(code)
    if bars is not None:
        # only today's bars
        today_bars = [b for b in bars if b[0] >= CONF_START_MIN]
        if today_bars:
            # P935 = 09:35 snapshot price = close of today's first 5m bar
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
                # 2) volume: last 2 bars at least one with vol-ratio and up
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
                # 3) no-chase (board-aware)
                if c > prev_close * (1 + gap_lim):
                    continue
                # 4) day-high guard
                if not _p2_day_high_ok(c, day_high, day_low):
                    continue
                trig_px = c
                break
            if trig_px and trig_px > 0:
                if not _abr_pass(code, now_min):
                    return None, "skip_low_abr"
                return round(trig_px, 2), "dyn_confirm"
            if now_min >= CONF_END_MIN:
                return None, "no_confirm_eod"
            return None, "wait_confirm"

    # --- fallback: snapshot confirm (no minute-line data) ---
    s = _snap(code)
    if s is None:
        return None, "no_quote"
    avg = _f(s, "Average", "Avg", default=None)
    before5 = _f(s, "Before5MinNow", default=None)
    # 1) trend: realtime > prev_close (intraday up) and > average price
    if not (price > prev_close and avg and price > avg):
        return None, "wait_confirm"
    # 2) strength: price >= 5-minutes-ago price (upward momentum)
    if before5 and price < before5:
        return None, "wait_confirm"
    # 3) no-chase (board-aware)
    gap_lim = _p2_max_gap(code)
    if price > prev_close * (1 + gap_lim):
        return None, "no_chase"
    hi = _f(s, "High", default=None) or price
    lo = _f(s, "Low", default=None) or price
    if not _p2_day_high_ok(price, hi, lo):
        return None, "skip_day_high"
    if not _abr_pass(code, now_min):
        return None, "skip_low_abr"
    return round(price, 2), "snap_confirm"


def _query_cash():
    """Return (cash, total_asset) from TDX query_stock_asset.
    TDX docs return {Balance,Cash,Asset,MarketValue}. Defensive parse:
    cash  -> Cash | Balance
    total -> Asset | TotalAssets | Cash+MarketValue"""
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


def _item_fund_hard_fail(item):
    """money_flow_gate weak-hard floor: deep 5d outflow or no participation."""
    if item.get("fund_hard_fail") is not None:
        return bool(item.get("fund_hard_fail"))
    s3 = float(item.get("main_net_3d") or 0)
    s5 = float(item.get("main_net_5d") or 0)
    pos5 = int(item.get("fund_pos_days_5") or 0)
    if s3 == 0 and s5 == 0 and pos5 == 0:
        return False
    if s3 <= 0 and s5 <= 0 and pos5 == 0:
        return True
    if s5 < -1e8:
        return True
    return False


def _check_buy(now, now_min, today, cands):
    # v2.27: only rank 1-2 may enter P2 / rotation. Filter BEFORE sweet-zone
    # reorder so rank 3+ cannot take a daily slot or trigger rotation.
    n_all = len(cands or [])
    cands = _filter_cands_by_max_rank(cands)
    if n_all and ST.get("rank_logged") != today:
        ST["rank_logged"] = today
        log("[RANK] max=" + str(MAX_CAND_RANK) + " keep=" + str(len(cands)) + "/" + str(n_all))
    # v2.24: sweet-zone trigger priority -- reorder candidates before the
    # race for the daily buy slots (no scoring change, ordering only)
    cands = _order_cands_by_sweet(cands)
    if len(ST["positions"]) >= MAX_HOLDINGS:
        # v2.14 rotation: holdings full and a candidate passed P2 -> first sell
        # the weakest position to free a slot (P1). Evaluate the candidate first
        # (P2 gating precedes) so we never sell a position for a weak name.
        worth_buy = False
        for item in cands:
            code = qmt_code(item.get("symbol"))
            if code in ST["positions"] or code in ST["sent_today"]:
                continue
            if _order_locked(today, code, "BUY"):
                continue
            fill, reason = _p2_decide(code, now_min)
            if fill is not None:
                worth_buy = True
                break
        if not worth_buy:
            log("[BUY] skip: holdings full & no P2-confirmed candidate")
            return
        sold = _rotation_sell(now, now_min, today, ROTATION_SELL_N)
        if not sold:
            log("[BUY] skip: holdings full & rotation sold nothing")
            return
        # sold ok, continue below (re-query cash; A-share T+0 recycle)
    cash, total_asset = _query_cash()
    if cash <= 0:
        log("[BUY] skip: cash=" + str(cash))
        return
    if total_asset <= 0:
        total_asset = cash

    # v2.9: count BUY orders actually FIRED today from order_locks (authoritative),
    # not from position_map. position_map entries for today's buys can be dropped
    # or kept pending, but the real budget is "how many BUY locks exist today".
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

    for item in cands:
        code = qmt_code(item.get("symbol"))
        rank = int(item.get("rank") or 0)
        if code in ST["positions"] or code in ST["sent_today"]:
            continue
        if len(ST["positions"]) >= MAX_HOLDINGS:
            break
        if today_bought >= MAX_DAILY_BUY:
            break
        # file-level dedup: guard against duplicate buys across restarts
        if _order_locked(today, code, "BUY"):
            log("[LOCK] " + code + " BUY skip (already ordered today)")
            continue

        # board permission: account cannot trade this board -> skip rank,
        # never spend a buy slot or produce a rejected order (v2.5)
        if not _board_allowed(code):
            log("[SKIP] " + code + " board not allowed rank=" + str(rank))
            ST["sent_today"].add(code)
            continue

        # ST/退市风险警示硬过滤（2026-08-25 事故：*ST威领被 Track B 买入）
        nm = str(item.get("name") or "")
        if "ST" in nm.upper() or nm.startswith("退") or "退市" in nm:
            log("[ST] " + code + " " + nm + " skip (risk-warning)")
            ST["sent_today"].add(code)
            continue

        if _item_fund_hard_fail(item):
            log("[FUND] " + code + " fund_hard_fail skip rank=" + str(rank))
            ST["sent_today"].add(code)
            continue

        prev_close = ST["prev_close"].get(code) or _prev_close(code)
        if prev_close:
            ST["prev_close"][code] = prev_close
        if _is_limit_up(code, prev_close):
            log("[WAIT] " + code + " limit-up rank=" + str(rank) + " skip today")
            ST["sent_today"].add(code)
            continue

        # Wyckoff distribution buy gate (v2.10): T-1 daily bars show
        # buy climax (wy_bc) or upthrust (wy_ut) -> skip this candidate today.
        if _wyckoff_distribution(code):
            log("[WYCKOFF] " + code + " distribution (bc/ut) rank=" +
                str(rank) + " skip for today")
            ST["sent_today"].add(code)
            continue

        fill, reason = _p2_decide(code, now_min)
        if fill is None:
            # no_confirm_eod / skip_high_turnover / skip_low_abr are final for
            # today -> abandon. Others (no_quote/no_m5/wait_confirm/no_chase)
            # are transient -> retry.
            if reason in ("no_confirm_eod", "skip_high_turnover",
                          "skip_low_abr"):
                log("[WAIT] " + code + " P2=" + reason +
                    " rank=" + str(rank) + " abandon today")
                ST["sent_today"].add(code)
            else:
                log("[WAIT] " + code + " P2=" + reason +
                    " rank=" + str(rank) + " retry next period")
            continue

        # v2.15 slip guard (2026-08-19): the P2 trigger is a 5m bar close that
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
            # v2.10: order_stock returns -1 (int) on rejection, or a dict
            # with ErrorId on acceptance. NEVER trust the call blindly: a
            # rejected order must not write a BUY lock (that would consume
            # today_bought and silently block all later buys).
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
                "name": item.get("name") or bare_code(code),
                "buy_date": today, "peak": fill,
                "trail_armed": False, "awaiting_new_high": False,
                "peel_peak_snapshot": fill, "peel_count": 0,
                "t2_extended": False, "vwap_broken": False,
                "wy_bc_armed": False,
                "today_high": fill,
                "fusion_scores": _fusion_from_item(item, cands or []),
            }
            today_bought += 1
            tag = "dyn_confirm" if reason == "dyn_confirm" else "snap_confirm"
            sweet_tag = " SWEET" if _is_sweet_zone(code) else ""
            log("[BUY] " + code + " x" + str(shares) + " @ " +
                str(round(fill, 2)) + " P2=" + tag + " rank=" + str(rank) +
                sweet_tag)
            _log_trade("BUY", code, fill, shares, "p2_" + tag,
                       pos=ST["positions"][code])
            _save_pos_state()
        except BaseException as e:
            log("[BUY] order fail: " + repr(e)[:100])
            ST["sent_today"].add(code)


# ================= MAIN LOOP =================
def is_trading_time(m):
    return (9 * 60 + 30 <= m <= 11 * 60 + 30) or (13 * 60 <= m <= 15 * 60)


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
        log("[WARN] account " + ACCOUNT + " handle failed, try client default logged-in")
    h = tq.stock_account(account="", account_type="STOCK")
    return h, "(default)"


def main():
    try:
        tq.initialize(__file__)
    except BaseException as e:
        log("[FATAL] tq.initialize fail: " + repr(e)[:120])
        log("      start TongDaXin Financial Terminal (quant sim) and login")
        sys.exit(1)
    handle, used_acct = _get_account_handle()
    try:
        if handle is None or int(handle or -1) < 0:
            log("[FATAL] cannot get account handle: login the SIM account in TDX client")
            log("      menu: Trade -> embedded SIM trading -> phone+password login")
            sys.exit(1)
    except BaseException:
        log("[FATAL] cannot get account handle: " + repr(handle))
        sys.exit(1)
    ST["account"] = handle
    log("[INIT] track-A tdx-sim v2.29 (P2 + rank<=2, vwap 2nd) | acct=" + used_acct +
        " | handle=" + str(handle) +
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

            # every ~60s sync positions (catch external operations)
            if int(time.time()) % 60 < POLL_SEC:
                _sync_positions()

            if not is_trading_time(now_min):
                time.sleep(POLL_SEC)
                continue

            cands = _build_cands(today)
            if cands is None:
                time.sleep(POLL_SEC)
                continue

            # bar-level guard (synced with QMT v2.6): an uncaught exception in
            # sell logic must never prevent buy logic from running this cycle
            # (QMT 2026-08-12: _annual_vol -> data layer raised and killed the
            # bar before _check_buy could place any order).
            try:
                _check_sell(now, now_min, today)
            except BaseException as e:
                log("[SELL-ERR] " + repr(e)[:120])

            try:
                _check_buy(now, now_min, today, cands)
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
