# coding:utf-8
# AlphaPilot -- Track A QMT sim full-chain strategy v2.27 (trading-day hold)
# File: TrackA_track_a_qmt_full_chain_sim.py
# =========================================================
# v2.27 changes vs v2.26 (2026-08-31, trading-day hold fix):
#   * _hold_days counts TRADING days, not calendar days. The old
#     (today - buy_date).days counted weekends/holidays, so a Friday buy read
#     as hold=3 on the following Monday (real T+1) and wrongly hit
#     t2_force_after_extend / rotation_sell. New _ASHARE_CLOSED_2026 set +
#     _trading_days_between(); only weekend + 2026 official closures excluded.
# v2.26 changes vs v2.25 (2026-08-31, vwap_weak_early next-morning confirm):
#   * Sell at next open only if the live price is still BELOW the day-VWAP
#     reference recorded when the signal armed (price < vwap_ref). If the price
#     has recovered above the reference, cancel the signal and keep holding.
#     Evidence (QMT sim 08-31, n=3): unconditional next-open sell hit the day's
#     low and all three rallied +3.5%/+3.8%/+7.0%. New persisted field vwap_ref.
# v2.25 changes vs v2.24 (2026-08-29, P2 sweet-zone trigger priority):
#   * New SWEET_ZONE_MODE (0=off / 1=priority / 2=only): P2 candidates whose
#     open gap is in [-1.5%, 0] (slight low-open) get priority when racing for
#     the daily buy slots. Ordering-only, no scoring change. BT 2026-04~07 +
#     real 07~08 show upward-bias T+1 for the sweet zone (7/7 slices >=).
#     BUY logs tagged [SWEET].
# v2.24 (2026-08-28): sell jsonl falls back to {buy_date}.candidates.json
# v2.23+ (2026-08-28): stamp fusion_scores on buy; append IC closed-trade on sell.
# v2.22 changes vs v2.21 (2026-08-26, fund_hard_fail client guard):
#   * _check_buy skips candidates with fund_hard_fail (defense in depth vs server).
# v2.21 changes vs v2.20 (2026-08-26, P2 dynamic session-low trend):
#   * P2 trend uses rolling session low (c > day_low) instead of c > p935
#     and drops the prev_close day-trend guard (relative vs dynamic high/low).
# v2.20 changes vs v2.19 (2026-08-26, P2 anti-chase alignment with Track B):
#   * Board-aware no-chase: main 6%, ChiNext/STAR 10%, BSE 12% (was uniform 8%).
#   * Day-high guard: skip P2 when price in top 15% of intraday range
#     (CONF_DAY_HIGH_MAX=0.85; bt Track B S2 +1.42% T+0 vs +0.77% baseline).
# v2.19 changes vs v2.18 (2026-08-20, T+1 winner force-sell fix):
#   * _sync_holdings recovers buy_date from the local trade log when QMT sim
#     leaves m_strOpenDate empty after a restart (000651 08-20: +1.5% T+1 sold
#     as t2_force_after_extend because empty buy_date -> _hold_days 999).
#   * _check_sell T+2 maturity check adds hold_days != 999 guard: unknown date
#     is never read as past maturity; real T+3 cap and hard-stop still fire.
# v2.18 changes vs v2.17 (2026-08-19, Kimi 3 cross-validation fixes):
#   * P0-A: _day_vwap docstrings made pure ASCII (QMT deploy hard rule).
#   * P0-B: vwap_broken / wy_bc_armed no longer short-circuit the dynamic
#     t2_force floor at 14:45; they fire next morning (09:35-09:50) instead.
#   * P1: t2_extended positions are held until hold_days >= T2_EXTEND_MAX_DAYS
#     (old code sold on the very next 14:45 pass, so T+3 meant only +1 day).
# v2.17 changes vs v2.16 (2026-08-19, dynamic t2_force floor + buy slip guard):
#   * _day_vwap unit fix: 5m volume is in HANDS (x100 to shares), fixed the
#     100x VWAP bug (300591 vwap=806.98 vs tape ~8.07) that made vwap_broken
#     always true and force-sold 301130 at +33%.
#   * _t2_force_floor dynamic force-sell line replaces the fixed 0% floor;
#     _day_amplitude_pct adds tolerance for wide-amplitude / high-vol names.
#   * MAX_BUY_SLIP_PCT=0.02: no-chase when the live price has run > 2% above
#     the P2 trigger (300591 08-18: trig 7.88 filled 8.54, +8.4% slip).
# v2.16 changes vs v2.15 (2026-08-18, DSH review of sell-side rework):
#   * Rotation protection: T+0 AND T+1 holdings are immune to rotation
#     (ROTATION_MIN_HOLD_DAYS 1 -> 2); only T+2+ positions may be rotated.
#   * Daily rotation cap ROTATION_DAILY_MAX=1 (limit churn & fees).
#   * Hysteresis (ROTATION_WEAK_GATE): only rotate when the weakest holding shows a
#     concrete weakness signal (day<0 / below day-VWAP / early-exit / underwater).
# v2.15 changes vs v2.14 (2026-08-18, DHS sell-side eval P0+P1 landed):
#   * T+2 force-close is now conditional: loss (ret<0) force-sell; profit without
#     an early-exit signal extends to T+3 (T2_EXTEND_MAX_DAYS, peel stays armed as
#     downside protection). Replaces the old price>=cost*0.95 one-size extension.
#   * Dynamic weakness rotation (P1): when holdings are full (MAX_HOLDINGS) and a
#     candidate passed P2, first evaluate the candidate (P2 gating precedes so we
#     never sell a position for a weak name), then sell the weakest 1 to free a
#     slot and re-query cash to buy on the same bar (A-share T+0 recycle).
#     Weakness score = ret30% + vwap-break20% + day20% + early15% + peel10% + days5%,
#     relative-rank normalized, momentum guard (day>3% and vol-ratio>1.3 -> skip).
#   * New helpers _hold_days/_closed_5m_bars/_volume_ratio_of/_weakness_score/
#     _rotation_sell. _hold_days fixes the DHS patch date-format bug
#     (%Y-%m-%d -> %Y%m%d, otherwise rotation can never find a sellable position).
# v2.14 changes vs v2.13 (2026-08-18):
#   P2 5m confirm now only uses TODAY's 5m bars. Old code called
#   get_market_data_ex(count=48, end_time=today) and reverse-engineered the
#   bar time via CONF_START_MIN + i*5 without filtering by date, so early in
#   the session the 5m series could contain previous days' bars. P2's p935 /
#   VWAP / volume-MA5 were then computed on stale bars, which let a
#   money_flow_pass=false, down-on-the-day name (08-18 Track B Xidian 301130,
#   buy log "@30.6" -- a price that never traded today, real fill 29.23) pass
#   the "5m volume-backed up-move" check. Now start_time=today pins the range and
#   _bar_times() keeps real timestamps only.
#   _p2_decide filters today_bars = [b for b in bars if b[0] >= CONF_START_MIN]
#   before computing p935 / VWAP / vol-MA5 (same as the TDX client), and adds a
#   day-trend guard (c >= prev_close) so it never confirms a stock that is
#   down on the day.
#   _day_vwap also restricted to today's bars.
#   _log_trade now updates C.trade_log in memory (ledger overwrite bug).
# v2.13 changes vs v2.12 (2026-08-16):
#   ABR (active-buy ratio) gate on top of P2 dynamic confirmation. 2026-08
#   backtest (114 candidates / 20 days real Top10): cumulative ABR >= 0.52 at
#   the P2 trigger lifts T+1 winrate 42.3% -> 54.2%, T+1 mean -0.46% ->
#   +0.36%. Data: mootdx_feed free tick direction (day-cumulative, matches
#   backtest) -> QMT L1 tick approx fallback. Soft gate: data unavailable ->
#   pass. P2 trigger with ABR below MIN_ACTIVE_BUY -> "skip_low_abr" (abandon
#   candidate for today).
# v2.12 changes vs v2.11 (2026-08-15):
#   FIX over-sized sell orders. _sync_holdings now captures the broker's
#   tradable quantity (m_nCanUseVolume) into pos["can_use"], and _do_sell /
#   _do_sell_half cap the order volume to it. 2026-08-14 real case: 002580
#   held 80900 but only 40500 were sellable (40400 had just been sold by
#   peel_half1; a sync race re-inflated the in-memory count), so the t2_force
#   order asked for 80900 and the broker rejected it with [251005]
#   insufficient available qty.
#   Same-day buys failed the T+1 skip too: QMT sim leaves m_strOpenDate empty,
#   so is_today_buy was False and the strategy tried to sell 000938/688180
#   bought today -> also rejected. Now buy_date is inferred from can_use<vol
#   (the locked part = today's T+1 buy) and the T+1 skip works even after a
#   strategy restart.
# v2.11 changes vs v2.10 (2026-08-14):
#   FIX critical "silent no-buy" bug: passorder REJECTED orders still wrote
#   BUY lock + position + trade log + today_bought, because `if ret != 0`
#   only printed. 2026-08-14 real case: account had ZERO broker orders
#   ([DIAG] n=0) but order_locks/trades recorded BUY 000938 + 688180 at
#   11:07 (right after a flaky login), so today_bought hit MAX_DAILY_BUY=2
#   and _check_buy silently broke before any candidate -- nothing bought all
#   day. Now a rejected order prints "[BUY] ... REJECTED ret=.. (no lock
#   written)" and never consumes a buy slot. Also added visible logs for
#   the two silent exits (holdings full / today_bought full) and an INIT
#   summary of today's order locks.
# v2.10 changes vs v2.9 (2026-08-12):
#   Wyckoff  : distribution-side signal integration (full-sample 386 P2 backtest,
#              2026-04~07, 5m data).
#     Buy gate  : skip candidate when T-1 daily bars show wy_bc (buy climax:
#                 near 60d high + long upper shadow + 1.5x volume) or wy_ut
#                 (upthrust: 5d new high above 20d box then closed back inside).
#                 40/386 (10.4%) skipped, avg +3.10% -> +3.40%, win 50.7%->51.0%,
#                 skipped trades avg +0.53% / med -1.34% (weak).
#     Sell early: position that prints a BC bar while held (day high >= peak*0.98
#                 + upper shadow + volume > 20d avg*1.5) sells at next open.
#                 win 50.7% -> 55.4%, median +0.12% -> +1.37%, maxDD -29.6% ->
#                 -22.5%, avg +3.10% -> +3.42%; early-exit med +5.15% (sells high).
#                 UT/box events hurt (false sells) -> not used.
#   Implementation: pure-QMT daily bars (get_market_data_ex period="1d") for the
#   buy gate; 5m bars + holding peak for the sell signal. All as-of (no future).
# v2.9 changes vs v2.8 (2026-08-12):
#   Order execution: passorder now passes quickTrade=1 (immediate fire).
#   order_shares/passorder quickTrade=0 are K-line driven: the signal only
#   fires at the FIRST tick of the NEXT bar, so "[SELL]/[BUY]" printed but
#   the broker saw nothing until the next minute bar opened (or never, at
#   14:57 close). Sell path switched from order_shares to passorder(24,...)
#   with quickTrade=1; buy path passorder(23,...) now passes quickTrade=1.
#   _sync_holdings keeps today's BUY-ordered-but-unfilled symbols in
#   position_map (marked pending=True) instead of dropping them as "closed",
#   which reset today_bought and let MAX_DAILY_BUY be exceeded (2026-08-12:
#   6 buys instead of 2). _check_sell skips pending positions.
#   today_bought is now counted from order_locks (authoritative) rather than
#   position_map, so a missing/unfilled fill can never inflate the daily buy
#   budget.
# v2.8 changes vs v2.7 (2026-08-12):
#   Remove one-shot DIAG_TEST_BUY_CODE buy-test diagnostic (was for verifying
#   the order channel; no longer needed).
# v2.7 changes vs v2.6 (2026-08-12):
#   Data-layer hardening: all get_market_data_ex callers now catch BaseException
#   (QMT raises non-Exception errors when daily K-line is missing, e.g. it did
#   not pull the previous day's bars -> _annual_vol crashed and killed the bar).
#   Sell path now also uses instrument_detail.PreClose for the daily-move calc
#   (same alternative as the buy path), so anomaly/limit-down guards stay active
#   when yesterday's daily bar is unavailable.
# v2.6 changes vs v2.5 (2026-08-12):
#   Resilience: bar-level guard in handlebar so a data-layer exception in sell
#   logic can never kill the bar before buy logic runs (QMT crashes the whole
#   strategy on any uncaught handlebar exception). _day_vwap/_annual_vol now
#   catch BaseException (QMT data layer can raise non-Exception errors).
# v2.5 changes vs v2.4 (2026-08-12):
#   Diagnostics: log passorder/order_shares return codes (0=accepted, non-zero=
#   rejected) + one-shot [DIAG] of today's broker ORDER list at init. Answers
#   "strategy logged [BUY]/[SELL] but the account page shows nothing".
# v2.4 changes vs v2.3 (2026-08-11):
#   Boards  : per-account board permission filter (ALLOW_STAR / ALLOW_CHINEXT /
#             ALLOW_BSE). Accounts without STAR/CHINEXT/BSE permission skip
#             those candidates and descend to the next rank, instead of
#             sending orders that get rejected and wasting buy slots.
# v2.3 changes vs v2.2 (2026-08-11):
#   Exit   : add VWAP weak-early exit. If a position closes day2 below its
#            day-VWAP (5m amount/volume), sell at day3 open. Full-sample
#            backtest (383 P2 trades, 2026-04~07): maxDD -29.6% -> -21.8%,
#            winrate 50.7% -> 52.5%, median +0.12% -> +0.40%, hold 4.0 -> 3.2d;
#            cost avg return -0.2pp. Only VWAP is a high-quality signal;
#            MA5/volume/return-threshold all harm (early-exit median -3~-5%).
# v2.2 changes vs v2.1 (2026-08-11):
#   Scores  : if local {date}.json / {date}.candidates.json is missing,
#             fetch directly from server nginx (REMOTE_SCORE_BASE) via urllib.
#             Local-first, remote as fallback -> no dependency on local
#             scheduled task. Throttled + silent-fail, retries next bar.
# v2.1 changes vs v2.0 (2026-08-10):
#   Holdings : MAX_HOLDINGS 2 -> 4, POSITION_PCT 0.25 -> 0.15.
#              Daily buy cap split to MAX_DAILY_BUY=2 (was tied to
#              MAX_HOLDINGS). Position sized on TOTAL ASSETS (m_dBalance)
#              so each buy = 15% of total funds (was available cash).
#              Backtest (83d, T+2, fee 0.1%): 4/2/15% -> +56.96% / maxDD
#              -20.84% vs old 2/2/25% +33.62% / -25.92%.
# v2.0 changes vs v1.0 (2026-08-09):
#   Entry  : read C:/alphapilot/scores/{YYYYMMDD}.candidates.json (Top10 pool)
#            + P2 dynamic confirmation (same as server intraday_low.dyn_confirm_price):
#              1) trend: price > P935(09:35 price) and price > VWAP
#              2) volume: last 2 5m bars at least one with vol-ratio>1.3 and up
#              3) no-chase: price <= prev_close * 1.05
#            First-come first-served: iterate candidate pool by rank,
#            buy max MAX_DAILY_BUY (2) per day. 09:35~14:57 observation window.
#            Not triggered by 14:57 -> abandon (no fallback).
#   Exit    : same as v1.0 (adaptive stop + dynamic peel + T+2 force close).
#
#   v1.0 entry (GapSoft C) is preserved in this file as _decide_gap_soft for
#   reference, but _check_buy now uses P2 dynamic confirmation.
#
# Deploy: copy plaintext into D:\guojin_QMT\python\  (QMT python dir)
# Account: 98009473 (QMT SIM trading end, userdata\users\98009473)
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

