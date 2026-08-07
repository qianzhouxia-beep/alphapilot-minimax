"""Self-improvement loop for the crypto paper trader.

Two responsibilities:
1. Attribution — scan historical closed trades, break down win rate / PnL by
   direction, symbol, exit reason, hour bucket, hold duration bucket, entry
   session, and entry score band. Flag any bucket that has lost money
   consistently and is statistically unlikely to be noise.
2. Adaptive rules — from attribution, propose:
     - per-symbol/direction entry-score floor lifts (eager=raise bar for losers)
     - session gates (disable entry during a persistently losing time window)
     - score-band calibration (low-confidence trades winning much worse than
       high-confidence → raises the global floor)
   All adaptive state is persisted to adaptive_state.json and is conservative:
   it never changes what the model predicts, only how eager the trader is to
   act. The model itself is still retrained daily by sg_pipeline.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .config import MODEL_DIR, PAPER


# ─── Attribution ───

@dataclass
class AttributionReport:
    n_trades: int = 0
    overall_win_rate: float = 0.0
    overall_pnl: float = 0.0
    by_direction: dict = field(default_factory=dict)    # dir -> stats
    by_symbol_dir: dict = field(default_factory=dict)   # (symbol, dir) -> stats
    by_exit_reason: dict = field(default_factory=dict)  # reason -> stats
    by_hour: dict = field(default_factory=dict)         # hour -> stats
    by_hold_bucket: dict = field(default_factory=dict)  # hold-hours bucket -> stats
    by_session: dict = field(default_factory=dict)      # entry session -> stats
    by_score_band: dict = field(default_factory=dict)   # entry score band -> stats
    flags: list = field(default_factory=list)           # actionable warnings


# Hold-duration buckets (hours). Max hold is 48h, so 48h+ is the overflow.
HOLD_BUCKETS = [
    (0, 4, "0-4h"), (4, 8, "4-8h"), (8, 16, "8-16h"),
    (16, 24, "16-24h"), (24, 48, "24-48h"), (48, 1e9, "48h+"),
]
# Entry sessions by UTC hour of entry_time
SESSION_BUCKETS = {"asia": (0, 8), "europe": (8, 16), "us": (16, 24)}


def _session_of(hour: int) -> str:
    for name, (lo, hi) in SESSION_BUCKETS.items():
        if lo <= hour < hi:
            return name
    return "asia"


def _bucket_stats(pnls: list[float]) -> dict:
    if not pnls:
        return {"n": 0, "pnl": 0.0, "win_rate": 0.0, "avg": 0.0}
    wins = [p for p in pnls if p > 0]
    return {
        "n": len(pnls),
        "pnl": round(float(sum(pnls)), 2),
        "win_rate": round(100 * len(wins) / len(pnls), 1),
        "avg": round(float(np.mean(pnls)), 4),
    }


def _prob_losing(pnls: list[float]) -> float:
    """Probability that the true win rate is below 0.5 (normal approx of binomial)."""
    n = len(pnls)
    if n == 0:
        return 0.0
    wins = sum(1 for p in pnls if p > 0)
    p_hat = wins / n
    se = np.sqrt(max(p_hat * (1 - p_hat), 1e-6) / n)
    if se <= 0:
        return 0.0
    z = (0.5 - p_hat) / se
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _hold_hours(t: dict) -> float | None:
    """Held hours from entry_time/exit_time, or None if unparseable."""
    try:
        et = t.get("entry_time", "")
        xt = t.get("exit_time", "")
        if not et or not xt:
            return None
        return (pd.Timestamp(xt) - pd.Timestamp(et)).total_seconds() / 3600.0
    except Exception:
        return None


def run_attribution(trades: list[dict], min_bucket_n: int = 10) -> AttributionReport:
    """Analyze closed trades and emit flags for consistently losing buckets."""
    rep = AttributionReport()
    if not trades:
        return rep

    rep.n_trades = len(trades)
    pnls = [t.get("pnl_usdt", 0.0) or 0.0 for t in trades]
    rep.overall_pnl = round(float(sum(pnls)), 2)
    rep.overall_win_rate = round(100 * sum(1 for p in pnls if p > 0) / len(pnls), 1)

    by_dir: dict[str, list[float]] = {}
    by_sd: dict[tuple, list[float]] = {}
    by_exit: dict[str, list[float]] = {}
    by_hour: dict[int, list[float]] = {}
    by_hold: dict[str, list[float]] = {}
    by_session: dict[str, list[float]] = {}
    by_band: dict[str, list[float]] = {}

    for t in trades:
        d = t.get("direction", "?")
        sym = str(t.get("symbol", "?")).replace("/USDT:USDT", "")
        reason = t.get("exit_reason", "?")
        pnl = t.get("pnl_usdt", 0.0) or 0.0

        by_dir.setdefault(d, []).append(pnl)
        by_sd.setdefault((sym, d), []).append(pnl)
        by_exit.setdefault(reason, []).append(pnl)

        # hour & session from exit/entry time
        et = str(t.get("exit_time", ""))
        if len(et) >= 13:
            try:
                hour = int(et[11:13])
                by_hour.setdefault(hour, []).append(pnl)
            except Exception:
                pass
        ent = str(t.get("entry_time", ""))
        if len(ent) >= 13:
            try:
                by_session.setdefault(_session_of(int(ent[11:13])), []).append(pnl)
            except Exception:
                pass

        # hold duration
        hh = _hold_hours(t)
        if hh is not None:
            for lo, hi, name in HOLD_BUCKETS:
                if lo <= hh < hi:
                    by_hold.setdefault(name, []).append(pnl)
                    break

        # entry score band (only present on trades entered after v2 deploy)
        sc = t.get("entry_score")
        if sc is not None:
            if sc < 0.50:
                band = "low(<0.50)"
            elif sc < 0.55:
                band = "mid(0.50-0.55)"
            else:
                band = "high(>=0.55)"
            by_band.setdefault(band, []).append(pnl)

    rep.by_direction = {k: _bucket_stats(v) for k, v in sorted(by_dir.items())}
    rep.by_symbol_dir = {f"{s}:{d}": _bucket_stats(v) for (s, d), v in sorted(by_sd.items())}
    rep.by_exit_reason = {k: _bucket_stats(v) for k, v in sorted(by_exit.items())}
    rep.by_hour = {f"{h:02d}h": _bucket_stats(v) for h, v in sorted(by_hour.items())}
    rep.by_hold_bucket = {k: _bucket_stats(v) for k, v in sorted(by_hold.items())}
    rep.by_session = {k: _bucket_stats(v) for k, v in sorted(by_session.items())}
    rep.by_score_band = {k: _bucket_stats(v) for k, v in sorted(by_band.items())}

    # Flags: consistently losing (symbol, direction) buckets
    for (s, d), pnls in sorted(by_sd.items()):
        st = _bucket_stats(pnls)
        if st["n"] >= min_bucket_n and st["pnl"] < 0:
            p = _prob_losing(pnls)
            if p > 0.9:
                rep.flags.append({
                    "type": "losing_bucket",
                    "bucket": f"{s}:{d}",
                    "n": st["n"], "pnl": st["pnl"], "win_rate": st["win_rate"],
                    "prob_losing": round(p, 3),
                    "suggestion": f"raise {d} threshold for {s} or disable",
                })

    # Flags: persistently losing session (entries during a time window)
    for name, pnls in sorted(by_session.items()):
        st = _bucket_stats(pnls)
        if st["n"] >= min_bucket_n and st["pnl"] < 0:
            p = _prob_losing(pnls)
            if p > 0.9:
                rep.flags.append({
                    "type": "losing_session",
                    "bucket": f"session:{name}",
                    "n": st["n"], "pnl": st["pnl"], "win_rate": st["win_rate"],
                    "prob_losing": round(p, 3),
                    "suggestion": f"disable entries during {name} session (UTC {SESSION_BUCKETS[name][0]}-{SESSION_BUCKETS[name][1]}h)",
                })

    # Flags: persistently losing hold-duration bucket (hint to shorten max_hold)
    for name, pnls in sorted(by_hold.items()):
        st = _bucket_stats(pnls)
        if st["n"] >= min_bucket_n and st["pnl"] < 0:
            p = _prob_losing(pnls)
            if p > 0.9:
                rep.flags.append({
                    "type": "losing_hold",
                    "bucket": f"hold:{name}",
                    "n": st["n"], "pnl": st["pnl"], "win_rate": st["win_rate"],
                    "prob_losing": round(p, 3),
                    "suggestion": f"shorten max_hold or trail earlier for holds {name}",
                })

    # Score-band calibration: low-confidence wins notably worse than high-confidence
    if len(by_band) >= 2:
        low = by_band.get("low(<0.50)", [])
        high = by_band.get("high(>=0.55)", [])
        if len(low) >= 8 and len(high) >= 8:
            low_wr = 100 * sum(1 for p in low if p > 0) / len(low)
            high_wr = 100 * sum(1 for p in high if p > 0) / len(high)
            low_pnl = float(sum(low))
            if low_wr < high_wr - 12 and low_pnl < 0:
                rep.flags.append({
                    "type": "low_conf_degraded",
                    "bucket": "score_band:low",
                    "n": len(low), "pnl": round(low_pnl, 2), "win_rate": round(low_wr, 1),
                    "high_win_rate": round(high_wr, 1),
                    "prob_losing": round(_prob_losing(low), 3),
                    "suggestion": "raise the global min_signal_score floor",
                })

    return rep


# ─── Adaptive rules ───

@dataclass
class AdaptiveDecision:
    asof: str
    baseline_long: float
    baseline_short: float
    per_symbol: dict = field(default_factory=dict)  # symbol -> {"long": floor, "short": floor}
    session_gates: dict = field(default_factory=dict)  # session name -> since ISO
    notes: list = field(default_factory=list)


MAX_LIFT = 0.08   # max per-bucket lift from the global floor
STEP = 0.01       # per-flag step
MIN_BAND_RAISE = 0.005  # when low-confidence bucket flagged, nudge the global floor


def adapt_thresholds(rep: AttributionReport, state: dict | None = None) -> AdaptiveDecision:
    """Compute adaptive rules from attribution, carrying forward prior state."""
    dec = AdaptiveDecision(
        asof=datetime.now().isoformat(),
        baseline_long=PAPER.min_signal_score,
        baseline_short=PAPER.min_signal_score_short,
    )

    path = MODEL_DIR / "adaptive_state.json"
    prev = {}
    if path.exists():
        try:
            prev = json.loads(path.read_text(encoding="utf-8"))
            dec.per_symbol = prev.get("per_symbol", {})
            dec.session_gates = prev.get("session_gates", {})
            if prev.get("baseline_long"):
                dec.baseline_long = prev["baseline_long"]
            if prev.get("baseline_short"):
                dec.baseline_short = prev["baseline_short"]
            dec.notes.append(f"loaded prior adaptive state ({len(dec.per_symbol)} symbols, "
                             f"{len(dec.session_gates)} session gates)")
        except Exception:
            pass

    for fl in rep.flags:
        # 1) Per-symbol/direction floor lift
        if fl["type"] == "losing_bucket":
            bucket = fl["bucket"]
            if ":" not in bucket:
                continue
            sym, d = bucket.rsplit(":", 1)
            if d not in ("long", "short"):
                continue
            base = dec.baseline_short if d == "short" else dec.baseline_long
            cur = dec.per_symbol.setdefault(sym, {"long": None, "short": None})
            cur_val = cur[d] if cur[d] is not None else base
            new_val = min(cur_val + STEP, base + MAX_LIFT)
            if new_val != cur_val:
                dec.per_symbol[sym][d] = round(new_val, 3)
                dec.notes.append(f"raised {sym} {d} floor {cur_val:.3f} -> {new_val:.3f} "
                                 f"(n={fl['n']}, wr={fl['win_rate']}%)")

        # 2) Session gates (disable a whole entry window)
        elif fl["type"] == "losing_session":
            name = fl["bucket"].split(":", 1)[1]
            if name not in dec.session_gates:
                dec.session_gates[name] = datetime.now().isoformat()
                dec.notes.append(f"gated entries during {name} session (wr={fl['win_rate']}%, "
                                 f"pnl={fl['pnl']:+.2f})")

        # 3) Low-confidence degradation → nudge global floor up
        elif fl["type"] == "low_conf_degraded":
            dec.baseline_long = round(min(dec.baseline_long + MIN_BAND_RAISE, PAPER.min_signal_score + MAX_LIFT), 3)
            dec.baseline_short = round(min(dec.baseline_short + MIN_BAND_RAISE, PAPER.min_signal_score_short + MAX_LIFT), 3)
            dec.notes.append(f"raised global floors (low-conf wr={fl['win_rate']}% vs high "
                             f"{fl['high_win_rate']}%) -> long={dec.baseline_long:.3f} short={dec.baseline_short:.3f}")

    path.write_text(json.dumps({
        "asof": dec.asof,
        "baseline_long": dec.baseline_long,
        "baseline_short": dec.baseline_short,
        "per_symbol": dec.per_symbol,
        "session_gates": dec.session_gates,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    return dec


def resolve_entry_threshold(sym: str, direction: str, dec: AdaptiveDecision | None = None) -> float:
    """Effective entry floor for (symbol, direction): baseline or lifted."""
    if dec is None:
        dec = load_adaptive()
    base = dec.baseline_short if direction == "short" else dec.baseline_long
    sym_ov = dec.per_symbol.get(sym, {})
    val = sym_ov.get(direction)
    return val if val is not None else base


def session_gate_disabled(session_name: str, dec: AdaptiveDecision | None = None) -> bool:
    """Whether entries are currently gated for a session."""
    if dec is None:
        dec = load_adaptive()
    return session_name in dec.session_gates


def load_adaptive() -> AdaptiveDecision:
    path = MODEL_DIR / "adaptive_state.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return AdaptiveDecision(
                asof=data.get("asof", ""),
                baseline_long=data.get("baseline_long", PAPER.min_signal_score),
                baseline_short=data.get("baseline_short", PAPER.min_signal_score_short),
                per_symbol=data.get("per_symbol", {}),
                session_gates=data.get("session_gates", {}),
            )
        except Exception:
            pass
    return AdaptiveDecision(
        asof=datetime.now().isoformat(),
        baseline_long=PAPER.min_signal_score,
        baseline_short=PAPER.min_signal_score_short,
    )


# ─── Report writer ───

def write_learning_report(rep: AttributionReport, dec: AdaptiveDecision) -> Path:
    out = {
        "asof": datetime.now().isoformat(),
        "attribution": {
            "n_trades": rep.n_trades,
            "overall_pnl": rep.overall_pnl,
            "overall_win_rate": rep.overall_win_rate,
            "by_direction": rep.by_direction,
            "by_symbol_dir": rep.by_symbol_dir,
            "by_exit_reason": rep.by_exit_reason,
            "by_hour": rep.by_hour,
            "by_hold_bucket": rep.by_hold_bucket,
            "by_session": rep.by_session,
            "by_score_band": rep.by_score_band,
        },
        "adaptive": {
            "baseline_long": dec.baseline_long,
            "baseline_short": dec.baseline_short,
            "per_symbol": dec.per_symbol,
            "session_gates": dec.session_gates,
            "notes": dec.notes,
        },
        "flags": rep.flags,
    }
    path = MODEL_DIR / "learning_report.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_learning_loop(trades: list[dict], min_bucket_n: int = 10) -> tuple[AttributionReport, AdaptiveDecision, Path]:
    """One full learning pass: attribute → adapt → persist."""
    rep = run_attribution(trades, min_bucket_n=min_bucket_n)
    dec = adapt_thresholds(rep)
    path = write_learning_report(rep, dec)
    return rep, dec, path


if __name__ == "__main__":
    import sys

    state_path = MODEL_DIR / "paper_state.json"
    trades = []
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        trades = state.get("trades", [])
        print(f"Loaded {len(trades)} trades from {state_path}")

    rep, dec, path = run_learning_loop(trades)
    print(f"\n=== Learning Report ({path}) ===")
    print(f"trades: {rep.n_trades}  overall_pnl: {rep.overall_pnl:+.2f}  win_rate: {rep.overall_win_rate}%")
    print("\nby direction:")
    for k, v in rep.by_direction.items():
        print(f"  {k}: {v}")
    if rep.by_session:
        print("\nby session:")
        for k, v in rep.by_session.items():
            print(f"  {k}: {v}")
    if rep.by_hold_bucket:
        print("\nby hold bucket:")
        for k, v in rep.by_hold_bucket.items():
            print(f"  {k}: {v}")
    if rep.by_score_band:
        print("\nby score band:")
        for k, v in rep.by_score_band.items():
            print(f"  {k}: {v}")
    print("\nflags:")
    for f in rep.flags:
        print(f"  [{f['type']}] {f['bucket']}: n={f['n']} pnl={f['pnl']:+.2f} wr={f['win_rate']}% "
              f"p_losing={f['prob_losing']}")
    print("\nadaptive:")
    print(f"  baselines: long={dec.baseline_long} short={dec.baseline_short}")
    print(f"  per_symbol: {dec.per_symbol}")
    print(f"  session_gates: {dec.session_gates}")
    print("\nnotes:")
    for n in dec.notes:
        print(f"  {n}")
