# -*- coding: utf-8 -*-
# AlphaPilot -- Track A Ptrade SIM strategy v1.7 (vwap 2nd confirm)
# File: TrackA_track_a_ptrade_sim.py
# =========================================================
# v1.7 changes vs v1.6 (2026-09-02, vwap 2nd confirm):
#   * vwap_weak_early needs TWO still-below minutes. Aligned with QMT v2.30.
# v1.6 changes vs v1.5 (2026-09-01, rotation off):
#   * ROTATION_ENABLE=False. Aligned with QMT v2.29.
# v1.5 changes vs v1.4 (2026-09-01, rank<=2 P2 gate):
#   * MAX_CAND_RANK=2: only 09:35 candidates.json rank 1-2 may enter P2
#     (incl. rotation worth_buy). Rank 3+ never race. Missing rank skipped.
#     P2 itself unchanged. Aligned with QMT v2.28.
# v1.4 changes vs v1.3 (2026-08-31, trading-day hold fix):
#   * _hold_days counts TRADING days, not calendar days. The old
#     (today - buy_date).days counted weekends/holidays, so a Friday buy read
#     as hold=3 on the following Monday (real T+1) and wrongly hit
#     t2_force_after_extend / rotation_sell. New _ASHARE_CLOSED_2026 set +
#     _trading_days_between(); only weekend + 2026 official closures excluded.
# v1.3 changes vs v1.2 (2026-08-31, vwap_weak_early next-morning confirm):
#   * Sell at next open only if the live price is still BELOW the day-VWAP
#     reference recorded when the signal armed (price < vwap_ref). If the price
#     has recovered above the reference, cancel the signal and keep holding.
#     Evidence (QMT sim 08-31, n=3): unconditional next-open sell hit the day's
#     low and all three rallied +3.5%/+3.8%/+7.0%. New persisted field vwap_ref.
# v1.2 changes vs v1.1 (2026-08-27, position state persistence):
#   * Persist sell-side metadata to ptrade_tracka_pos_state.json (auto read/write).
#   * _recover_buy_date reads persisted state before trade log.
# v1.1 changes vs v1.0 (2026-08-20, T+1 winner force-sell fix):
#   * _sync_holdings recovers buy_date from context.memo trade_log when the
#     broker leaves open date empty after a restart and T+1 already unlocked
#     (000651 QMT-SIM 08-20: +1.5% T+1 wrongly sold as t2_force_after_extend).
#   * _check_sell T+2 maturity check adds hold_days != 999 guard.
# Port of production_strategies/track_a/TrackA_track_a_qmt_full_chain_sim.py
# (QMT v2.18) to the Ptrade (Hundsun) platform. Ptrade runs on the broker's
# cloud VM, so:
#   * the strategy is a SINGLE self-contained file (helpers are inlined below);
#   * scores are delivered by HTTP (whitelist) OR upload_files (see adapter);
#   * code format is .SS (Shanghai) / .SZ (Shenzhen) / .BJ (BSE);
#   * ABR gate: L2 get_individual_transaction when available, else snapshot
#     inner/outer volume, else soft-pass (same semantics as the QMT mootdx
#     soft gate).
# All entry/exit/rotation logic is byte-for-byte faithful to QMT v2.18
# (dynamic T+2 force floor, slip guard, weakness rotation, T+1 immunity,
#  daily rotation cap, hysteresis gate, VWAP weak-early, Wyckoff BC).
#
# Deploy: paste into a Ptrade strategy (simulation account), set period to
# "minute", then run in SIM. After sim validation, clone to LIVE template.
# Pure ASCII. No f-strings (legacy Ptrade VM = Py3.5+).
#
# ================= CONFIG =================
# --- score delivery ---
REMOTE_SCORE_BASE = "http://150.158.100.236/qmt_scores"  # server nginx; needs broker whitelist
REMOTE_FETCH_START_MIN = 9 * 60     # don't try remote before 09:00
REMOTE_FETCH_SEC = 60               # min interval between remote attempts
REMOTE_TIMEOUT = 5
# upload_files / research fallback (see load_score_file): set to "" to disable
UPLOAD_DIR = ""                     # e.g. "" uses get_research_path()+"/upload_files"
RESEARCH_EXTRA = ""                 # extra local dir relative to research root

# --- account / sizing ---
MAX_HOLDINGS = 4
MAX_DAILY_BUY = 2
MAX_CAND_RANK = 2              # only 09:35 candidates.json rank 1-2 may enter P2; 0=off
POSITION_PCT = 0.15

# --- P2 dynamic confirmation (aligned with server intraday_low) ---
CONF_VOL_RATIO = 1.3
CONF_MAX_GAP = 0.08
CONF_DAY_HIGH_MAX = 0.85
CONF_START_MIN = 9 * 60 + 35        # observation window start 09:35
CONF_END_MIN = 14 * 60 + 57         # observation window end 14:57
CONF_MAX_TURNOVER = 5.0
P2_MODE = True

# --- ABR (active-buy ratio) gate ---
# L2 first (get_individual_transaction), else snapshot in/out volume, else
# soft-pass. MIN_ACTIVE_BUY / start minute kept identical to QMT v2.13.
USE_ABR_GATE = True
MIN_ACTIVE_BUY = 0.52
ABR_GATE_START_MIN = 9 * 60 + 30

# --- board permission filter ---
ALLOW_STAR = True
ALLOW_CHINEXT = True
ALLOW_BSE = True

# --- legacy GapSoft C entry (kept for reference / rollback) ---
GAP_OPEN_OK = 0.015
GAP_SOFT_LO = 0.03
GAP_HARD_SKIP = 0.05
LIMIT_PREMIUM = 0.01
LIMIT_PREMIUM_SOFT = 0.02
MID_WEIGHT = 0.70

# --- adaptive exit defaults ---
DEF_HARD_STOP = -0.10
DEF_TRAIL_ARM = 0.03
DEF_PEEL_PB = 0.015
PEEL_MAX_STEPS = 2
VOL_BASELINE = 0.30

# --- T+2 force close ---
T2_FORCE_HHMM = 14 * 60 + 45
T2_EXTEND_MIN_PRICE_RATIO = 0.95
T2_EXTEND_MAX_DAYS = 3
T2_EXTEND_PROFIT_MIN = 0.0      # legacy: superseded by the dynamic floor
# dynamic floor (v2.17)
T2_FORCE_AMP_FRAC = 0.50
T2_FORCE_AMP_MIN = 4.0
T2_FORCE_VOL_K = 0.10
T2_FORCE_FLOOR_MAX = -0.10
# buy-side slip guard (v2.17)
MAX_BUY_SLIP_PCT = 0.02