# ================= CONFIG =================
ACCOUNT_ID = "98009473"
SCORE_DIR = r"C:\alphapilot\scores"
REMOTE_SCORE_BASE = "http://150.158.100.236/qmt_scores"  # server nginx static dir
REMOTE_FETCH_SEC = 60         # min interval between remote fetch attempts
REMOTE_TIMEOUT = 8            # seconds per remote fetch
REMOTE_FETCH_START_MIN = 9 * 60  # don't try remote before 09:00 (server not ready)
TRADE_LOG = r"C:\alphapilot\sim_trades_fullchain.json"
LEDGER_DAILY = r"C:\alphapilot\ledger_daily.json"
LEDGER_DUP_SEC = 300
LEDGER_SNAP_MIN = 15 * 60 + 5
# File-backed daily order lock: QMT schedules handlebar independently per
# bar/symbol, so in-memory sent_today/position_map may not survive across
# calls. Guarantee at most 1 BUY and 1 SELL(reason) per symbol per day.
ORDER_LOCK_FILE = r"C:\alphapilot\order_locks.json"

POS_STATE_FILE = r"C:\alphapilot\sim_pos_state.json"
POS_STATE_PERSIST = (
    "buy_date", "buy_price", "peak", "peel_count", "peel_peak_snapshot",
    "t2_extended", "vwap_broken", "vwap_ref", "wy_bc_armed", "trail_armed",
    "awaiting_new_high", "fusion_scores",
)
FUSION_CLOSED_LOG = r"C:\alphapilot\fusion_closed_trades.jsonl"
FUSION_SOURCE = "qmt_sim"


