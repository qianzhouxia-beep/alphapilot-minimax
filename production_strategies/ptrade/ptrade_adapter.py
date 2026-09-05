# -*- coding: utf-8 -*-
"""AlphaPilot -- Ptrade adapter layer (QMT -> Ptrade migration).

Ptrade (Hundsun) runs strategies on the broker's cloud VM. The strategy must
be a SINGLE self-contained .py file (transaction module).  This module is the
canonical source of the helper functions that every migrated strategy inlines
(see the "COPY INTO STRATEGY" header comment inside each helper).

Differences handled here (vs the QMT/TDX codebase):
  1. Code format      : QMT uses 600519.SH / 000001.SZ / 830799.BJ.
                        Ptrade uses 600519.SS / 000001.SZ / 830799.BJ (SS, not SH).
  2. Data delivery    : Ptrade cloud cannot read the local PC or reach the
                        AlphaPilot server nginx by default. Two channels:
                          A. direct HTTP (needs broker firewall whitelist for
                             the server IP/domain -- ask the account manager),
                          B. upload_files (Ptrade client "scheduled upload",
                             read via get_research_path()).
                        load_score_file() tries HTTP first, then the uploaded
                        copy, then a local cache dir (research module).
  3. Quotes           : get_snapshot() replaces get_market_data_ex/get_full_tick.
                        It returns turnover_ratio / vol_ratio / wavg_px (day
                        VWAP) / up_px / down_px / business_amount_in|out
                        (inner/outer volume -> active-buy ratio approximation).
  4. ABR gate         : L2 (get_individual_transaction) if the account has it,
                        else inner/outer volume from snapshot as a drop-in
                        approximation, else None -> soft-pass (same semantics
                        as the QMT mootdx-feed soft gate).
  5. Orders           : order(security, amount) replaces passorder. A rejected
                        order returns None (QMT returned a non-zero ret code).
  6. Account/positions: context.portfolio (cash / portfolio_value) and
                        get_positions() replace get_trade_detail_data.
  7. Ledger / locks   : written to the research path when writable, else kept
                        in-memory only (g-object). Ptrade may deny filesystem
                        writes in the strategy sandbox.

Pure ASCII.  No f-strings (legacy Ptrade VMs run Py3.5+; keep it portable).
"""

import json
import time
from datetime import datetime, date

try:
    import urllib.request as _urlreq
except Exception:                     # research/backtest may not have it
    _urlreq = None


# =====================================================================
# LOGGING
# =====================================================================
def _log(msg):
    """Ptrade print() output is shown in the strategy run log; log.info()
    may be unavailable in backtest on some broker builds, so try both."""
    try:
        print(msg)
    except Exception:
        pass


# =====================================================================
# CODE FORMAT CONVERSION
# =====================================================================
def to_ptrade_code(code):
    """Convert any input to Ptrade code format: 600519.SS / 000001.SZ / 830799.BJ.
    Accepts bare '600519', QMT '600519.SH', lower-case 'sh600519', etc."""
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
    """Bare 6-digit code without suffix (for dict keys / matching)."""
    s = str(code or "").strip().upper()
    return "".join(ch for ch in s if ch.isdigit())[-6:]


# =====================================================================
# DATA FILE DELIVERY (dual channel)
# =====================================================================
# Ptrade cloud cannot reach the AlphaPilot server nginx by default. The
# strategy tries, in order:
#   1. HTTP GET {REMOTE_SCORE_BASE}/{name}          (whitelist required)
#   2. {get_research_path()}/upload_files/{name}     (client scheduled upload)
#   3. {get_research_path()}/{name}                  (research module, manual)
# The FIRST hit that parses as JSON wins. The result is cached per (name).
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