# --- rotation (v2.16; off since v1.6, rank<=2 ~1 buy/day) ---
ROTATION_ENABLE = False
ROTATION_SELL_N = 1
ROTATION_MIN_HOLD_DAYS = 2
ROTATION_DAILY_MAX = 1
ROTATION_WEAK_GATE = True
ROTATION_MOMENTUM_DROP_PCT = 3.0
ROTATION_MOMENTUM_VOL_RATIO = 1.3
W_WEAK_RET = 0.30
W_WEAK_VWAP = 0.20
W_WEAK_DAY = 0.20
W_WEAK_EARLY = 0.15
W_WEAK_PEEL = 0.10
W_WEAK_DAYS = 0.05

# --- VWAP weak-early exit (v2.3) ---
VWAP_CONFIRM_MIN = T2_FORCE_HHMM
VWAP_SELL_START = 9 * 60 + 35
VWAP_SELL_END = 9 * 60 + 50

# --- Wyckoff distribution (v2.10) ---
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

# --- ledger / locks (research path; Ptrade may deny FS writes -> in-memory) ---
LEDGER_DUP_SEC = 300
LEDGER_SNAP_MIN = 15 * 60 + 5

POS_STATE_PERSIST = (
    "buy_date", "buy_price", "peak", "peel_count", "peel_peak_snapshot",
    "t2_extended", "vwap_broken", "vwap_ref", "vwap_early_hits", "vwap_early_min",
    "wy_bc_armed", "trail_armed",
    "awaiting_new_high",
)

# =========================================================
# ADAPTER: code format / files / quotes / kline / account / order
# (canonical copy lives in ptrade_adapter.py; keep in sync)
# =========================================================
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

try:
    import urllib.request as _urlreq
except Exception:
    _urlreq = None


def _log(msg):
    try:
        print(msg)
    except Exception:
        pass


def to_ptrade_code(code):
    s = str(code or "").strip().upper()
    if not s:
        return ""
    s = s.replace("SH", "").replace("SS", "").replace("SZ", "").replace("BJ", "")
    s = "".join(ch for ch in s if ch.isdigit())
    if len(s) < 6:
        return str(code or "").strip()
    c6 = s[-6:]
    if c6[0] in ("6", "9", "5"):
        return c6 + ".SS"
    if c6[0] in ("0", "2", "3"):
        return c6 + ".SZ"
    return c6 + ".BJ"


def to_6(code):
    s = str(code or "").strip().upper()
    return "".join(ch for ch in s if ch.isdigit())[-6:]


def _research_path():
    try:
        return str(get_research_path())
    except Exception:
        return ""


def _http_get(url, timeout=5):
    if _urlreq is None:
        return None
    try:
        req = _urlreq.Request(url, headers={"User-Agent": "AlphaPilot/1.0"})
        with _urlreq.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
        return body if body else None
    except Exception:
        return None


def load_score_file(name, cache, allow_http=True):
    if name in cache:
        return cache[name]
    data = None
    if allow_http and REMOTE_SCORE_BASE:
        body = _http_get(REMOTE_SCORE_BASE.rstrip("/") + "/" + name,
                         timeout=REMOTE_TIMEOUT)
        if body:
            try:
                data = json.loads(body.decode("utf-8", "replace"))
            except Exception:
                data = None
            if data is not None:
                cache[name] = data
                _log("[FILE] " + name + " <- HTTP ok")
                return data
    rp = _research_path()
    bases = []
    if rp:
        bases.append(rp + "/upload_files")
        bases.append(rp)
    if RESEARCH_EXTRA:
        bases.append(rp + "/" + RESEARCH_EXTRA if rp else RESEARCH_EXTRA)
    for base in bases:
        if not base:
            continue
        for p in (base + "/" + name, base + "/" + name.replace("-", "")):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data is not None:
                    cache[name] = data
                    _log("[FILE] " + name + " <- " + p)
                    return data
            except Exception:
                continue
    cache[name] = None
    return None


def _snap(code):
    try:
        d = get_snapshot(code)
        if d and isinstance(d, dict) and len(d):
            return d
    except Exception:
        pass
    return None


def _f(v, dflt=None):
    try:
        if v is None:
            return dflt
        return float(v)
    except (TypeError, ValueError):
        return dflt


def get_quote(code):
    d = _snap(code)
    if not d:
        return None, None, None, None
    return (_f(d.get("last_px")), _f(d.get("preclose_px")),
            _f(d.get("open_px")), _f(d.get("high_px")))


def get_last(code):
    d = _snap(code)
    return _f(d.get("last_px")) if d else None


def get_prev_close(code):
    d = _snap(code)
    return _f(d.get("preclose_px")) if d else None


def get_turnover(code):
    d = _snap(code)
    return _f(d.get("turnover_ratio")) if d else None


def is_limit_up(code):
    d = _snap(code)
    if not d:
        return False
    up = _f(d.get("up_px"))
    last = _f(d.get("last_px"))
    if not up or up <= 0 or not last:
        return False
    return last >= up - 0.001


def get_day_vwap(code):
    d = _snap(code)
    if not d:
        return None
    vw = _f(d.get("wavg_px"))
    if vw and vw > 0:
        return vw
    return None


def get_active_buy_ratio(code):
    # 1) L2
    try:
        tx = get_individual_transaction([code], data_count=50, is_dict=True)
        if tx and code in tx:
            buy = 0.0
            tot = 0.0
            for r in tx[code]:
                try:
                    amt = float(r.get("business_amount") or 0)
                    if amt <= 0:
                        continue
                    d = str(r.get("business_direction") or "")
                    if d in ("1", "B"):
                        buy += amt
                        tot += amt
                    elif d in ("0", "S"):
                        tot += amt
                except (TypeError, ValueError):
                    continue
            if tot > 0:
                return buy / tot
    except Exception:
        pass
    # 2) snapshot in/out
    d = _snap(code)
    if d:
        inn = _f(d.get("business_amount_in"))
        out = _f(d.get("business_amount_out"))
        if (inn is not None and out is not None and inn + out > 0):
            return out / (inn + out)
    return None


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


def get_daily_bars(code, count=80, field=None):
    try:
        fields = [field] if field else ["open", "high", "low", "close", "amount"]
        df = get_price(code, count=count, frequency="1d", fields=fields, fq="pre")
        if df is None or len(df) == 0:
            return [] if field else {}
        if field:
            return _col(df, field)
        return {f: _col(df, f) for f in fields}
    except Exception:
        return [] if field else {}