MAX_HOLDINGS = 4
MAX_DAILY_BUY = 2
POSITION_PCT = 0.22

# --- P2 dynamic confirmation params (aligned with server intraday_low) ---
CONF_VOL_RATIO = 1.3          # 5m volume ratio threshold
CONF_MAX_GAP = 0.08           # legacy uniform cap (superseded by _p2_max_gap)
CONF_DAY_HIGH_MAX = 0.85      # skip if (c-low)/(high-low) > 0.85 (top 15% of range)
CONF_START_MIN = 9 * 60 + 35  # observation window start 09:35
CONF_END_MIN = 14 * 60 + 57   # observation window end 14:57
CONF_MAX_TURNOVER = 5.0       # max daily turnover % (2026-08 full-window backtest: >5% weakens)
P2_MODE = True                # v2.0 default: P2 dynamic confirm entry

# --- P2 sweet-zone priority (v2.25, 2026-08-29) ---
# BT evidence (2026-04~07 synthetic + real 07~08): P2 triggers with open gap
# in [-1.5%, 0] (slight low-open) show upward-bias T+1 vs the rest (7/7 slices
# >=). This is a TRIGGER-ORDER preference, not a scoring change: sweet-zone
# candidates get priority when multiple P2-confirmed candidates race for the
# daily buy slots. Non-sweet candidates still fill remaining slots.
#   SWEET_ZONE_MODE 0 = off (status quo)
#                    1 = priority (sweet first, non-sweet still fill)
#                    2 = only (strictly sweet-zone, fewer trades, bt best)
SWEET_ZONE_MODE = 1
SWEET_GAP_LO = -1.5           # sweet zone = gap% in [LO, HI]
SWEET_GAP_HI = 0.0

# --- ABR (active-buy ratio) gate v2.13 (Level-2 style via mootdx feed) ---
# Backtest 2026-08 (114 candidates / 20 days, real Top10 archives):
#   cumulative ABR >= 0.52 at the P2 trigger lifts T+1 winrate 42.3% -> 54.2%,
#   T+1 mean -0.46% -> +0.36% (low ABR = weak buy force -> filter).
# Source priority: mootdx_feed (separate process, free TDX tick direction,
# day-cumulative, matches backtest P2_cum) -> QMT L1 tick approx (last 120
# ticks, trade px>=ask1=buy). SOFT gate: ABR unavailable -> pass, so a feed
# outage never freezes buying.
USE_ABR_GATE = True
MIN_ACTIVE_BUY = 0.52
ABR_GATE_START_MIN = 9 * 60 + 30   # continuous session only (feed valid)
MOOTDX_FEED_DIR = r"C:\alphapilot\l2_feed"
MOOTDX_FEED_MAX_AGE_SEC = 60       # feed entry older than this -> stale, ignore
USE_MOOTDX_ACTIVE_BUY = True       # master switch; False = keep L1 approx only

# --- board permission filter (v2.4): per-account board access ---
# Unified: one codebase deploys to any account; set False per that account's
# board permission. Disallowed board -> skip that candidate and move to the
# next rank (no wasted buy slot, no rejected order).
# SIM account (98009473): all open. Live: close boards without permission,
# e.g. ALLOW_CHINEXT=False if no ChiNext access, ALLOW_STAR=False if no STAR
# access, ALLOW_BSE=False if no BSE access.
ALLOW_STAR = True             # STAR market 688/689
ALLOW_CHINEXT = True          # ChiNext 300/301
ALLOW_BSE = True              # BSE 8xx/4xx/920

# --- fallback legacy GapSoft C entry (v1.0, keep for reference / rollback) ---
GAP_OPEN_OK = 0.015
GAP_SOFT_LO = 0.03
GAP_HARD_SKIP = 0.05
LIMIT_PREMIUM = 0.01
LIMIT_PREMIUM_SOFT = 0.02
MID_WEIGHT = 0.70

# --- adaptive exit defaults (fallback when no kline) ---
DEF_HARD_STOP = -0.10
DEF_TRAIL_ARM = 0.03
DEF_PEEL_PB = 0.015
PEEL_MAX_STEPS = 2
VOL_BASELINE = 0.30

# --- T+2 force close ---
T2_FORCE_HHMM = 14 * 60 + 45
T2_EXTEND_MIN_PRICE_RATIO = 0.95

