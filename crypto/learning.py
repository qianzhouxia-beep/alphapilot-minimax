"""Self-improvement loop for the crypto paper trader.

Two responsibilities:
1. Attribution — scan historical closed trades, break down win rate / PnL by
   direction, symbol, exit reason, hour bucket, and per-direction threshold band.
   Flag any (symbol, direction) bucket that has lost money consistently and is
   statistically unlikely to be noise.
2. Adaptive thresholds — from attribution, propose per-symbol short/long score
   floor adjustments (raising the bar for losing buckets, never lowering the
   global floor too far). Applies bounds so the system can't over-react.

This is deliberately *conservative*: it never changes what the model predicts,
only how eager the trader is to act on low-confidence signals. The model itself
is still retrained daily by sg_pipeline.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

from .config import MODEL_DIR, PAPER


# ─── Attribution ───

@dataclass
class AttributionReport:
    n_trades: int = 0
    overall_win_rate: float = 0.0
    overall_pnl: float = 0.0
    by_direction: dict = field(default_factory=dict)   # dir -> stats
    by_symbol_dir: dict = field(default_factory=dict)  # (symbol, dir) -> stats
    by_exit_reason: dict = field(default_factory=dict) # reason -> stats
    by_hour: dict = field(default_factory=dict)        # hour -> stats
    flags: list = field(default_factory=list)          # actionable warnings


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
    """Bootstrap-ish estimate: probability that true win rate < 0.5.

    Uses a normal approximation of the binomial test. Returns 0..1.
    A bucket is 'consistently losing' when p > 0.9 AND n >= 10.
    """
    n = len(pnls)
    if n == 0:
        return 0.0
    wins = sum(1 for p in pnls if p > 0)
    p_hat = wins / n
    se = np.sqrt(max(p_hat * (1 - p_hat), 1e-6) / n)
    if se <= 0:
        return 0.0
    z = (0.5 - p_hat) / se  # how far below 50% are we, in SEs
    from math import erf, sqrt

    return 0.5 * (1 + erf(z / sqrt(2)))


def run_attribution(trades: list[dict], min_bucket_n: int = 10) -> AttributionReport:
    """Analyze closed trades and emit flags for consistently losing buckets."""
    rep = AttributionReport()
    if not trades:
        return rep

    rep.n_trades = len(trades)
    pnls = [t.get("pnl_usdt", 0.0) or 0.0 for t in trades]
    rep.overall_pnl = round(float(sum(pnls)), 2)
    rep.overall_win_rate = round(100 * sum(1 for p in pnls if p > 0) / len(pnls), 1)

    # direction
    by_dir: dict[str, list[float]] = {}
    by_sd: dict[tuple, list[float]] = {}
    by_exit: dict[str, list[float]] = {}
    by_hour: dict[int, list[float]] = {}

    for t in trades:
        d = t.get("direction", "?")
        sym = str(t.get("symbol", "?")).replace("/USDT:USDT", "")
        reason = t.get("exit_reason", "?")
        pnl = t.get("pnl_usdt", 0.0) or 0.0

        by_dir.setdefault(d, []).append(pnl)
        by_sd.setdefault((sym, d), []).append(pnl)
        by_exit.setdefault(reason, []).append(pnl)

        # hour bucket from exit_time
        try:
            et = str(t.get("exit_time", ""))
            if len(et) >= 13:
                hour = int(et[11:13])
                by_hour.setdefault(hour, []).append(pnl)
        except Exception:
            pass

    rep.by_direction = {k: _bucket_stats(v) for k, v in sorted(by_dir.items())}
    rep.by_symbol_dir = {f"{s}:{d}": _bucket_stats(v) for (s, d), v in sorted(by_sd.items())}
    rep.by_exit_reason = {k: _bucket_stats(v) for k, v in sorted(by_exit.items())}
    rep.by_hour = {f"{h:02d}h": _bucket_stats(v) for h, v in sorted(by_hour.items())}

    # Flags: consistently losing (symbol, direction) buckets
    for (s, d), pnls in sorted(by_sd.items()):
        st = _bucket_stats(pnls)
        if st["n"] >= min_bucket_n and st["pnl"] < 0:
            p = _prob_losing(pnls)
            if p > 0.9:
                rep.flags.append({
                    "type": "losing_bucket",
                    "bucket": f"{s}:{d}",
                    "n": st["n"],
                    "pnl": st["pnl"],
                    "win_rate": st["win_rate"],
                    "prob_losing": round(p, 3),
                    "suggestion": f"consider raising {d} threshold for {s} or disabling",
                })
    return rep


# ─── Adaptive thresholds ───

@dataclass
class AdaptiveDecision:
    asof: str
    baseline_long: float
    baseline_short: float
    per_symbol: dict = field(default_factory=dict)  # symbol -> {"long": floor, "short": floor}
    notes: list = field(default_factory=list)


# Max per-bucket adjustment from the global floor (keeps it conservative).
MAX_LIFT = 0.08
STEP = 0.01


def adapt_thresholds(rep: AttributionReport, state: dict | None = None) -> AdaptiveDecision:
    """Compute per-symbol threshold lifts from attribution.

    Rule: for each (symbol, dir) bucket with n >= min_n and pnl < 0 and
    prob_losing > 0.9, raise that symbol+dir entry floor by STEP per flag
    (capped at MAX_LIFT). Never lowers the global baseline.
    """
    dec = AdaptiveDecision(
        asof=datetime.now().isoformat(),
        baseline_long=PAPER.min_signal_score,
        baseline_short=PAPER.min_signal_score_short,
    )

    # load current per-symbol state (if any) to carry forward prior lifts
    per_sym: dict[str, dict] = {}
    path = MODEL_DIR / "adaptive_state.json"
    if path.exists():
        try:
            prev = json.loads(path.read_text(encoding="utf-8"))
            per_sym = prev.get("per_symbol", {})
            dec.notes.append(f"loaded prior adaptive state ({len(per_sym)} symbols)")
        except Exception:
            pass

    for fl in rep.flags:
        if fl["type"] != "losing_bucket":
            continue
        bucket = fl["bucket"]
        if ":" not in bucket:
            continue
        sym, d = bucket.rsplit(":", 1)
        if d not in ("long", "short"):
            continue

        cur = per_sym.setdefault(sym, {"long": None, "short": None})
        cur_val = cur[d]
        if cur_val is None:
            cur_val = dec.baseline_short if d == "short" else dec.baseline_long
        new_val = min(cur_val + STEP, dec.baseline_short + MAX_LIFT if d == "short"
                      else dec.baseline_long + MAX_LIFT)
        if new_val != cur_val:
            per_sym[sym][d] = round(new_val, 3)
            dec.notes.append(f"raised {sym} {d} floor {cur_val:.3f} -> {new_val:.3f} "
                             f"(n={fl['n']}, wr={fl['win_rate']}%)")

    dec.per_symbol = per_sym

    # persist
    path.write_text(json.dumps({
        "asof": dec.asof,
        "baseline_long": dec.baseline_long,
        "baseline_short": dec.baseline_short,
        "per_symbol": per_sym,
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
    """Persist a human-readable learning report to MODEL_DIR/learning_report.json."""
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
        },
        "adaptive": {
            "baseline_long": dec.baseline_long,
            "baseline_short": dec.baseline_short,
            "per_symbol": dec.per_symbol,
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
    print("\nflags:")
    for f in rep.flags:
        print(f"  {f['bucket']}: n={f['n']} pnl={f['pnl']:+.2f} wr={f['win_rate']}% "
              f"p_losing={f['prob_losing']}")
    print("\nadaptive per_symbol:")
    for s, d in dec.per_symbol.items():
        print(f"  {s}: {d}")
    print("\nnotes:")
    for n in dec.notes:
        print(f"  {n}")