def get_m5_bars(code, today_str=None):
    try:
        today = today_str or datetime.now().strftime("%Y-%m-%d")
        df = get_price(code, count=48, frequency="5m",
                       fields=["open", "close", "high", "low", "volume"], fq="pre")
        if df is None or len(df) == 0:
            return []
        opens = _col(df, "open")
        closes = _col(df, "close")
        highs = _col(df, "high")
        lows = _col(df, "low")
        vols = _col(df, "volume")
        n = min(len(opens), len(closes), len(highs), len(lows), len(vols))
        out = []
        idx = df.index
        import re
        for i in range(n):
            t = idx[i]
            ds = None
            tmin = None
            try:
                if hasattr(t, "strftime"):
                    ds = t.strftime("%Y-%m-%d")
                    tmin = int(t.hour) * 60 + int(t.minute)
                else:
                    s = str(t).strip()
                    m = re.match(r"(\d{4})[-/](\d{2})[-/](\d{2})[ T](\d{2}):(\d{2})", s)
                    if m:
                        y, mo, dd, h, mi = m.groups()
                        ds = "%s-%s-%s" % (y, mo, dd)
                        tmin = int(h) * 60 + int(mi)
                    else:
                        m = re.match(r"^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})", s)
                        if m:
                            y, mo, dd, h, mi = m.groups()
                            ds = "%s-%s-%s" % (y, mo, dd)
                            tmin = int(h) * 60 + int(mi)
            except Exception:
                continue
            if ds != today or tmin is None:
                continue
            out.append((tmin, float(opens[i]), float(closes[i]),
                        float(highs[i]), float(lows[i]), float(vols[i])))
        if len(out) < 2:
            return []
        return out
    except Exception:
        return []


def annual_vol(code):
    try:
        arr = get_daily_bars(code, count=22, field="close")
        if len(arr) < 3:
            return None
        lr = []
        for i in range(1, len(arr)):
            a = float(arr[i - 1])
            b = float(arr[i])
            if a > 0 and b > 0:
                lr.append(math.log(b / a))
        if len(lr) < 2:
            return None
        m = sum(lr) / len(lr)
        var = sum((x - m) ** 2 for x in lr) / (len(lr) - 1)
        av = math.sqrt(var) * math.sqrt(252)
        return max(0.10, min(0.80, av))
    except Exception:
        return None


def day_amplitude_pct(code, prev_close):
    d = _snap(code)
    if not d or not prev_close or prev_close <= 0:
        return 0.0
    hi = _f(d.get("high_px"))
    lo = _f(d.get("low_px"))
    if not hi or not lo or hi <= 0 or lo <= 0:
        return 0.0
    return max(0.0, (hi - lo) / prev_close * 100.0)


def portfolio_cash_total(context):
    try:
        p = context.portfolio
        cash = float(p.cash or 0)
        total = float(p.portfolio_value or 0)
        if total <= 0:
            total = cash
        return cash, total
    except Exception:
        return 0.0, 0.0


def get_positions_map():
    out = {}
    try:
        positions = get_positions()
        if not positions:
            return out
        for sid, pos in positions.items():
            amount = int(getattr(pos, "amount", 0) or 0)
            if amount <= 0:
                continue
            enable = int(getattr(pos, "enable_amount", 0) or 0)
            cost = float(getattr(pos, "cost_basis", 0) or 0)
            out[to_ptrade_code(sid)] = {
                "shares": amount,
                "can_use": enable,
                "cost": cost,
                "amount": amount,
                "enable_amount": enable,
            }
    except Exception:
        pass
    return out


def get_today_buy_sids():
    out = set()
    try:
        trades = get_trades()
        if not trades:
            return out
        today = datetime.now().strftime("%Y-%m-%d")
        for t in trades:
            try:
                dt = t.get("created") or t.get("date") or t.get("time") or ""
                if str(dt)[:10] != today:
                    continue
                amt = int(t.get("amount") or 0)
                if amt > 0:
                    out.add(to_ptrade_code(t.get("sid") or t.get("symbol") or ""))
            except (TypeError, ValueError):
                continue
    except Exception:
        pass
    return out


def do_order(code, amount, limit_price=None):
    if not amount:
        return False
    try:
        oid = order(code, int(amount), limit_price=limit_price)
        if oid:
            _log("[ORD] " + code + " amt=" + str(int(amount)) +
                 " lmt=" + (str(round(limit_price, 3)) if limit_price else "mkt") +
                 " -> " + str(oid))
            return True
        _log("[ORD] " + code + " amt=" + str(int(amount)) + " REJECTED (None)")
        return False
    except Exception as e:
        _log("[ORD] " + code + " fail: " + repr(e)[:120])
        return False


def _safe_write(path, obj):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
        return True
    except Exception:
        return False


def _safe_read(path, dflt):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return dflt


def _lock_path():
    rp = _research_path()
    if rp:
        return rp + "/ptrade_tracka_order_locks.json"
    return ""


def order_locked(today, code, reason):
    p = _lock_path()
    if not p:
        return False
    d = _safe_read(p, {})
    return bool(d.get(today, {}).get(code, {}).get(reason, False))


def mark_order_locked(today, code, reason):
    p = _lock_path()
    if not p:
        return
    d = _safe_read(p, {})
    d.setdefault(today, {}).setdefault(code, {})[reason] = time.time()
    for old in [k for k in d if k != today]:
        d.pop(old, None)
    _safe_write(p, d)


def _trade_log_path():
    rp = _research_path()
    if rp:
        return rp + "/ptrade_tracka_trades.json"
    return ""


def _pos_state_path():
    rp = _research_path()
    if rp:
        return rp + "/ptrade_tracka_pos_state.json"
    return ""


def _load_pos_state(memo):
    p = _pos_state_path()
    if p:
        try:
            data = _safe_read(p, {})
            if isinstance(data, dict):
                pos = data.get("positions")
                if isinstance(pos, dict):
                    memo["pos_state"] = pos
                    return pos
        except Exception:
            pass
    memo["pos_state"] = memo.get("pos_state") or {}
    return memo["pos_state"]


def _pos_snapshot(pos):
    out = {}
    for k in POS_STATE_PERSIST:
        if k in pos:
            out[k] = pos[k]
    return out