# --- T+2 conditional force-close + dynamic weakness rotation (v2.16, 2026-08-18) ---
# Data basis (DHS eval + prod Top2 paired sample, 11 trading days):
#   T+2 profit group holding +1d: mean slightly up but only 44% keep rising,
#     must be backed by peel; T+2 loss group holding +1d: mean -0.82pp, force sell.
#   T+3 profit group holding to T+4: +1.71pp / 62.5% keep rising, but n=14 -> default T+3.
T2_EXTEND_MAX_DAYS = 3          # max hold days for a profitable position (T+3; try 4 for T+4)
T2_EXTEND_PROFIT_MIN = 0.0      # legacy: superseded by the dynamic t2_force floor (v2.17)
# Dynamic T+2 force-close floor (v2.17, 2026-08-19): a wide intraday amplitude
# and high vol name tolerates a deeper normal pullback. A fixed 0% floor
# force-sold healthy names on noise (300591 08-19: buy slip to 8.54 made the
# next day's -1% look like -8.7%; 301130 was force-sold at +33% only because
# the _day_vwap unit bug set vwap_broken). Now ret must fall below the dynamic
# floor to force-sell; hard_stop (hs) still catches the true tail risk.
T2_FORCE_AMP_FRAC = 0.50        # fraction of day amplitude (%) added to the floor
T2_FORCE_AMP_MIN = 4.0          # amplitude below this adds no extra tolerance
T2_FORCE_VOL_K = 0.10           # +0.10 annual vol -> -1pp more tolerance
T2_FORCE_FLOOR_MAX = -0.10      # absolute floor (never below hard_stop)

# Buy-side slip guard (v2.17, 2026-08-19): the P2 trigger is a 5m bar close that
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

# --- VWAP weak-early exit (v2.3) ---
# Full-sample backtest (383 P2 trades): only VWAP is a high-quality signal.
# Confirm on day2 close window (>=14:45), sell at day3 open (09:35-09:50).
VWAP_CONFIRM_MIN = T2_FORCE_HHMM      # same window as T+2 force close
VWAP_SELL_START = 9 * 60 + 35
VWAP_SELL_END = 9 * 60 + 50

# --- Wyckoff distribution (v2.10) ---
# Buy gate: skip candidate when T-1 daily bars show wy_bc or wy_ut.
# Sell early: BC bar while held (peak * 0.98 + upper shadow + 1.5x vol).
WY_BC_WIN = 10            # lookback window for buy climax detection
WY_BC_HI_LOOKBACK = 60    # near-60d high reference
WY_BC_VOL_RATIO = 1.5     # climax volume vs prior 20d avg
WY_BC_SHADOW_FRAC = 0.35  # upper shadow >= 35% of daily range
WY_UT_BOX_DAYS = 20       # box reference days for upthrust
WY_UT_BREAK_PCT = 0.01    # 5d high > box high * 1.01 then closed back inside
WY_BC_SELL_VOL_RATIO = 1.5
WY_BC_SELL_SHADOW_FRAC = 0.35
WY_BC_SELL_NEAR_PEAK = 0.98

# --- safety ---
LIMIT_DOWN_PCT = -9.7
ANOMALY_PCT = -21.0
RESYNC_SEC = 300
UNIV_SEC = 60


# ================= INIT =================
def init(C):
    C.scores_cache = {}
    C.cand_cache = {}
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
    print("[INIT] track-A qmt-sim v2.27 (P2 dyn-confirm + rotation) | acct=" + ACCOUNT_ID +
          " | holdings=" + str(len(codes)) + " | score_dir=" + str(C.score_dir) +
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
        C._univ_dirty = True

    ts = time.time()
    if ts - C._last_resync >= RESYNC_SEC:
        C._last_resync = ts
        _sync_holdings(C)

    cands = _load_candidates(C, today)
    if cands is None:
        scores = _load_scores(C, today)
        if scores is None:
            return
        cands = [{"symbol": c, "name": c, "score": s, "rank": i + 1}
                 for i, (c, s) in enumerate(list(scores.items())[:10])]
    # subscribe candidates (need local 5m data for get_market_data_ex)
    cand = [_qmt_code(x["symbol"]) for x in cands]
    if (getattr(C, '_univ_dirty', True) or
            ts - C._last_univ >= UNIV_SEC or
            cand != getattr(C, '_univ_codes', [])):
        C._last_univ = ts
        C._univ_codes = list(cand)
        C._univ_dirty = False
        try:
            C.set_universe(list(C.position_map.keys()) + cand)
        except BaseException:
            pass

    if not _is_trading_time(now_min):
        return

    # bar-level guard: an uncaught exception inside handlebar crashes the whole
    # strategy in QMT. A data-layer failure in sell logic must never prevent
    # buy logic from running on the same bar (this is exactly the failure mode
    # seen 2026-08-12: _annual_vol -> get_market_data_ex raised and killed the
    # bar before _check_buy could place any order).
    try:
        _check_sell(C, now, now_min, today)
    except BaseException as e:
        print("[SELL-ERR] " + repr(e)[:120])

    try:
        _check_buy(C, now, now_min, today, cands)
    except BaseException as e:
        print("[BUY-ERR] " + repr(e)[:120])

    if now_min >= LEDGER_SNAP_MIN and getattr(C, "_snap_day", "") != today:
        C._snap_day = today
        _snap_daily(C, today, now)


def _is_trading_time(m):
    return (9 * 60 + 30 <= m <= 11 * 60 + 30) or (13 * 60 <= m <= 15 * 60)


# ================= SCORES / CANDIDATES =================
def _find_score_dir():
    for p in (SCORE_DIR, r"D:\alphapilot\scores",
              r"E:\alphapilot\scores",
              os.path.join(os.getcwd(), "scores"), r".\scores"):
        if os.path.exists(p):
            return p
    return SCORE_DIR


def _fetch_remote_scores(C, date_str):
    """Fetch {date}.json / {date}.candidates.json from server nginx if local
    file is missing (Plan A: QMT pulls directly, no local task dependency).
    Throttled to REMOTE_FETCH_SEC, silent-fail (retry on next bar).
    Only attempts after REMOTE_FETCH_START_MIN (server generates ~09:36)."""
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
    for suffix in (".json", ".candidates.json"):
        fpath = os.path.join(C.score_dir, date_str + suffix)
        if os.path.exists(fpath) and os.path.getsize(fpath) > 0:
            continue
        url = REMOTE_SCORE_BASE + "/" + date_str + suffix
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "QMT/2.2"})
            with urllib.request.urlopen(req, timeout=REMOTE_TIMEOUT) as resp:
                body = resp.read()
                if not body:
                    print("[FETCH] " + url + " empty")
                    continue
                with open(fpath, "wb") as f:
                    f.write(body)
                print("[FETCH] " + date_str + suffix + " <- " + url +
                      " (" + str(len(body)) + "b)")
        except Exception as e:
            print("[FETCH] " + url + " fail: " + str(e)[:90])



def _load_scores(C, date_str):
    if date_str in C.scores_cache:
        return C.scores_cache[date_str]
    fpath = os.path.join(C.score_dir, date_str + ".json")
    if not os.path.exists(fpath):
        _fetch_remote_scores(C, date_str)
        if not os.path.exists(fpath):
            return None
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            d = json.load(f)
        C.scores_cache[date_str] = d
        print("[SCORES] " + date_str + " n=" + str(len(d)))
        return d
    except Exception as e:
        print("[SCORES] err: " + str(e))
        return None


