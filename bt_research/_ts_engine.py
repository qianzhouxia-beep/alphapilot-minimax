# -*- coding: utf-8 -*-
"""
_ts_engine.py - TrendState engine (ASCII, stdlib only).
Ported 1:1 from wb_trend_state_calc.py v1.0 (commit b66ddfc) so results are
identical to WB's reference implementation. Used by Track A QMT sim/live for:
  C  TSDOWN: holding State switches to DOWN -> next-open half-sell.
  B  D8 release: TrendScore>=55 x2 days + T3==1.0 + close>MA10 (3 conditions)
     before expire -> resume normal stops.
Inputs are time-ascending lists (no future leakage; caller must pass only
bars up to the decision reference day). All constants inline (no globals).
"""


def _clip(x, lo, hi):
    return max(lo, min(hi, x))


def _sma(vals, n, i):
    if i + 1 < n:
        return None
    return sum(vals[i + 1 - n:i + 1]) / n


def _pivots(highs, lows, k):
    n = len(highs)
    ph, pl = [], []
    for i in range(k, n - k):
        if highs[i] >= max(highs[i - k:i]) and highs[i] > max(highs[i + 1:i + k + 1]):
            ph.append(i)
        if lows[i] <= min(lows[i - k:i]) and lows[i] < min(lows[i + 1:i + k + 1]):
            pl.append(i)
    return ph, pl


def _linreg_r2(closes, i, n):
    if i + 1 < n or n < 3:
        return 0.0
    import math
    ys = [math.log(closes[j]) for j in range(i + 1 - n, i + 1)]
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((xs[j] - mx) * (ys[j] - my) for j in range(n))
    syy = sum((y - my) ** 2 for y in ys)
    if sxx and syy:
        return (sxy * sxy) / (sxx * syy)
    return 0.0