def _merge_pos_state(pos, saved):
    if not saved or not isinstance(saved, dict):
        return
    if saved.get("buy_date") and not str(pos.get("buy_date") or "").strip():
        pos["buy_date"] = str(saved["buy_date"])
    try:
        sp = float(saved.get("peak") or 0)
        if sp > float(pos.get("peak") or 0):
            pos["peak"] = sp
    except Exception:
        pass
    try:
        pc = int(saved.get("peel_count") or 0)
        if pc > int(pos.get("peel_count") or 0):
            pos["peel_count"] = pc
    except Exception:
        pass
    try:
        ps = float(saved.get("peel_peak_snapshot") or 0)
        if ps > float(pos.get("peel_peak_snapshot") or 0):
            pos["peel_peak_snapshot"] = ps
    except Exception:
        pass
    for bk in ("t2_extended", "vwap_broken", "wy_bc_armed", "trail_armed",
               "awaiting_new_high"):
        if saved.get(bk):
            pos[bk] = True
    try:
        vr = float(saved.get("vwap_ref") or 0)
        if vr > 0:
            pos["vwap_ref"] = vr
    except Exception:
        pass
    try:
        eh = int(saved.get("vwap_early_hits") or 0)
        if eh > int(pos.get("vwap_early_hits") or 0):
            pos["vwap_early_hits"] = eh
    except Exception:
        pass
    try:
        em = int(saved.get("vwap_early_min") or 0)
        if em > 0 and int(pos.get("vwap_early_min") or 0) <= 0:
            pos["vwap_early_min"] = em
    except Exception:
        pass
    try:
        bp = float(saved.get("buy_price") or 0)
        if bp > 0 and float(pos.get("buy_price") or 0) <= 0:
            pos["buy_price"] = bp
    except Exception:
        pass


def _save_pos_state(context):
    try:
        positions = {}
        for code, pos in (getattr(context, "position_map", None) or {}).items():
            if int(pos.get("shares") or 0) <= 0:
                continue
            positions[code] = _pos_snapshot(pos)
        context.memo["pos_state"] = positions
        p = _pos_state_path()
        if p:
            payload = {
                "version": 1,
                "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "positions": positions,
            }
            _safe_write(p, payload)
    except Exception:
        pass


def log_trade(memo, action, code, price, vol, reason):
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
        sig_ts = memo.setdefault("_ledger_sig_ts", {})
        if now - sig_ts.get(sig, 0.0) < LEDGER_DUP_SEC:
            return
        sig_ts[sig] = now
        memo["trade_log"] = memo.get("trade_log", []) + [rec]
        p = _trade_log_path()
        if p:
            _safe_write(p, memo["trade_log"])
    except Exception:
        pass


def is_trading_time(m):
    return (9 * 60 + 30 <= m <= 11 * 60 + 30) or (13 * 60 <= m <= 15 * 60)


def now_min():
    n = datetime.now()
    return n.hour * 60 + n.minute


# =========================================================
# BOARD PERMISSION
# =========================================================
def _board_allowed(code):
    c6 = to_6(code)
    if c6.startswith(("688", "689")):
        return ALLOW_STAR
    if c6.startswith(("300", "301")):
        return ALLOW_CHINEXT
    if c6.startswith(("8", "4", "920")) or c6.startswith("43"):
        return ALLOW_BSE
    return True


# =========================================================
# SCORES / CANDIDATES
# =========================================================
def _filter_st_out(out):
    """ST/退市风险警示硬过滤（2026-08-25 事故：*ST威领被 Track B 买入）。"""
    keep = []
    for it in out:
        nm = str(it.get("name") or "")
        if "ST" in nm.upper() or nm.startswith("退") or "退市" in nm:
            continue
        keep.append(it)
    if len(keep) != len(out):
        _log("[CAND] ST/退市硬过滤剔除 " + str(len(out) - len(keep)))
    return keep


def _load_candidates(context, date_str):
    """Top-10 candidates: {date}.candidates.json ({"candidates": [...]}),
    else {date}.fullpool.json / {date}.json first-10 fallback. None when
    unavailable. Server format (export_qmt_scores.py) is byte-for-byte:
    {"date", "asof", "candidates": [{"symbol", "name", "score", "rank"}...]}."""
    cache = context.scores_cache if hasattr(context, "scores_cache") else {}
    d = load_score_file(date_str + ".candidates.json", cache)
    if isinstance(d, dict):
        rows = d.get("candidates") or d.get("rows")
        if isinstance(rows, list) and rows:
            out = []
            for i, it in enumerate(rows):
                out.append({
                    "symbol": to_ptrade_code(it.get("symbol")),
                    "name": it.get("name") or it.get("symbol") or "",
                    "score": it.get("score_0500") or it.get("score") or 0,
                    "rank": it.get("rank") or (i + 1),
                })
            return _filter_st_out(out)
    # fullpool / json fallback (first 10 by rank)
    for name in (date_str + ".fullpool.json", date_str + ".json"):
        d2 = load_score_file(name, cache)
        if isinstance(d2, dict):
            recs = d2.get("rows") or d2.get("recommendations")
            if isinstance(recs, list) and recs:
                out = []
                for i, it in enumerate(recs[:10]):
                    sym = it.get("symbol") if isinstance(it, dict) else it
                    out.append({
                        "symbol": to_ptrade_code(sym),
                        "name": it.get("name", sym) if isinstance(it, dict) else sym,
                        "score": it.get("score_0500", it.get("score", 0))
                        if isinstance(it, dict) else 0,
                        "rank": it.get("rank") if isinstance(it, dict) and it.get("rank") else (i + 1),
                    })
                return _filter_st_out(out)
    return None


# =========================================================
# POSITION SYNC
# =========================================================
def _recover_buy_date(memo, code):
    """Restore buy_date from persisted pos state, then local trade log."""
    sym = to_ptrade_code(code)
    try:
        saved = (memo.get("pos_state") or {}).get(sym)
        if not saved:
            saved = _load_pos_state(memo).get(sym)
        bd = str((saved or {}).get("buy_date") or "").strip()
        if bd:
            if len(bd) >= 10 and "-" in bd[:10]:
                return bd[:10].replace("-", "")
            return bd
    except Exception:
        pass
    try:
        for t in reversed(memo.get("trade_log") or []):
            if t.get("action") != "BUY":
                continue
            if to_ptrade_code(t.get("symbol")) != sym:
                continue
            ts = str(t.get("time") or "")
            if len(ts) >= 10:
                return ts[:10].replace("-", "")
    except Exception:
        pass
    return ""