def load_score_file(name, remote_base, cache=None, allow_http=True):
    """Load a JSON score file by name (e.g. '20260819.candidates.json').
    Returns parsed dict/list, or None. `cache` is a dict used to memoize
    (per strategy run). HTTP attempts are silent + throttled by the caller."""
    if cache is not None and name in cache:
        return cache[name]
    data = None
    # 1) HTTP direct
    if allow_http and remote_base:
        body = _http_get(remote_base.rstrip("/") + "/" + name)
        if body:
            try:
                data = json.loads(body.decode("utf-8", "replace"))
            except Exception:
                data = None
            if data is not None:
                if cache is not None:
                    cache[name] = data
                _log("[FILE] " + name + " <- HTTP ok")
                return data
    # 2) upload_files + research root
    rp = _research_path()
    for base in (rp + "/upload_files", rp):
        if not base:
            continue
        for p in (base + "/" + name, base + "/" + name.replace("-", "")):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data is not None:
                    if cache is not None:
                        cache[name] = data
                    _log("[FILE] " + name + " <- " + p)
                    return data
            except Exception:
                continue
    if cache is not None:
        cache[name] = None          # negative cache: don't hammer every bar
    return None


# =====================================================================
# QUOTE / SNAPSHOT
# =====================================================================
def _snap(code):
    """Real-time snapshot dict via Ptrade get_snapshot. None on failure."""
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
    """Return (last, prev_close, open, high) from snapshot. All float or None."""
    d = _snap(code)
    if not d:
        return None, None, None, None
    last = _f(d.get("last_px"))
    prev = _f(d.get("preclose_px"))
    opn = _f(d.get("open_px"))
    hi = _f(d.get("high_px"))
    return last, prev, opn, hi


def get_last(code):
    d = _snap(code)
    return _f(d.get("last_px")) if d else None


def get_prev_close(code):
    d = _snap(code)
    return _f(d.get("preclose_px")) if d else None


def get_turnover(code):
    """Daily turnover % straight from the snapshot."""
    d = _snap(code)
    return _f(d.get("turnover_ratio")) if d else None


def is_limit_up(code):
    """True when current price is sealed at limit-up (>= up_px - tick)."""
    d = _snap(code)
    if not d:
        return False
    up = _f(d.get("up_px"))
    last = _f(d.get("last_px"))
    if not up or up <= 0 or not last:
        return False
    return last >= up - 0.001


def get_day_vwap(code):
    """Day VWAP from snapshot wavg_px (weighted average price). None on fail."""
    d = _snap(code)
    if not d:
        return None
    vw = _f(d.get("wavg_px"))
    if vw and vw > 0:
        return vw
    return None


def get_active_buy_ratio(code):
    """Active-buy ratio.

    Priority:
      1. L2 get_individual_transaction (if the account has L2 permission):
         business_direction 1 = active buy. Roll over recent records.
      2. Snapshot inner/outer volume: business_amount_out / (in+out).
      3. None -> soft-pass (same as the QMT mootdx-feed missing-data pass).
    """
    try:
        tx = get_individual_transaction([code], data_count=50, is_dict=True)
        if tx and code in tx:
            rows = tx[code]
            buy = 0.0
            tot = 0.0
            for r in rows:
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
    d = _snap(code)
    if d:
        inn = _f(d.get("business_amount_in"))
        out = _f(d.get("business_amount_out"))
        if (inn is not None and out is not None and inn + out > 0):
            return out / (inn + out)
    return None


# =====================================================================
# KLINE (historical / intraday)
# =====================================================================
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
    """Daily bars via get_price. Returns list of floats for `field`, or a dict
    {field: [..]} when field is None. [] on failure."""
    try:
        fields = [field] if field else ["open", "high", "low", "close", "amount"]
        df = get_price(code, count=count, frequency="1d", fields=fields,
                       fq="pre")
        if df is None or len(df) == 0:
            return [] if field else {}
        if field:
            return _col(df, field)
        return {f: _col(df, f) for f in fields}
    except Exception:
        return [] if field else {}