def _load_candidates(C, date_str):
    """Top10 candidate pool from {date}.candidates.json (v2.0, prefer this)."""
    if date_str in C.cand_cache:
        return C.cand_cache[date_str]
    fpath = os.path.join(C.score_dir, date_str + ".candidates.json")
    if not os.path.exists(fpath):
        _fetch_remote_scores(C, date_str)
        if not os.path.exists(fpath):
            return None
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            d = json.load(f)
        cands = d.get("candidates") or []
        st_dropped = [it for it in cands if _is_st_name(it.get("name"))]
        if st_dropped:
            cands = [it for it in cands if it not in st_dropped]
            print("[CAND] ST hard drop " + str(len(st_dropped)) + ": "
                  + ", ".join(str(it.get("name")) for it in st_dropped[:10]))
        C.cand_cache[date_str] = cands
        print("[CAND] " + date_str + " n=" + str(len(cands)))
        return cands
    except Exception as e:
        print("[CAND] err: " + str(e))
        return None



# ================= POSITION STATE (persist across QMT restarts) =================
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
    if saved.get("fusion_scores") and not pos.get("fusion_scores"):
        pos["fusion_scores"] = saved["fusion_scores"]


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
    """Print today's orders as seen by the broker. Zero accepted orders while
    the strategy logs [BUY]/[SELL] proves the order never reached the account
    (rejected at passorder layer / wrong account / backtest mode)."""
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
            # v2.19 (2026-08-20): QMT sim leaves m_strOpenDate empty for both
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
                # v2.9: if we ordered BUY today but the fill never landed in
                # the account yet, keep the position marked pending instead of
                # dropping it. Dropping it reset today_bought and let
                # MAX_DAILY_BUY be exceeded (2026-08-12: 6 buys instead of 2).
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


def _get_active_buy_from_mootdx(code):
    """Read day-cumulative active-buy ratio from mootdx_feed local JSON.

    mootdx_feed.py runs as a separate process and writes
    {MOOTDX_FEED_DIR}/{YYYYMMDD}.json = {code: {abr, buy_vol, sell_vol, ts, n}}.
    abr is cumulative over the session (transaction() returns the day's ticks)
    -> same bucket-free cumulative semantics as the backtest P2_cum gate.
    Returns (abr, age_sec) or (None, None) when no fresh entry.
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
    """Active buy ratio: mootdx real ticks first, then QMT L1 tick approx.

    mootdx feed (free TDX per-tick buy/sell direction) preferred when fresh.
    Fallback: last 120 L1 ticks, trade px >= ask1 -> active buy, <= bid1 ->
    active sell (only counted, not neutral). Returns None when no data.
    """
    abr, age = _get_active_buy_from_mootdx(code)
    if abr is not None:
        return abr
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


def _get_turnover(C, code):
    """Daily turnover % = today's cumulative volume / float shares.

    QMT volume unit is shares (same as backtest), FloatShares from
    get_instrument_detail is also shares, so ratio is self-consistent.
    Returns None on failure.
    """
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


def _is_limit_up(C, code):
    """True if current price is sealed at the limit-up price (cannot buy).

    Uses UpStopPrice from get_instrument_detail (most reliable: handles
    10%/20%/30% and ST boards automatically). Falls back to False on error
    so a data hiccup never blocks a valid candidate.
    """
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


def _is_st_name(name):
    """ST/risk-warning guard (QMT client, 2026-08-25). Missing name -> False."""
    n = str(name or "").strip().upper()
    if not n:
        return False
    _dl = "\u9000"
    _dl2 = "\u9000\u5e02"
    return "ST" in n or n.startswith(_dl) or _dl2 in n


def _board_allowed(code):
    """Board permission filter (v2.4). True if this account can trade the
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
    """Prev close. Prefer instrument_detail.PreClose (most reliable; in QMT
    sim, daily bars with count=2 often fail to return yesterday so _get_quote's
    prev degenerates to today's realtime price, breaking no-chase protection)."""
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
    tmin is minutes since midnight (e.g. 09:35 = 575). Only today's bars are
    kept. (v2.13, 2026-08-18) QMT get_market_data_ex(count=48) without
    start_time can return previous days' 5m bars early in the session; the old
    code reverse-engineered the bar time via CONF_START_MIN + i*5 and never
    filtered by date, so P2's p935 / VWAP / volume-MA5 were computed on stale
    bars. Now start_time pins today and real timestamps are kept."""
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
    None on fail.
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
    """20-day annualized volatility (0.10~0.80). Pure python (no numpy)."""
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


# ================= WYCKOFF DISTRIBUTION (v2.10) =================
def _wyckoff_distribution(C, code):
    """Buy gate: True if T-1 daily bars show wy_bc or wy_ut (distribution).

    As-of: uses daily bars strictly before today. QMT sim daily bars can be
    unreliable; on any data failure we return False (never block a valid
    candidate on a data hiccup). Backtest: 40/386 skipped (10.4%), avg
    +3.10% -> +3.40%, skipped trades weak (avg +0.53%).
    """
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
        # Drop the last element: it is today's (partial) bar. T-1 is index n-2.
        hi = hi[: n - 1]
        lo = lo[: n - 1]
        cl = cl[: n - 1]
        op = op[: n - 1]
        vo = vo[: n - 1]
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
                    if cl[k] < op[k] or tail > (hi[k] - lo[k]) * WY_BC_SHADOW_FRAC:
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


def _wyckoff_holding_bc(C, code, peak):
    """Sell early: True if today's 5m bars print a buy-climax bar while held.

    Bar qualifies: high >= peak * 0.98 (near holding peak), volume > 20d avg
    * 1.5, and a long upper shadow or red close. Uses today's 5m bars + daily
    volume reference. Backtest: win 50.7% -> 55.4%, med +1.37%, maxDD -22.5%.
    """
    if peak <= 0:
        return False
    try:
        # 20d avg daily volume (volume, shares) from daily bars before today.
        # NOTE: use "volume" not "amount" -- today_v below is a 5m volume sum,
        # so both sides must be shares (volume-vs-volume, matches bt_wyckoff_sell).
        data = C.get_market_data_ex(
            ["volume"], [code], period="1d", count=22, subscribe=True)
        if not data or not isinstance(data, dict) or code not in data:
            return False
        vols = _col(data[code], "volume")
        if len(vols) < 6:
            return False
        # last element is today's partial bar; drop it, then prior 20
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
    # daily volume so far today (5m sum), compare to 20d avg
    today_v = sum(b[5] for b in bars)
    if today_v <= vma20 * WY_BC_SELL_VOL_RATIO:
        return False
    # find a BC bar: near holding peak + long upper shadow
    for b in bars:
        _, o, c, h, l, _ = b
        if h >= peak * WY_BC_SELL_NEAR_PEAK:
            body_top = max(o, c)
            tail = h - body_top
            rng = h - l
            if (c < o or (rng > 0 and tail > rng * WY_BC_SELL_SHADOW_FRAC)):
                return True
    return False


# ================= P2 DYNAMIC CONFIRM ENTRY (v2.0) =================
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


def _sweet_gap_pct(C, code):
    """Open gap% = (open/prev_close - 1)*100 for sweet-zone check.
    Uses _get_quote (price, prev, open, high); open = today's open."""
    try:
        price, prev, open_, high = _get_quote(C, code)
        if not prev or prev <= 0 or not open_ or open_ <= 0:
            return None
        return (open_ / prev - 1.0) * 100.0
    except BaseException:
        return None