def _sync_holdings(context, today):
    try:
        live = get_positions_map()
        today_buys = get_today_buy_sids()
        pm = context.position_map
        for code, info in live.items():
            vol = info["shares"]
            cost = info["cost"]
            can_use = info["can_use"]
            # v1.1 (2026-08-20): same defect as QMT -- once T+1 unlocks
            # (can_use == vol) the old inference stops firing and buy_date would
            # fall empty, making _hold_days return 999 and force-selling a T+1
            # winner at 14:45 (000651 08-20: +1.5%, t2_force_after_extend).
            # Recover the true buy date from the local trade log first.
            bd = today if code in today_buys else ""
            if not bd:
                bd = _recover_buy_date(context.memo, code)
            if not bd and can_use < vol:
                bd = today
            saved = (context.memo.get("pos_state") or {}).get(code)
            if code not in pm:
                pm[code] = {
                    "shares": vol,
                    "can_use": can_use,
                    "buy_price": cost if cost > 0 else 0,
                    "name": code,
                    "buy_date": bd,
                    "peak": cost if cost > 0 else 0,
                    "trail_armed": False,
                    "awaiting_new_high": False,
                    "peel_peak_snapshot": cost if cost > 0 else 0,
                    "peel_count": 0,
                    "t2_extended": False,
                    "vwap_broken": False,
                    "wy_bc_armed": False,
                    "pending": False,
                    "today_high": cost if cost > 0 else 0,
                }
                _merge_pos_state(pm[code], saved)
                if not pm[code].get("buy_date"):
                    pm[code]["buy_date"] = _recover_buy_date(context.memo, code)
                _log("[SYNC] +" + code + " " + str(vol) + "sh cost=" +
                     str(round(cost, 3)) + " bd=" + str(pm[code].get("buy_date") or bd) +
                     " can_use=" + str(can_use) +
                     (" [state]" if saved else ""))
            else:
                p = pm[code]
                p["shares"] = vol
                p["can_use"] = can_use
                if cost > 0:
                    p["buy_price"] = cost
                p["pending"] = False
                if not p.get("buy_date") and bd:
                    p["buy_date"] = bd
                _merge_pos_state(p, saved)
                if not p.get("buy_date"):
                    p["buy_date"] = _recover_buy_date(context.memo, code)
        for code in list(pm.keys()):
            if code not in live:
                if order_locked(today, code, "BUY"):
                    pm[code]["pending"] = True
                    continue
                _log("[SYNC] -" + code + " closed")
                pm.pop(code, None)
        _save_pos_state(context)
    except Exception as e:
        _log("[SYNC] err: " + repr(e)[:80])


# =========================================================
# QUOTE / INDICATOR HELPERS (adapted)
# =========================================================
def _get_quote(code):
    return get_quote(code)


def _get_last(code):
    return get_last(code)


def _get_prev_close(code):
    return get_prev_close(code)


def _get_turnover(code):
    return get_turnover(code)


def _is_limit_up(code):
    return is_limit_up(code)


def _day_vwap(code):
    """Day VWAP from Ptrade snapshot wavg_px (no hand/share unit issue: the
    snapshot reports CNY/share directly)."""
    vw = get_day_vwap(code)
    if vw and vw > 0:
        return vw
    return None


def _get_active_buy_ratio(code):
    return get_active_buy_ratio(code)


def _annual_vol(code):
    return annual_vol(code)


def _adaptive_params(code):
    vol = _annual_vol(code)
    if vol is None:
        return DEF_HARD_STOP, DEF_TRAIL_ARM, DEF_PEEL_PB
    dev = vol - VOL_BASELINE
    hs = round(DEF_HARD_STOP - dev * 0.10, 3)
    ta = round(max(0.01, DEF_TRAIL_ARM - dev * 0.05), 3)
    pb = round(min(0.05, DEF_PEEL_PB + dev * 0.03), 3)
    return hs, ta, pb


def _day_amplitude_pct(code):
    _, prev, _, _ = _get_quote(code)
    return day_amplitude_pct(code, prev)


def _t2_force_floor(code):
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


# =========================================================
# WYCKOFF DISTRIBUTION (v2.10) -- pure logic, data via get_price
# =========================================================
def _wyckoff_distribution(code):
    try:
        dd = get_daily_bars(code, count=80)
        if not dd:
            return False
        op = dd.get("open", [])
        hi = dd.get("high", [])
        lo = dd.get("low", [])
        cl = dd.get("close", [])
        vo = dd.get("amount", [])
        n = min(len(op), len(hi), len(lo), len(cl), len(vo))
        if n < 62:
            return False
        hi = hi[:n - 1]
        lo = lo[:n - 1]
        cl = cl[:n - 1]
        op = op[:n - 1]
        vo = vo[:n - 1]
        m = len(hi)
        if m < 62:
            return False
        hi60 = float(max(hi[:m - 10])) if m - 10 > 0 else 0.0
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
    except Exception:
        return False


def _wyckoff_holding_bc(code, peak):
    if peak <= 0:
        return False
    try:
        vols = get_daily_bars(code, count=22, field="volume")
        if len(vols) < 6:
            return False
        vols = vols[:-1]
        if len(vols) < 5:
            return False
        vma20 = float(sum(vols[-20:]) / min(20, len(vols)))
        if vma20 <= 0:
            return False
    except Exception:
        return False
    bars = get_m5_bars(code)
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


# =========================================================
# P2 DYNAMIC CONFIRM ENTRY (v2.0)
# =========================================================
def _vol_ma5(vols, i):
    s = vols[max(0, i - 4):i + 1]
    return sum(s) / len(s) if s else 0.0


def _p2_max_gap(code):
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
    price, prev, open_, high = _get_quote(code)
    last = _get_last(code) or price
    if not price or price <= 0:
        return None, "no_quote"
    pc = _get_prev_close(code)
    if pc:
        prev = pc
    if not prev or prev <= 0:
        return None, "no_quote"
    if now_min > CONF_END_MIN:
        return None, "no_confirm_eod"
    if now_min < CONF_START_MIN:
        return None, "wait_confirm"
    _to = _get_turnover(code)
    if _to is not None and _to > CONF_MAX_TURNOVER:
        return None, "skip_high_turnover"
    bars = get_m5_bars(code)
    if not bars:
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
        if USE_ABR_GATE and now_min >= ABR_GATE_START_MIN:
            abr = _get_active_buy_ratio(code)
            if abr is not None and abr < MIN_ACTIVE_BUY:
                return None, "skip_low_abr"
        return round(trig_px, 2), "dyn_confirm"
    if now_min >= CONF_END_MIN:
        return None, "no_confirm_eod"
    return None, "wait_confirm"


# =========================================================
# SELL (adaptive exit, same as v1.0)
# =========================================================
def _hold_days(pos, today):
    """Trading days from buy_date -> today (buy day excluded). buy_date %Y%m%d
    or 'YYYY-MM-DD'. 999 on missing/unparseable. v1.4: weekends + 2026 A-share
    closures excluded (see _trading_days_between), so Friday buy = T+1 on Monday."""
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
    except Exception:
        return 999