def get_m5_bars(code, today_str=None):
    """Today's 5m bars from get_price. Returns [(tmin, open, close, high, low,
    vol), ...] with tmin = minutes since midnight (09:35 -> 575), only today's
    bars. [] on failure. get_price '5m' index carries real datetimes."""
    try:
        today = today_str or datetime.now().strftime("%Y-%m-%d")
        df = get_price(code, count=48, frequency="5m",
                       fields=["open", "close", "high", "low", "volume"],
                       fq="pre")
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
                    # '2026-08-19 09:35:00' or '20260819093500' or '20260819'
                    import re
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
                        else:
                            m = re.match(r"^(\d{4})(\d{2})(\d{2})$", s)
                            if m:
                                y, mo, dd = m.groups()
                                ds = "%s-%s-%s" % (y, mo, dd)
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
    """20-day annualized volatility (0.10 ~ 0.80), pure python."""
    try:
        arr = get_daily_bars(code, count=22, field="close")
        if len(arr) < 3:
            return None
        import math
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
    """Today's intraday amplitude (high-low)/prev*100 from the snapshot."""
    d = _snap(code)
    if not d or not prev_close or prev_close <= 0:
        return 0.0
    hi = _f(d.get("high_px"))
    lo = _f(d.get("low_px"))
    if not hi or not lo or hi <= 0 or lo <= 0:
        return 0.0
    return max(0.0, (hi - lo) / prev_close * 100.0)


# =====================================================================
# ACCOUNT / POSITIONS
# =====================================================================
def portfolio_cash_total(context):
    """Return (cash, total_asset) from context.portfolio."""
    try:
        p = context.portfolio
        cash = float(p.cash or 0)
        total = float(p.portfolio_value or 0)
        if total <= 0:
            total = cash
        return cash, total
    except Exception:
        return 0.0, 0.0


def get_positions_map(context):
    """Return {ptrade_code: {shares, can_use, cost, amount, enable_amount}}."""
    out = {}
    try:
        positions = get_positions()
        if not positions:
            return out
        for sid, pos in positions.items():
            amount = int(getattr(pos, "amount", 0) or 0)
            if amount <= 0:
                continue
            enable = int(getattr(pos, "enable_amount", 0)
                         or getattr(pos, "enable_amount", 0) or 0)
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
    """Set of securities bought TODAY (from get_trades), used to infer buy_date
    for T+1 protection when the Position object has no open-date field."""
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
                if amt > 0:                     # buy (positive)
                    out.add(to_ptrade_code(t.get("sid") or t.get("symbol") or ""))
            except (TypeError, ValueError):
                continue
    except Exception:
        pass
    return out


# =====================================================================
# ORDERING
# =====================================================================
def do_order(code, amount, limit_price=None):
    """Buy (amount>0) or sell (amount<0). Returns True when the order was
    ACCEPTED (order() returns an order id), False on rejection/failure."""
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


# =====================================================================
# LEDGER / ORDER LOCKS (research-path files with in-memory fallback)
# =====================================================================
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


def order_locked(today, code, reason, lock_file, memo):
    try:
        d = _safe_read(lock_file, {})
        return bool(d.get(today, {}).get(code, {}).get(reason, False))
    except Exception:
        return False


def mark_order_locked(today, code, reason, lock_file, memo):
    try:
        d = _safe_read(lock_file, {})
        d.setdefault(today, {}).setdefault(code, {})[reason] = time.time()
        for old in [k for k in d if k != today]:
            d.pop(old, None)
        _safe_write(lock_file, d)
    except Exception:
        pass


def log_trade(memo, action, code, price, vol, reason, trade_log, dup_sec=300):
    """Append a trade record to memo['trade_log'] and persist to trade_log file
    when writable. Dedup by (action, code, price, vol) within dup_sec."""
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
        if now - sig_ts.get(sig, 0.0) < dup_sec:
            return
        sig_ts[sig] = now
        memo["trade_log"] = memo.get("trade_log", []) + [rec]
        _safe_write(trade_log, memo["trade_log"])
    except Exception:
        pass


# =====================================================================
# TRADING WINDOW
# =====================================================================
def is_trading_time(m):
    return (9 * 60 + 30 <= m <= 11 * 60 + 30) or (13 * 60 <= m <= 15 * 60)


def now_min():
    n = datetime.now()
    return n.hour * 60 + n.minute