def _is_sweet_zone(C, code):
    """True if this candidate's open gap is in the P2 sweet zone."""
    if SWEET_ZONE_MODE <= 0:
        return False
    g = _sweet_gap_pct(C, code)
    if g is None:
        return False
    return (SWEET_GAP_LO - 1e-9) <= g <= (SWEET_GAP_HI + 1e-9)


def _order_cands_by_sweet(C, cands):
    """Trigger-order preference (v2.25): sweet-zone candidates first when they
    race for the daily buy slots. SWEET_ZONE_MODE=1 sorts (sweet first, others
    by rank); =2 keeps only sweet-zone names. Returns a new list."""
    if SWEET_ZONE_MODE <= 0:
        return cands
    out = []
    for item in cands:
        code = _qmt_code(item.get("symbol"))
        if SWEET_ZONE_MODE == 2 and not _is_sweet_zone(C, code):
            print("[SWEET] " + code + " not in sweet zone, skip (mode=2)")
            continue
        out.append(item)
    if SWEET_ZONE_MODE == 1:
        out.sort(key=lambda it: (0 if _is_sweet_zone(C, _qmt_code(it.get("symbol")))
                                 else 1, int(it.get("rank") or 0)))
    return out


def _p2_day_high_ok(c, day_high, day_low):
    rng = day_high - day_low
    if rng <= 0:
        return True
    return (c - day_low) / rng <= CONF_DAY_HIGH_MAX


def _p2_decide(C, code, now_min):
    """P2 dynamic confirmation. Returns (fill_price or None, reason).

    reason: "dyn_confirm" | "wait_confirm" | "no_confirm_eod" | "no_quote" | "no_m5"
    """
    price, prev, open_, high = _get_quote(C, code)
    last = _get_last(C, code) or price
    if not price or price <= 0:
        return None, "no_quote"
    # prev close: prefer instrument_detail.PreClose (QMT sim daily bars often
    # fail to return yesterday, so _get_quote's prev degenerates to today's
    # realtime price, which would silently disable no-chase protection).
    pc = _get_prev_close(C, code)
    if pc:
        prev = pc
    if not prev or prev <= 0:
        return None, "no_quote"

    # observation window
    if now_min > CONF_END_MIN:
        return None, "no_confirm_eod"
    if now_min < CONF_START_MIN:
        return None, "wait_confirm"

    # turnover gate: skip if daily turnover > CONF_MAX_TURNOVER (backtest: >5% weakens).
    # QMT 1d volume is cumulative during the session, aligned with backtest turnover_t.
    # If data unavailable (None) do not block, to avoid missing opportunities.
    _to = _get_turnover(C, code)
    if _to is not None and _to > CONF_MAX_TURNOVER:
        return None, "skip_high_turnover"

    bars = _get_m5_bars(C, code)
    if bars is None:
        return None, "no_m5"

    today_bars = [b for b in bars if b[0] >= CONF_START_MIN]
    if not today_bars:
        return None, "wait_confirm"

    # Rolling session low replaces P935 as the trend reference (v2.21).
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
        # 1) dynamic trend: climbing from rolling session low (not vs P935/open)
        if not (day_low > 0 and c > day_low and vwap > 0 and c > vwap):
            continue
        # 2) volume: last 2 bars at least one with vol-ratio > CONF_VOL_RATIO and up
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
        if c > prev * (1 + gap_lim):
            continue
        # 4) day-high guard: avoid buying in top 15% of intraday range
        if not _p2_day_high_ok(c, day_high, day_low):
            continue
        trig_px = c
        break

    if trig_px and trig_px > 0:
        if USE_ABR_GATE and now_min >= ABR_GATE_START_MIN:
            abr = _get_active_buy_ratio(C, code)
            if abr is not None and abr < MIN_ACTIVE_BUY:
                return None, "skip_low_abr"
        return round(trig_px, 2), "dyn_confirm"
    if now_min >= CONF_END_MIN:
        return None, "no_confirm_eod"
    return None, "wait_confirm"


# ================= SELL (adaptive exit, same as v1.0) =================
def _check_sell(C, now, now_min, today):
    for code, pos in list(C.position_map.items()):
        if pos.get("pending"):
            # v2.9: BUY ordered today but not yet filled -> nothing real to
            # sell yet, and it must not be sold before it actually exists.
            continue
        price, prev, open_, high = _get_quote(C, code)
        if price is None or price <= 0 or pos.get("buy_price", 0) <= 0:
            continue
        # prev close: prefer instrument_detail.PreClose. QMT sim daily bars
        # often fail to return yesterday (same issue that killed _annual_vol
        # on 2026-08-12), which would silently zero out the daily move and
        # disable the anomaly/limit-down guards. PreClose is the reliable
        # source (same alternative the buy path uses in _p2_decide).
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

        # limit-down: allowed even on T+1 buy day
        if daily <= LIMIT_DOWN_PCT:
            _do_sell(C, code, pos, price,
                     "limit_down daily=" + str(round(daily, 1)) + "%")
            continue

        bd = pos.get("buy_date", "")
        is_today_buy = (bd == today)
        if is_today_buy:
            continue  # T+1: cannot sell today's buy (except limit-down)

        # Wyckoff buy-climax early exit (v2.10): if today's bars print a
        # climax bar near the holding peak (long upper shadow + 1.5x vol),
        # sell at next open. Confirmed only in the close window so the daily
        # volume comparison is meaningful; fires on the next day's open.
        if (not pos.get("wy_bc_armed") and now_min >= VWAP_CONFIRM_MIN and
                _wyckoff_holding_bc(C, code, pos.get("peak", cost))):
            pos["wy_bc_armed"] = True
            print("[BC] " + code + " holding buy-climax px=" +
                  str(round(price, 2)) + " peak=" + str(round(pos.get("peak", 0), 2)))
        if pos.get("wy_bc_armed") and VWAP_SELL_START <= now_min <= VWAP_SELL_END:
            _do_sell(C, code, pos, price, "wyckoff_bc " +
                     str(round(ret, 1)) + "%")
            continue

        # VWAP weak-early exit (v2.3): if day2 closes below day-VWAP, sell at
        # day3 open. In production the T+2 block below force-closes (<95% cost)
        # or extends (+1d) at 14:45 on day2, so this only matters for positions
        # that survive to day3 (extended). Confirm on the same window as T+2,
        # then fire on the next open.
        if not pos.get("vwap_broken") and now_min >= VWAP_CONFIRM_MIN:
            vw = _day_vwap(C, code)
            if vw and vw > 0 and price < vw:
                pos["vwap_broken"] = True
                pos["vwap_ref"] = vw
                print("[VWAP] " + code + " day-vwap broken px=" +
                      str(round(price, 2)) + " vwap=" + str(round(vw, 2)) +
                      " ret=" + str(round(ret, 1)) + "%")
        # v2.26: next-morning confirm. Unconditional next-open sell sold the
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

        # hard stop: close-confirm window only (>=14:45)
        if now_min >= T2_FORCE_HHMM and ret <= hs * 100:
            _do_sell(C, code, pos, price,
                     "hard_stop " + str(round(ret, 1)) + "% vs " +
                     str(round(hs * 100, 1)) + "%")
            continue

        # T+2 conditional force-close (v2.17, 2026-08-19): dynamic floor force-sell + profit extend T+3 (peel guards)
        if now_min >= T2_FORCE_HHMM:
            hold_days = _hold_days(pos, today)
            if pos.get("t2_extended"):
                # already extended: force-sell at maturity (hold_days >= T2_EXTEND_MAX_DAYS)
                # only. v2.17 fix: the old code sold on the very next 14:45 pass, so
                # T2_EXTEND_MAX_DAYS=3 bought just 1 extra day instead of the intended
                # T+3. Inside the window the position keeps running with the trailing
                # peel / vwap_weak_early / wyckoff_bc exits still armed.
                # v2.19: hold_days == 999 means buy_date is unknown (never extended
                # without one), so never treat it as past maturity.
                if hold_days != 999 and hold_days >= T2_EXTEND_MAX_DAYS:
                    _do_sell(C, code, pos, price,
                             "t2_force_after_extend " + str(round(ret, 1)) + "%")
                    continue
            else:
                # v2.17: dynamic floor instead of fixed 0%. A wide-amplitude / high-vol
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
                # v2.17 (2026-08-19): do NOT let vwap_broken / wy_bc_armed short-circuit
                # the dynamic floor. Both are NEXT-MORNING (09:35-09:50) exit signals:
                # 300591 08-19 fair-cost -1.0% was force-sold only because vwap_broken
                # set in the same 14:45 pass (price 7.80 < vwap 8.05) hit this branch
                # before the floor (-4.45%) could hold it. After extension the T+3
                # morning window fires vwap_weak_early / wyckoff_bc. Only hold-cap and
                # hard-stop refuse to extend.
                # v2.19: hold_days == 999 (buy_date unknown) must not be read as
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

        # dynamic peel (intraday, profit only)
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