def ts_compute(closes, highs, lows, vols, params):
    """Full TrendState series over ascending bars.
    params: dict with ma_windows/slope_span/slope_norm10/slope_norm20/pivot_k/
            chan_n/roc_n/roc_norm/reg_n/vol_n/vr_lo/vr_hi/w{...}/
            up_th/down_th/confirm/veto_t4.
    Returns list of per-bar dict: {score, raw, state, t1,t2,t3,t4,t5,t6, veto}
    (state already confirm-lagged). score None before warmup."""
    ma_w = params["ma_windows"]
    span = params["slope_span"]
    k = params["pivot_k"]
    n = len(closes)
    out = []
    prev_state = None
    pend = None
    cnt = 0
    for i in range(n):
        ma = {w: _sma(closes, w, i) for w in ma_w}
        ma10_prev = _sma(closes, 10, i - span)
        ma20_prev = _sma(closes, 20, i - span)
        # T1
        if None in (ma[5], ma[10], ma[20], ma[60]):
            t1 = None
        else:
            t1 = int(closes[i] > ma[5]) + int(ma[5] > ma[10]) + \
                int(ma[10] > ma[20]) + int(ma[20] > ma[60])
        # T2
        if None in (ma[10], ma10_prev, ma[20], ma20_prev) or not ma10_prev or not ma20_prev:
            t2 = None
        else:
            s10 = ma[10] / ma10_prev - 1
            s20 = ma[20] / ma20_prev - 1
            n10 = _clip(s10 / params["slope_norm10"], -1, 1)
            n20 = _clip(s20 / params["slope_norm20"], -1, 1)
            t2 = (n10 + n20 + 2) / 4
        # T3
        ph, pl = _pivots(highs[:i + 1], lows[:i + 1], k)
        if len(ph) < 2 or len(pl) < 2:
            t3 = 0.5
        else:
            hh = highs[ph[-1]] > highs[ph[-2]]
            hl = lows[pl[-1]] > lows[pl[-2]]
            t3 = 0.5 * int(hh) + 0.5 * int(hl)
        # T4
        cnn = params["chan_n"]
        if i + 1 < cnn:
            t4 = None
        else:
            llv = min(lows[i + 1 - cnn:i + 1])
            hhv = max(highs[i + 1 - cnn:i + 1])
            if hhv - llv == 0:
                t4 = 0.5
            else:
                t4 = _clip((closes[i] - llv) / (hhv - llv), 0, 1)
        # T5
        rn = params["roc_n"]
        if i < rn:
            t5 = None
        else:
            roc = closes[i] / closes[i - rn] - 1
            mom = (_clip(roc / params["roc_norm"], -1, 1) + 1) / 2
            q = _linreg_r2(closes, i, params["reg_n"])
            t5 = 0.7 * mom + 0.3 * q
        # T6
        vn = params["vol_n"]
        if i < vn:
            t6 = None
        else:
            up_v, dn_v = [], []
            for j in range(i + 1 - vn, i + 1):
                if closes[j] > closes[j - 1]:
                    up_v.append(vols[j])
                elif closes[j] < closes[j - 1]:
                    dn_v.append(vols[j])
            if not dn_v:
                t6 = 1.0
            elif not up_v:
                t6 = 0.0
            else:
                vr = (sum(up_v) / len(up_v)) / (sum(dn_v) / len(dn_v)) if dn_v else 0.0
                t6 = _clip((vr - params["vr_lo"]) / (params["vr_hi"] - params["vr_lo"]), 0, 1)
        # warmup gate
        if i + 1 < max(ma_w) or None in (t1, t2, t3, t4, t5, t6):
            out.append({"score": None, "raw": None, "state": None,
                        "t1": t1, "t2": t2, "t3": t3, "t4": t4, "t5": t5,
                        "t6": t6, "veto": False})
            continue
        w = params["w"]
        score = 100.0 * (w["T1"] * t1 / 4 + w["T2"] * t2 + w["T3"] * t3
                         + w["T4"] * t4 + w["T5"] * t5 + w["T6"] * t6)
        veto = (t3 == 0.0 and t4 < params["veto_t4"])
        if veto:
            raw = "DOWN"
        elif score >= params["up_th"]:
            raw = "UP"
        elif score <= params["down_th"]:
            raw = "DOWN"
        else:
            raw = "RANGE"
        # confirm-lagged state machine (same as wb compute_series)
        if prev_state is None:
            state = raw
        elif raw == prev_state:
            pend, cnt = None, 0
            state = prev_state
        else:
            if pend == raw:
                cnt += 1
            else:
                pend, cnt = raw, 1
            if cnt >= params["confirm"]:
                prev_state = raw
                pend, cnt = None, 0
                state = prev_state
            else:
                state = prev_state
        prev_state = state
        out.append({"score": round(score, 1), "raw": raw, "state": state,
                    "t1": t1, "t2": round(t2, 3), "t3": t3, "t4": round(t4, 3),
                    "t5": round(t5, 3), "t6": round(t6, 3), "veto": bool(veto)})
    return out


TS_PARAMS = {
    "ma_windows": [5, 10, 20, 60],
    "slope_span": 5,
    "slope_norm10": 0.03,
    "slope_norm20": 0.02,
    "pivot_k": 3,
    "chan_n": 20,
    "roc_n": 10,
    "roc_norm": 0.10,
    "reg_n": 20,
    "vol_n": 10,
    "vr_lo": 0.6,
    "vr_hi": 1.6,
    "w": {"T1": 0.25, "T2": 0.15, "T3": 0.20,
          "T4": 0.15, "T5": 0.15, "T6": 0.10},
    "up_th": 65,
    "down_th": 40,
    "confirm": 2,
    "veto_t4": 0.30,
}


def ts_state_of(closes, highs, lows, vols, params=None):
    """Latest confirm-lagged state (UP/DOWN/RANGE) + last two scores + last
    T3 + ma10-of-last-close. Returns dict or None if data too short."""
    p = params or TS_PARAMS
    if len(closes) < max(p["ma_windows"]) + 5:
        return None
    ser = ts_compute(closes, highs, lows, vols, p)
    valid = [r for r in ser if r["score"] is not None]
    if len(valid) < 2:
        return None
    last = valid[-1]
    prev = valid[-2]
    # ma10 of the LAST bar (close vs ma10 -> use sma at last index)
    n = len(closes)
    ma10 = _sma(closes, 10, n - 1)
    return {
        "state": last["state"],
        "score": last["score"],
        "score_prev": prev["score"],
        "score_prev2": valid[-3]["score"] if len(valid) >= 3 else None,
        "t3": last["t3"],
        "t1": last["t1"],
        "t4": last["t4"],
        "close": closes[-1],
        "ma10": ma10,
    }