def _closed_5m_bars(now_min):
    if now_min <= 9 * 60 + 30:
        return 0
    if now_min <= 11 * 60 + 30:
        return (now_min - (9 * 60 + 35)) // 5 + 1
    if now_min < 13 * 60 + 5:
        return 24
    if now_min <= 15 * 60:
        return 24 + (now_min - (13 * 60 + 5)) // 5 + 1
    return 48


def _volume_ratio_of(code):
    """Volume ratio = today cum vol / prior 5d same-time cum vol mean (aligned
    with Track B v1.1 same-time window). None on fail (momentum guard soft)."""
    nm = now_min()
    today = datetime.now().strftime("%Y%m%d")
    try:
        k = _closed_5m_bars(nm)
        if k <= 0:
            return None
        # get_price 5m returns up to count bars; use enough lookback for 5 days
        df = get_price(code, count=6 * 48, frequency="5m",
                       fields=["volume"], fq="pre")
        if df is None or len(df) == 0:
            return None
        vols = _col(df, "volume")
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
    except Exception:
        return None



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


def _check_sell(context, now, now_min, today):
    pm = context.position_map
    for code, pos in list(pm.items()):
        if pos.get("pending"):
            continue
        price, prev, open_, high = _get_quote(code)
        if price is None or price <= 0 or pos.get("buy_price", 0) <= 0:
            continue
        pc = _get_prev_close(code)
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
            _log("[WARN] " + code + " daily=" + str(round(daily, 1)) +
                 "% anomaly, hold")
            continue
        if daily <= LIMIT_DOWN_PCT:
            _do_sell(context, code, pos, price,
                     "limit_down daily=" + str(round(daily, 1)) + "%")
            continue

        bd = pos.get("buy_date", "")
        is_today_buy = (bd == today)
        if is_today_buy:
            continue

        # Wyckoff buy-climax early exit (v2.10)
        if (not pos.get("wy_bc_armed") and now_min >= VWAP_CONFIRM_MIN and
                _wyckoff_holding_bc(code, pos.get("peak", cost))):
            pos["wy_bc_armed"] = True
            _log("[BC] " + code + " holding buy-climax px=" +
                 str(round(price, 2)) + " peak=" + str(round(pos.get("peak", 0), 2)))
        if pos.get("wy_bc_armed") and VWAP_SELL_START <= now_min <= VWAP_SELL_END:
            _do_sell(context, code, pos, price, "wyckoff_bc " +
                     str(round(ret, 1)) + "%")
            continue

        # VWAP weak-early exit (v2.3; +next-morning confirm v1.3)
        if not pos.get("vwap_broken") and now_min >= VWAP_CONFIRM_MIN:
            vw = _day_vwap(code)
            if vw and vw > 0 and price < vw:
                pos["vwap_broken"] = True
                pos["vwap_ref"] = vw
                _log("[VWAP] " + code + " day-vwap broken px=" +
                     str(round(price, 2)) + " vwap=" + str(round(vw, 2)) +
                     " ret=" + str(round(ret, 1)) + "%")
        # v1.3: next-morning confirm. Unconditional next-open sell sold the
        # day's low on all 3 real triggers (QMT sim 08-31). Sell only if the
        # live price is still below the recorded reference; recover -> cancel.
        if pos.get("vwap_broken") and VWAP_SELL_START <= now_min <= VWAP_SELL_END:
            vref = float(pos.get("vwap_ref") or 0)
            decision = _vwap_morning_decide(pos, price, now_min)
            if decision == "recover":
                _log("[VWAP] " + code + " recovered px=" +
                     str(round(price, 2)) + " ref=" + str(round(vref, 2)) +
                     " cancel weak-early")
            elif decision == "wait1":
                _log("[VWAP] " + code + " first confirm wait 2nd px=" +
                     str(round(price, 2)) + " ref=" + str(round(vref, 2)))
            elif decision == "sell":
                _do_sell(context, code, pos, price, "vwap_weak_early " +
                         str(round(ret, 1)) + "%")
                continue

        hs, ta, pb = _adaptive_params(code)

        # hard stop: close-confirm window only
        if now_min >= T2_FORCE_HHMM and ret <= hs * 100:
            _do_sell(context, code, pos, price,
                     "hard_stop " + str(round(ret, 1)) + "% vs " +
                     str(round(hs * 100, 1)) + "%")
            continue

        # T+2 conditional force-close (v2.17)
        if now_min >= T2_FORCE_HHMM:
            hold_days = _hold_days(pos, today)
            if pos.get("t2_extended"):
                # v1.1 (2026-08-20): hold_days == 999 (buy_date unknown) must not
                # be read as past maturity and force-sell a fresh winner.
                if hold_days != 999 and hold_days >= T2_EXTEND_MAX_DAYS:
                    _do_sell(context, code, pos, price,
                             "t2_force_after_extend " + str(round(ret, 1)) + "%")
                    continue
            else:
                force_floor = _t2_force_floor(code) * 100
                if ret < force_floor:
                    _do_sell(context, code, pos, price,
                             "t2_force " + str(round(ret, 1)) + "% floor=" +
                             str(round(force_floor, 1)) + "%")
                    continue
                if ((hold_days != 999 and hold_days >= T2_EXTEND_MAX_DAYS)
                        or ret <= hs * 100):
                    _do_sell(context, code, pos, price,
                             "t2_force_after_extend " + str(round(ret, 1)) + "%")
                    continue
                pos["t2_extended"] = True
                _log("[EXT] " + code + " extend px=" + str(round(price, 2)) +
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
                    _do_sell(context, code, pos, price,
                             "peel_clear pk=" + str(round(peak, 2)) +
                             " pb=" + str(round(pbk, 1)) + "%")
                    continue
                _do_sell_half(context, code, pos, price,
                              "peel_half" + str(n + 1) +
                              " pk=" + str(round(peak, 2)) +
                              " pb=" + str(round(pbk, 1)) + "%")
                pos["peel_count"] = n + 1
                pos["awaiting_new_high"] = True
                pos["peel_peak_snapshot"] = peak

        if (pos.get("awaiting_new_high") and
                pos.get("peak", 0) > pos.get("peel_peak_snapshot", 0) + 1e-9):
            pos["awaiting_new_high"] = False
    _save_pos_state(context)


# =========================================================
# ROTATION (v2.16)
# =========================================================
def _weakness_score(context, today):
    pm = context.position_map
    cands = []
    for c, p in list(pm.items()):
        if p.get("pending"):
            continue
        if _hold_days(p, today) < ROTATION_MIN_HOLD_DAYS:
            continue
        pq, pp, po, ph = _get_quote(c)
        if pq is None or pq <= 0 or p.get("buy_price", 0) <= 0:
            continue
        pc2 = _get_prev_close(c)
        pret = (pq / p["buy_price"] - 1) * 100
        pday = (pq / pc2 - 1) * 100 if pc2 and pc2 > 0 else 0.0
        vw = _day_vwap(c)
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
    for it in cands:
        vr = _volume_ratio_of(it["code"])
        if (it["day"] > ROTATION_MOMENTUM_DROP_PCT and
                (vr or 0) > ROTATION_MOMENTUM_VOL_RATIO):
            it["skip"] = True

    def _rank01(vals, invert=False):
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


def _rotation_sell(context, now, now_min, today, need_n):
    if not ROTATION_ENABLE:
        return []
    if order_locked(today, "__ROT__", "rot"):
        _log("[ROT] daily cap " + str(ROTATION_DAILY_MAX) + " reached, skip")
        return []
    cands, sellable = _weakness_score(context, today)
    if not sellable:
        _log("[ROT] no sellable holdings (min_hold=" +
             str(ROTATION_MIN_HOLD_DAYS) + ")")
        return []
    w = sellable[0]
    if (ROTATION_WEAK_GATE and not
            (w["day"] < 0 or w["vwap_break"] == 1.0
             or w["early"] == 1.0 or w["ret"] < 0)):
        _log("[ROT] skip: weakest " + w["code"] +
             " still healthy (no weakness signal), no churn")
        return []
    sold = []
    for it in sellable[:need_n]:
        code = it["code"]
        pm = context.position_map
        if code in pm and not pm[code].get("pending"):
            price, prev, open_, high = _get_quote(code)
            pos = pm[code]
            ret = (price / pos["buy_price"] - 1) * 100 if price else 0
            if (ret > 0 and (pos.get("peel_count") or 0) < PEEL_MAX_STEPS
                    and pos["shares"] >= 400):
                _do_sell_half(context, code, pos, price,
                              "rotation_peel ret=" + str(round(ret, 1)) + "%")
            else:
                _do_sell(context, code, pos, price,
                         "rotation_sell ret=" + str(round(ret, 1)) + "%")
            sold.append(code)
            mark_order_locked(today, "__ROT__", "rot")
            _log("[ROT] sell " + code + " weakness=" +
                 str(round(it.get("score", 0), 2)))
    return sold


def _sell_lock_key(reason):
    if not reason:
        return "SELL"
    tok = str(reason).split(" ")[0]
    if tok.startswith("t2_force"):
        return "t2_force"
    return tok


def _do_sell(context, code, pos, price, reason):
    vol = pos.get("shares", 0)
    can_use = pos.get("can_use", vol)
    if can_use < vol:
        _log("[SELL] " + code + " cap " + str(vol) + " -> " + str(can_use) +
             " (can_use, T+1)")
        vol = can_use
    if vol <= 0 or vol > 999999:
        return
    today = datetime.now().strftime("%Y%m%d")
    lockk = _sell_lock_key(reason)
    if order_locked(today, code, lockk):
        _log("[LOCK] skip sell " + code + " " + lockk +
             " (already ordered today)")
        return
    _log("[SELL] " + code + " " + reason + " all " + str(vol) +
         "sh @ " + str(round(price, 2)))
    if not do_order(code, -vol):
        _log("[SELL] " + code + " " + reason + " all " + str(vol) +
             "sh order REJECTED (no lock, retry)")
        return
    mark_order_locked(today, code, lockk)
    log_trade(context.memo, "SELL", code, price, vol, reason)
    context.position_map.pop(code, None)
    _save_pos_state(context)


def _do_sell_half(context, code, pos, price, reason):
    shares = pos.get("shares", 0)
    can_use = pos.get("can_use", shares)
    if can_use < shares:
        _log("[SELL] " + code + " cap " + str(shares) + " -> " + str(can_use) +
             " (can_use, T+1)")
        shares = can_use
    if shares <= 0:
        _log("[SELL] " + code + " skip " + reason + " no tradable shares (T+1)")
        return
    half = max(100, (shares // 2 // 100) * 100)
    if half <= 0 or half >= shares:
        _do_sell(context, code, pos, price, reason + " (half>=all)")
        return
    today = datetime.now().strftime("%Y%m%d")
    lockk = _sell_lock_key(reason)
    if order_locked(today, code, lockk):
        _log("[LOCK] skip sell-half " + code + " " + lockk +
             " (already ordered today)")
        return
    _log("[SELL] " + code + " " + reason + " half " + str(half) +
         "sh @ " + str(round(price, 2)))
    if not do_order(code, -half):
        _log("[SELL] " + code + " " + reason + " half " + str(half) +
             "sh order REJECTED (no lock, retry)")
        return
    mark_order_locked(today, code, lockk)
    pos["shares"] = shares - half
    pos["can_use"] = max(0, can_use - half)
    log_trade(context.memo, "SELL_HALF", code, price, half, reason)
    _save_pos_state(context)


# =========================================================
# BUY (P2 first-come, v2.0)
# =========================================================
def _item_fund_hard_fail(item):
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


def _check_buy(context, now, now_min, today, cands):
    n_all = len(cands or [])
    cands = _filter_cands_by_max_rank(cands)
    if n_all and context.run_count % 60 == 1:
        _log("[RANK] max=" + str(MAX_CAND_RANK) + " keep=" + str(len(cands)) + "/" + str(n_all))
    pm = context.position_map
    if len(pm) >= MAX_HOLDINGS:
        worth_buy = False
        for item in cands:
            code = to_ptrade_code(item.get("symbol"))
            if code in pm or code in context.sent_today:
                continue
            if order_locked(today, code, "BUY"):
                continue
            fill, reason = _p2_decide(code, now_min)
            if fill is not None:
                worth_buy = True
                break
        if not worth_buy:
            _log("[BUY] skip: holdings full & no P2-confirmed candidate")
            return
        sold = _rotation_sell(context, now, now_min, today, ROTATION_SELL_N)
        if not sold:
            _log("[BUY] skip: holdings full & rotation sold nothing")
            return

    cash, total_asset = portfolio_cash_total(context)
    if cash <= 0:
        if context.run_count % 60 == 0:
            _log("[CASH] cash=" + str(cash))
        return
    if total_asset <= 0:
        total_asset = cash

    today_bought = 0
    for k, v in (_load_order_locks_ctx(context).get(today, {})).items():
        if "BUY" in v:
            today_bought += 1

    if today_bought >= MAX_DAILY_BUY:
        _log("[BUY] today_bought=" + str(today_bought) +
             " >= MAX_DAILY_BUY=" + str(MAX_DAILY_BUY) + " skip all")
        return

    for item in cands:
        code = to_ptrade_code(item.get("symbol"))
        rank = int(item.get("rank") or 0)
        if code in pm:
            continue
        if code in context.sent_today:
            continue
        if len(pm) >= MAX_HOLDINGS:
            break
        if today_bought >= MAX_DAILY_BUY:
            break
        if order_locked(today, code, "BUY"):
            _log("[LOCK] " + code + " BUY skip (already ordered today)")
            continue

        if not _board_allowed(code):
            _log("[SKIP] " + code + " board not allowed rank=" + str(rank))
            context.sent_today.add(code)
            continue

        if _item_fund_hard_fail(item):
            _log("[FUND] " + code + " fund_hard_fail skip rank=" + str(rank))
            context.sent_today.add(code)
            continue

        if _is_limit_up(code):
            _log("[WAIT] " + code + " limit-up rank=" + str(rank) +
                 " skip for today")
            context.sent_today.add(code)
            continue

        if _wyckoff_distribution(code):
            _log("[WYCKOFF] " + code + " distribution (bc/ut) rank=" +
                 str(rank) + " skip for today")
            context.sent_today.add(code)
            continue

        fill, reason = _p2_decide(code, now_min)
        if fill is None:
            if reason in ("no_confirm_eod", "skip_high_turnover", "skip_low_abr"):
                _log("[WAIT] " + code + " P2=" + reason +
                     " rank=" + str(rank) + " abandon for today")
                context.sent_today.add(code)
            else:
                _log("[WAIT] " + code + " P2=" + reason +
                     " rank=" + str(rank) + " retry next period")
            continue

        # v2.17 slip guard
        try:
            _live = _get_last(code)
            if _live and _live > fill * (1 + MAX_BUY_SLIP_PCT):
                _log("[BUY] " + code + " slip guard: live " +
                     str(round(_live, 2)) + " > trig " + str(round(fill, 2)) +
                     " +" + str(round((_live / fill - 1) * 100, 1)) +
                     "% hold off")
                continue
        except Exception:
            pass

        shares = int(total_asset * POSITION_PCT / fill / 100) * 100
        if shares < 100:
            _log("[SKIP] " + code + " insufficient cash")
            continue
        max_cash_shares = int(cash / fill / 100) * 100
        if max_cash_shares < 100:
            _log("[SKIP] " + code + " insufficient cash")
            continue
        shares = min(shares, max_cash_shares)
        if not do_order(code, shares):
            _log("[BUY] " + code + " x" + str(shares) +
                 " order REJECTED (no lock written) rank=" + str(rank))
            context.sent_today.add(code)
            continue
        context.sent_today.add(code)
        mark_order_locked(today, code, "BUY")
        pm[code] = {
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
        }
        today_bought += 1
        _log("[BUY] " + code + " x" + str(shares) + " @ " +
             str(round(fill, 2)) + " P2=dyn_confirm rank=" + str(rank))
        log_trade(context.memo, "BUY", code, fill, shares, "p2_dyn_confirm")
        _save_pos_state(context)


def _load_order_locks_ctx(context):
    p = _lock_path()
    if not p:
        return {}
    return _safe_read(p, {})


# =========================================================
# PTRADE ENTRY POINTS
# =========================================================
def initialize(context):
    context.scores_cache = {}
    context.current_date = ""
    context.position_map = {}
    context.sent_today = set()
    context._last_resync = 0
    context.run_count = 0
    context.memo = {}
    try:
        context.memo["trade_log"] = _safe_read(_trade_log_path(), [])
        if not isinstance(context.memo["trade_log"], list):
            context.memo["trade_log"] = []
    except Exception:
        context.memo["trade_log"] = []
    _load_pos_state(context.memo)
    context._snap_day = ""
    today = datetime.now().strftime("%Y%m%d")
    _sync_holdings(context, today)
    try:
        set_universe(list(context.position_map.keys()) or ["600519.SS"])
    except Exception:
        pass
    _log("[INIT] track-A ptrade v1.7 (P2 + rank<=2, vwap 2nd) sim | " +
         "holdings=" + str(len(context.position_map)) +
         " | pos_state=" + str(len(context.memo.get("pos_state") or {})) +
         " | remote=" + REMOTE_SCORE_BASE)
    _log("[INIT] L2 available: " +
         str(_probe_l2()))


def _probe_l2():
    try:
        get_individual_transaction(["600519.SS"], data_count=1, is_dict=True)
        return True
    except Exception:
        return False


def before_trading_start(context, data):
    today = datetime.now().strftime("%Y%m%d")
    _sync_holdings(context, today)


def handle_data(context, data):
    context.run_count += 1
    now = datetime.now()
    now_min = now.hour * 60 + now.minute
    today = now.strftime("%Y%m%d")

    if today != context.current_date:
        context.current_date = today
        context.sent_today = set()
        context.scores_cache.pop(today, None)
        context.scores_cache.pop(today + ".candidates.json", None)
        context.scores_cache.pop(today + ".json", None)

    ts = time.time()
    if ts - getattr(context, "_last_resync", 0) >= RESYNC_SEC:
        context._last_resync = ts
        _sync_holdings(context, today)

    cands = _load_candidates(context, today)
    if cands is None:
        return

    if not is_trading_time(now_min):
        return

    try:
        _check_sell(context, now, now_min, today)
    except Exception as e:
        _log("[SELL-ERR] " + repr(e)[:120])

    try:
        _check_buy(context, now, now_min, today, cands)
    except Exception as e:
        _log("[BUY-ERR] " + repr(e)[:120])

    if now_min >= LEDGER_SNAP_MIN and getattr(context, "_snap_day", "") != today:
        context._snap_day = today
        _snap_daily(context, today, now)


def _snap_daily(context, today, now):
    try:
        pos_list = []
        for code, pos in context.position_map.items():
            shares = int(pos.get("shares") or 0)
            cost = float(pos.get("buy_price") or pos.get("cost") or 0)
            if shares <= 0:
                continue
            px = cost
            q = _get_quote(code)
            if q and q[0]:
                px = float(q[0] or cost)
            pl = (px - cost) * shares
            pct = (px / cost - 1) * 100 if cost > 0 else 0.0
            pos_list.append({
                "code": code, "shares": shares, "cost": round(cost, 3),
                "price": round(px, 3), "pl": round(pl, 2),
                "pl_pct": round(pct, 2),
            })
        realized = 0.0
        for tr in context.memo.get("trade_log", []):
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
        _log("[LEDGER] snapshot " + today + " pos=" + str(len(pos_list)) +
             " unreal=" + str(day["unrealized_pl"]))
    except Exception:
        pass