# ============ Sell-side rework v2.16: T+2 conditional + dynamic weakness rotation (2026-08-18) ============
def _hold_days(pos, today):
    """Holding days from buy_date -> today (buy day excluded). buy_date is %Y%m%d
    (e.g. 20260818). The DHS patch parsed it as %Y-%m-%d, which mismatched v2.14's
    format -> ValueError -> 999 -> rotation never found a sellable position.
    Now unified on %Y%m%d, with a 'YYYY-MM-DD' fallback.
    v2.27: counts TRADING days (weekends + 2026 A-share closures excluded),
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


def _volume_ratio_of(C, code):
    """Volume ratio = today cum vol / prior 5d same-time cum vol mean (aligned
    with Track B v1.1 same-time window to avoid 09:35 structural under-count).
    None on fail (momentum guard soft-skips)."""
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
        cur = sum(float(v) for v in vols[n - k:n] if v == v)
        if cur <= 0:
            return None
        base_list = []
        for d in range(1, 6):
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


def _weakness_score(C, today):
    """Weakness score 0~1 per holding, higher = more likely to sell. Only
    sellable positions are scored (not pending, held >= ROTATION_MIN_HOLD_DAYS).
    Relative-rank normalized (0~1) + momentum guard (daily > 3% and rising vol
    -> skip). Returns (all_cands_sorted, sellable)."""
    cands = []
    for c, p in list(C.position_map.items()):
        if p.get("pending"):
            continue
        if _hold_days(p, today) < ROTATION_MIN_HOLD_DAYS:
            continue
        pq, pp, po, ph = _get_quote(C, c)
        if pq is None or pq <= 0 or p.get("buy_price", 0) <= 0:
            continue
        pc2 = _get_prev_close(C, c)
        pret = (pq / p["buy_price"] - 1) * 100
        pday = (pq / pc2 - 1) * 100 if pc2 and pc2 > 0 else 0.0
        vw = _day_vwap(C, c)
        vwap_break = 1.0 if (vw and pq < vw) else 0.0
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
        vr = _volume_ratio_of(C, it["code"])
        if (it["day"] > ROTATION_MOMENTUM_DROP_PCT and
                (vr or 0) > ROTATION_MOMENTUM_VOL_RATIO):
            it["skip"] = True

    def _rank01(vals, invert=False):
        """Rank values ascending to 0~1; invert=True flips (big value = high weak score).
        FIXED vs DHS draft: enumerate sorted positions, not the raw list order,
        otherwise duplicate values get an arbitrary rank and a strong name can
        be mis-scored as the weakest."""
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
    """When holdings are full (MAX_HOLDINGS) and a new Top2 passed P2, sell the
    weakest position to free a slot. Prefers peel half (when profitable), else
    full sell. Returns the codes actually sold. _do_sell/_do_sell_half pop
    position_map on success, so the caller can buy immediately after."""
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
            ret = (price / pos["buy_price"] - 1) * 100 if price else 0
            if (ret > 0 and (pos.get("peel_count") or 0) < PEEL_MAX_STEPS
                    and pos["shares"] >= 400):
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
    # derive a stable per-reason key (e.g. "peel_half1", "t2_force") so a
    # multi-step peel can fire once per step, but identical reasons dedup.
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
        # v2.12: never ask the broker for more than the tradable quantity.
        # Stale in-memory shares (sync race after a peel_half) used to fire
        # over-sized sells the broker rejected with [251005] insufficient qty.
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
        # v2.9: passorder(24,...) with quickTrade=1 fires immediately. The old
        # order_shares is K-line driven (=quickTrade=0) and only sends at the
        # first tick of the NEXT bar, so sells printed but never reached the
        # broker in realtime.
        ret = passorder(24, 1101, ACCOUNT_ID, code, 5, -1, vol,
                        "fullchain", 1, "", C)
        if ret != 0:
            # v2.11: rejected sell -> no lock, no trade log, keep position so
            # it is retried next period (2026-08-14: rejected sell of 301202
            # wrote a fake SELL trade + dropped the position while the broker
            # still held it).
            print("[SELL] " + code + " " + reason + " all " + str(vol) +
                  "sh order REJECTED ret=" + str(ret) + " (no lock, retry)")
            return
        _mark_order_locked(today, code, lockk)
    except BaseException as e:
        print("[SELL] order fail: " + str(e))
        return
    _log_trade(C, "SELL", code, price, vol, reason, pos=pos)
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
        # v2.9: passorder quickTrade=1 -> immediate fire (order_shares was
        # K-line driven and only sent at the next bar's first tick).
        ret = passorder(24, 1101, ACCOUNT_ID, code, 5, -1, half,
                        "fullchain", 1, "", C)
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
    _log_trade(C, "SELL_HALF", code, price, half, reason, pos=pos)
    _save_pos_state(C)


# ================= BUY (P2 first-come, v2.0) =================
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


def _check_buy(C, now, now_min, today, cands):
    # v2.25: sweet-zone trigger priority -- reorder candidates before the
    # race for the daily buy slots (no scoring change, ordering only)
    cands = _order_cands_by_sweet(C, cands)
    if len(C.position_map) >= MAX_HOLDINGS:
        # v2.16 rotation: holdings full and a candidate passed P2 -> first sell
        # the weakest position to free a slot (P1). Evaluate the candidate first
        # (P2 gating precedes) so we never sell a position for a weak name.
        worth_buy = False
        for item in cands:
            code = _qmt_code(item.get("symbol"))
            if code in C.position_map or code in C.sent_today:
                continue
            if _order_locked(today, code, "BUY"):
                continue
            fill, reason = _p2_decide(C, code, now_min)
            if fill is not None:
                worth_buy = True
                break
        if not worth_buy:
            print("[BUY] skip: holdings full & no P2-confirmed candidate")
            return
        sold = _rotation_sell(C, now, now_min, today, ROTATION_SELL_N)
        if not sold:
            print("[BUY] skip: holdings full & rotation sold nothing")
            return
        # sold ok, continue below (re-query cash; A-share T+0 recycle)
    acct = None
    cash = 0.0
    total_asset = 0.0
    try:
        acct = get_trade_detail_data(ACCOUNT_ID, "STOCK", "ACCOUNT") or []
        if acct:
            cash = float(getattr(acct[0], "m_dAvailable", 0) or 0)
            # m_dBalance = total assets (confirmed by QMT docs); fall back to
            # available cash if the field is absent on some broker builds
            total_asset = float(getattr(acct[0], "m_dBalance", 0) or 0)
    except BaseException as e:
        cash = 0.0
        print("[CASH] acct query fail acct=" + ACCOUNT_ID +
              " n=" + str(len(acct) if acct else 0) +
              " err=" + str(e)[:80])
    if cash <= 0:
        if C.run_count % 60 == 0:
            print("[CASH] cash=" + str(cash) + " acct=" + ACCOUNT_ID +
                  " n=" + str(len(acct) if acct else 0))
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

    # v2.11: no more silent break -- log why we refuse to buy
    if today_bought >= MAX_DAILY_BUY:
        print("[BUY] today_bought=" + str(today_bought) +
              " >= MAX_DAILY_BUY=" + str(MAX_DAILY_BUY) + " skip all")
        return

    for item in cands:
        code = _qmt_code(item.get("symbol"))
        rank = int(item.get("rank") or 0)
        if code in C.position_map:
            continue
        if code in C.sent_today:
            continue
        if len(C.position_map) >= MAX_HOLDINGS:
            break
        if today_bought >= MAX_DAILY_BUY:
            break
        # file-level dedup: guard against repeated passorder from separate
        # handlebar invocations that do not share in-memory sent_today
        if _order_locked(today, code, "BUY"):
            print("[LOCK] " + code + " BUY skip (already ordered today)")
            continue

        # board permission: account cannot trade this board -> skip rank,
        # never spend a buy slot or produce a rejected order (v2.4)
        if not _board_allowed(code):
            print("[SKIP] " + code + " board not allowed rank=" + str(rank))
            C.sent_today.add(code)
            continue

        if _is_st_name(item.get("name")):
            print("[ST] " + code + " " + str(item.get("name") or "") + " skip (risk-warning)")
            C.sent_today.add(code)
            continue

        if _item_fund_hard_fail(item):
            print("[FUND] " + code + " fund_hard_fail skip rank=" + str(rank))
            C.sent_today.add(code)
            continue

        # limit-up sealed board: cannot fill, skip this rank for today
        if _is_limit_up(C, code):
            print("[WAIT] " + code + " limit-up rank=" + str(rank) +
                  " skip for today")
            C.sent_today.add(code)
            continue

        # Wyckoff distribution buy gate (v2.10): T-1 daily bars show
        # buy climax (wy_bc) or upthrust (wy_ut) -> skip this candidate today.
        if _wyckoff_distribution(C, code):
            print("[WYCKOFF] " + code + " distribution (bc/ut) rank=" +
                  str(rank) + " skip for today")
            C.sent_today.add(code)
            continue

        # P2 dynamic confirmation -> fill at realtime
        fill, reason = _p2_decide(C, code, now_min)
        if fill is None:
            # no_confirm_eod (past 14:57), skip_high_turnover (turnover
            # accumulates monotonically, will not fall back below the cap
            # intraday) and skip_low_abr (ABR confirmed weak at P2 trigger)
            # abandon the candidate for today. Others
            # (no_quote/no_m5/wait_confirm) are transient -> retry next period,
            # otherwise one quote hiccup kills the candidate for the whole day
            # and realtime monitoring silently misses a valid buy.
            if reason in ("no_confirm_eod", "skip_high_turnover",
                          "skip_low_abr"):
                print("[WAIT] " + code + " P2=" + reason +
                      " rank=" + str(rank) + " abandon for today")
                C.sent_today.add(code)
            else:
                print("[WAIT] " + code + " P2=" + reason +
                      " rank=" + str(rank) + " retry next period")
            continue

        # v2.17 slip guard (2026-08-19): the P2 trigger is a 5m bar close that
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

        shares = int(total_asset * POSITION_PCT / fill / 100) * 100
        if shares < 100:
            print("[SKIP] " + code + " insufficient cash")
            continue
        # cap to available cash (position sized on total assets, but we can
        # only spend what is free today)
        max_cash_shares = int(cash / fill / 100) * 100
        if max_cash_shares < 100:
            print("[SKIP] " + code + " insufficient cash")
            continue
        shares = min(shares, max_cash_shares)
        try:
            # v2.9: quickTrade=1 -> fire immediately (default 0 is K-line
            # driven and only sends at the next bar's first tick, so the
            # order printed but never reached the broker in realtime).
            ret = passorder(23, 1101, ACCOUNT_ID, code, 5, -1, shares,
                            "fullchain", 1, "", C)
            if ret != 0:
                # v2.11: passorder non-zero = REJECTED. Never write lock /
                # position / trade log on a rejected order: those fake records
                # consumed today_bought and silently blocked every later buy
                # (2026-08-14: account had ZERO broker orders but lock+trades
                # were written for 000938/688180 at 11:07, then no buys all day).
                print("[BUY] " + code + " x" + str(shares) +
                      " order REJECTED ret=" + str(ret) +
                      " (no lock written) rank=" + str(rank))
                C.sent_today.add(code)
                continue
            C.sent_today.add(code)
            _mark_order_locked(today, code, "BUY")
            C.position_map[code] = {
                "shares": shares,
                "buy_price": fill,
                "name": item.get("name") or code,
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
                "fusion_scores": _fusion_from_item(item, C.cand_cache.get(today) or []),
            }
            today_bought += 1
            sweet_tag = " SWEET" if _is_sweet_zone(C, code) else ""
            print("[BUY] " + code + " x" + str(shares) + " @ " +
                  str(round(fill, 2)) + " P2=dyn_confirm rank=" + str(rank) +
                  sweet_tag)
            _log_trade(C, "BUY", code, fill, shares, "p2_dyn_confirm",
                       pos=C.position_map[code])
            _save_pos_state(C)
        except BaseException as e:
            print("[BUY] order fail: " + str(e))
            # mark as attempted anyway so we don't spam retries on a
            # limit-up board that keeps rejecting the order
            C.sent_today.add(code)


# ================= LEDGER (auto bookkeeping) =================
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
    sdir = SCORE_DIR
    try:
        sdir = getattr(C, "score_dir", None) or SCORE_DIR
    except Exception:
        sdir = SCORE_DIR
    fpath = os.path.join(sdir, ymd + ".candidates.json")
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


def _log_trade(C, action, code, price, vol, reason, pos=None):
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
        _append_fusion_closed(action, code, price, vol, pos)
    except Exception:
        pass


def _snap_daily(C, today, now):
    """End-of-day snapshot: positions + realized/unrealized P&L estimate."""
    try:
        pos_list = []
        for code, pos in C.position_map.items():
            shares = int(pos.get("shares") or 0)
            cost = float(pos.get("buy_price") or pos.get("cost") or 0)
            if shares <= 0:
                continue
            # latest price from quote (fallback to cost)
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
        # realized P&L for the day from this session's trades
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
