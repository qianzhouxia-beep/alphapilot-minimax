#!/usr/bin/env python3
"""24/7 Continuous Paper Trading Simulation — Singapore Server.

Stateful grid-style simulation that runs forever:
  - Every 120s, checks for new 2h bar from Binance
  - Computes features, predicts, enters/exits positions
  - Persists state.json for crash recovery
  - Handles SIGTERM/SIGINT gracefully
  - Auto-reloads model after daily retrain (checks mtime)

State file:  {MODEL_DIR}/paper_state.json
Equity log:  {MODEL_DIR}/paper_equity.jsonl
"""
from __future__ import annotations

import json
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Ensure alphapilot root is on path
_THIS_DIR = Path(__file__).resolve().parent
_APP_ROOT = _THIS_DIR.parent
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from crypto import config as C
from crypto.learning import load_adaptive, resolve_entry_threshold, session_gate_disabled
from crypto.smc_gate import (
    direction_allowed,
    explain,
    trend_state,
    is_counter_trend,
    counter_trend_min_signal,
    chop_min_signal,
)

# ─── Constants (mirrors grid_backtest.py) ───
MAKER_FEE = C.MAKER_FEE
TAKER_FEE = C.TAKER_FEE
# Win-rate optimization (OOS-validated, 2026-08-10):
#   tighter TP (0.5/1/1.5%) → 2h bars hit TP easily → win rate 64.8%→81.3% OOS
#   wider SL (-2.5/-3/-4%)  → avoid stop-out by 2h noise
#   max_hold 24 bars (48h)  → let winners breathe, cut stale losers
TAKE_PROFIT_LEVELS = [0.005, 0.01, 0.015]
STOP_LOSS_LEVELS = [-0.025, -0.03, -0.04]
BATCHES = 3
BATCH_SPREAD = 0.005
MAX_POSITIONS_PER_SYM = C.PAPER.max_positions

FEATURE_WINDOW = 500

# How often to reload model/factors (in cycles, 60s per cycle)
RELOAD_INTERVAL = 60  # ~2h (120s per cycle)


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ─── Model / factors ───

_model_l: Any = None
_model_s: Any = None
_model_l_mtime: float = 0.0
_model_s_mtime: float = 0.0


def _ensure_model():
    """Load long+short models if not loaded, or reload if files changed (daily retrain)."""
    global _model_l, _model_s, _model_l_mtime, _model_s_mtime
    import xgboost as xgb

    # Long model (always)
    lpath = C.MODEL_DIR / "model_long.ubj"
    if not lpath.exists():
        raise FileNotFoundError(f"Model not found: {lpath}")
    lmtime = lpath.stat().st_mtime
    if _model_l is None or lmtime > _model_l_mtime:
        _model_l = xgb.Booster()
        _model_l.load_model(str(lpath))
        _model_l_mtime = lmtime
        log(f"Model loaded/reloaded: {lpath} (mtime={datetime.fromtimestamp(lmtime).strftime('%H:%M:%S')})")

    # Short model (optional, only if enabled and file exists)
    if C.USE_SHORT_MODEL:
        spath = C.MODEL_DIR / "model_short.ubj"
        if not spath.exists():
            if _model_s is not None:
                log("WARNING: model_short.ubj removed — short signals disabled")
            _model_s = None
        else:
            smtime = spath.stat().st_mtime
            if _model_s is None or smtime > _model_s_mtime:
                _model_s = xgb.Booster()
                _model_s.load_model(str(spath))
                _model_s_mtime = smtime
                log(f"Model loaded/reloaded: {spath} (mtime={datetime.fromtimestamp(smtime).strftime('%H:%M:%S')})")
    else:
        _model_s = None


def _load_icir_factors() -> list[str]:
    """Load the exact factor list used for training (model_factors.json).

    Falls back to ICIR top-K for backward-compat. Returns empty if none found.
    """
    mf = C.MODEL_DIR / "model_factors.json"
    if mf.exists():
        try:
            with open(mf) as f:
                factors = json.load(f).get("factors", [])
            if factors:
                return factors
        except Exception:
            pass
    if not C.ICIR_PATH.exists():
        return []
    with open(C.ICIR_PATH) as f:
        icir_data = json.load(f)
    ranked = sorted(icir_data.get("summary", {}).items(), key=lambda x: -x[1]["abs_icir"])
    return [f[0] for f in ranked[:C.ICIR_TOP_K]]


# ─── State persistence ───

STATE_PATH = C.MODEL_DIR / "paper_state.json"
EQUITY_LOG = C.MODEL_DIR / "paper_equity.jsonl"


def _save_state(state: dict):
    state["saved_at"] = datetime.now().isoformat()
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_state() -> dict:
    if not STATE_PATH.exists():
        log("No state file found, initializing fresh")
        return _fresh_state()
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        # Migration: pre-bar_seq states stored next_batch_id in last_signal_by_sym,
        # which froze cooldown in quiet markets. Reset so bar_seq starts clean.
        if "bar_seq" not in data:
            data["bar_seq"] = 0
            data["last_signal_by_sym"] = {}
        log(f"State loaded: {len(data.get('trades',[]))} trades, "
             f"{len(data.get('positions',[]))} open, capital=${data.get('capital',0):.2f}")
        return data
    except Exception as e:
        log(f"ERROR loading state: {e}, starting fresh")
        return _fresh_state()


def _fresh_state() -> dict:
    return {
        "initial_capital": 1000.0,
        "capital": 1000.0,
        "positions": [],
        "trades": [],
        "equity_curve": [1000.0],
        "next_batch_id": 0,
        "bar_seq": 0,
        "last_bar_ts": "",
        "last_signal_by_sym": {},
        "last_price_by_sym": {},
        "total_entries": 0,
        "total_exits": 0,
    }


# ─── Signal handling ───

_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    log(f"Signal {signum} received, shutting down gracefully...")
    _shutdown = True


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


# ─── Data fetching ───

def _fetch_all_new_bars(last_bar_ts: str) -> pd.DataFrame:
    """Fetch latest 2h bars for all symbols."""
    from crypto.data import fetch_klines
    all_dfs = []
    since = None
    if last_bar_ts:
        try:
            since = pd.Timestamp(last_bar_ts)
        except Exception:
            pass
    for sym in C.SYMBOLS:
        try:
            df = fetch_klines(sym, timeframe="2h", limit=100)
            if df.empty:
                continue
            if since is not None:
                overlap = since - pd.Timedelta(hours=6)  # 3×2h overlap
                df = df[df["timestamp"] > overlap].copy()
            if df.empty:
                continue
            df["symbol"] = sym
            df["timeframe"] = "2h"
            all_dfs.append(df)
            time.sleep(0.3)
        except Exception as e:
            log(f"  Error fetching {sym}: {e}")
    if not all_dfs:
        return pd.DataFrame()
    return pd.concat(all_dfs, ignore_index=True).sort_values(["symbol", "timestamp"]).reset_index(drop=True)


# ─── Position logic ───

def _check_exits(state: dict, sym: str, price: float, ts: pd.Timestamp) -> list[dict]:
    """Check and close positions for a symbol. Returns closed trade dicts."""
    closed = []
    for pos in list(state["positions"]):
        if pos.get("symbol") != sym:
            continue
        direction = pos["direction"]
        unrealized = (price / pos["entry_price"] - 1) * (1 if direction == "long" else -1)
        level = pos.get("level", 0)
        tp = TAKE_PROFIT_LEVELS[min(level, len(TAKE_PROFIT_LEVELS) - 1)]
        sl = STOP_LOSS_LEVELS[min(level, len(STOP_LOSS_LEVELS) - 1)]

        try:
            entry_ts = pd.Timestamp(pos["entry_time"])
            bars_held = (ts - entry_ts).total_seconds() / 3600
            if bars_held >= C.EXIT.max_hold_bars * 2:  # bars × 2h timeframe
                pos["exit_reason"] = "max_hold"
                closed.append(_close_batch(pos, price, ts))
                state["positions"].remove(pos)
                continue
        except Exception:
            pass

        if unrealized >= tp:
            pos["exit_reason"] = "take_profit"
            closed.append(_close_batch(pos, price, ts))
            state["positions"].remove(pos)
            continue
        if unrealized <= sl:
            pos["exit_reason"] = "stop_loss"
            closed.append(_close_batch(pos, price, ts))
            state["positions"].remove(pos)
            continue
    return closed


def _close_batch(pos: dict, exit_price: float, ts: pd.Timestamp) -> dict:
    direction = pos["direction"]
    # Maker exits (take_profit): limit fill — no slippage, maker fee.
    # Taker exits (stop_loss/max_hold): market fill — taker fee.
    reason = pos.get("exit_reason", "")
    if reason == "take_profit":
        eff_fee = MAKER_FEE
    else:
        eff_fee = TAKER_FEE
    pnl_pct = (exit_price / pos["entry_price"] - 1) * (1 if direction == "long" else -1)
    pnl_usdt = pos["batch_size"] * pnl_pct
    fee = pos["batch_size"] * pos.get("entry_fee_rate", MAKER_FEE) + pos["batch_size"] * eff_fee
    return {
        "symbol": pos["symbol"], "batch_id": pos["batch_id"],
        "entry_time": pos["entry_time"], "entry_price": pos["entry_price"],
        "direction": direction, "batch_size": pos["batch_size"],
        "exit_time": ts.isoformat(), "exit_price": exit_price,
        "entry_score": pos.get("entry_score"),
        "pnl_pct": round(pnl_pct, 6), "pnl_usdt": round(pnl_usdt - fee, 4),
        "exit_reason": reason, "fee_usdt": round(fee, 4),
    }


def _try_entry(state: dict, sym: str, price: float, prob_l: float, prob_s: float, ts: pd.Timestamp,
               atr_pct: float | None = None, trend: str = "chop", trend_breakdown: dict | None = None):
    active = sum(1 for p in state["positions"] if p.get("symbol") == sym)
    if active >= MAX_POSITIONS_PER_SYM * BATCHES:
        return

    # Adaptive per-symbol/direction floors (learned from attribution loop)
    adaptive = load_adaptive()
    thr_l = resolve_entry_threshold(sym, "long", adaptive)
    thr_s = resolve_entry_threshold(sym, "short", adaptive)

    # Session gate: skip entries during a persistently-losing UTC window
    try:
        hour = ts.hour
        sess = "asia" if hour < 8 else ("europe" if hour < 16 else "us")
        if session_gate_disabled(sess, adaptive):
            return
    except Exception:
        pass

    best_signal, best_dir = 0.0, None
    if prob_l > thr_l and prob_l > best_signal:
        best_signal, best_dir = prob_l, "long"
    if prob_s > thr_s and prob_s > best_signal:
        best_signal, best_dir = prob_s, "short"
    if best_dir is None:
        return

    # SMC Layer ① — selective trend gate (backtest-validated):
    #   with-trend → keep original thresholds
    #   counter-trend → require stronger signal (≥0.55)
    #   chop (no clear HTF structure) → allow only if signal strong (≥0.55)
    if C.SMC_ENABLED:
        if is_counter_trend(best_dir, trend):
            if best_signal < counter_trend_min_signal():
                state.setdefault("smc", {}).setdefault("blocks", {}).setdefault("counter_trend", 0)
                state["smc"]["blocks"]["counter_trend"] += 1
                log(f"  SMC-GATE BLOCK {sym.replace('/USDT:USDT','')} {best_dir} "
                    f"(counter-trend sig={best_signal:.3f}<{counter_trend_min_signal():.2f} "
                    f"[{explain(trend_breakdown or {})}])")
                return
        elif not direction_allowed(best_dir, trend):
            if best_signal < chop_min_signal():
                state.setdefault("smc", {}).setdefault("blocks", {}).setdefault("chop", 0)
                state["smc"]["blocks"]["chop"] += 1
                log(f"  SMC-GATE BLOCK {sym.replace('/USDT:USDT','')} {best_dir} "
                    f"(chop sig={best_signal:.3f}<{chop_min_signal():.2f} "
                    f"[{explain(trend_breakdown or {})}])")
                return

    # Cooldown between signals per symbol, measured in bars (matches backtest).
    last = state["last_signal_by_sym"].get(sym, -C.SIGNAL_COOLDOWN_BARS)
    if state["bar_seq"] - last < C.SIGNAL_COOLDOWN_BARS:
        return

    state["last_signal_by_sym"][sym] = state["bar_seq"]

    # ATR-based dynamic batch sizing (Turtle-inspired)
    if C.PAPER.use_atr_sizing and atr_pct is not None and atr_pct > 1e-6:
        raw_batch = state["capital"] * C.PAPER.atr_risk_pct / (atr_pct * BATCHES)
        max_batch = state["capital"] * C.PAPER.atr_max_batch_pct
        batch_size = min(raw_batch, max_batch)
    else:
        batch_size = state["capital"] * C.PAPER.per_trade_risk / BATCHES

    # Global exposure cap: never exceed global_max_position_pct of capital in open batches.
    # Check AFTER sizing so we compare against the actual batch that would open (not a
    # theoretical 3×atr_max_batch_pct which already exceeds the cap by construction).
    try:
        cap = state.get("capital", 0) or 1e-9
        total_expo = sum(p.get("batch_size", 0) for p in state["positions"])
        if total_expo + batch_size * BATCHES > cap * C.PAPER.global_max_position_pct:
            return
    except Exception:
        pass

    for level in range(BATCHES):
        px = price * (1 - level * BATCH_SPREAD) if best_dir == "long" else price * (1 + level * BATCH_SPREAD)
        state["positions"].append({
            "symbol": sym, "direction": best_dir, "entry_price": px,
            "batch_size": batch_size, "level": level,
            "batch_id": state["next_batch_id"],
            "entry_time": ts.isoformat(), "exit_reason": "",
            "entry_score": best_signal, "entry_atr_pct": atr_pct,
            "entry_fee": batch_size * MAKER_FEE, "entry_fee_rate": MAKER_FEE,
        })
        state["next_batch_id"] += 1

    state["total_entries"] += 1
    risk_str = f"atr_batch=${batch_size:.2f}" if C.PAPER.use_atr_sizing and atr_pct is not None and atr_pct > 1e-6 else f"risk=${state['capital']*C.PAPER.per_trade_risk:.2f}"
    log(f"  ENTER {sym.replace('/USDT:USDT','')} {best_dir} @ ${price:.2f} "
        f"(prob={best_signal:.3f}, {risk_str})")


# ─── Capital / equity ───

def _recalc_capital(state: dict) -> float:
    cap = state["initial_capital"]
    for t in state["trades"]:
        cap += t.get("pnl_usdt", 0)
    return max(cap, 0)


def _compute_equity(state: dict) -> float:
    cap = _recalc_capital(state)
    upnl = 0.0
    last_px = state.get("last_price_by_sym", {})
    for p in state["positions"]:
        px = last_px.get(p["symbol"])
        if px is None:
            continue
        upnl += p["batch_size"] * (px / p["entry_price"] - 1) * (1 if p["direction"] == "long" else -1)
    return max(cap + upnl, 0)


# ─── Main ───

def _main_loop():
    log("=" * 50)
    log("AlphaPilot Crypto — 24/7 Paper Trader Starting")
    log("=" * 50)
    log(f"Config: {C.PAPER.per_trade_risk*100:.0f}% risk/signal, "
         f"min_score={C.PAPER.min_signal_score}/{C.PAPER.min_signal_score_short} (long/short), "
         f"{len(C.SYMBOLS)} symbols, 2h timeframe, "
         f"direction={'long+short' if C.USE_SHORT_MODEL else 'long-only'}")

    # Load adaptive state (per-symbol threshold lifts from learning loop)
    try:
        from crypto.learning import load_adaptive
        _adaptive = load_adaptive()
        if _adaptive.per_symbol:
            log(f"Adaptive floors loaded: {_adaptive.per_symbol}")
    except Exception:
        pass

    state = _load_state()

    # Preload model
    try:
        _ensure_model()
    except FileNotFoundError as e:
        log(f"FATAL: {e}. Run sg_pipeline.py first.")
        sys.exit(1)

    factors = _load_icir_factors()
    if not factors:
        log("WARNING: No ICIR factors found, will try again on first cycle")

    log(f"Factors: {len(factors)}")
    log(f"Open positions: {len(state['positions'])}")

    # Initial data window
    log("Fetching initial data window...")
    from crypto.data import build_dataset
    from crypto.features import compute_features, list_factors
    df_cache = build_dataset(limit=FEATURE_WINDOW * 3, force_refresh=False)
    log(f"Cache: {len(df_cache)} rows")
    df_cache = compute_features(df_cache, forward=None, threshold=None)
    if not factors:
        factors = _load_icir_factors() or list_factors()
    _fill_factors(df_cache, factors)
    log(f"Cache ready: {len(df_cache)} rows, {len(factors)} factors")

    cycle_count = 0
    reload_countdown = 0
    log("Entering main loop (checking every 120s)...")

    while not _shutdown:
        try:
            # Periodically reload model & factors (after daily retrain)
            reload_countdown -= 1
            if reload_countdown <= 0:
                _ensure_model()
                new_factors = _load_icir_factors()
                if new_factors:
                    factors = new_factors
                reload_countdown = RELOAD_INTERVAL
                # Self-improvement pass: attribute recent trades → adapt thresholds
                try:
                    from crypto.learning import run_learning_loop
                    _, _, _lpath = run_learning_loop(state.get("trades", []))
                    log(f"Learning pass done ({len(state.get('trades', []))} trades) → {_lpath}")
                except Exception as _e:
                    log(f"Learning pass failed: {_e}")

            df_cache = _main_cycle(state, df_cache, factors)
            cycle_count += 1

            if cycle_count % 30 == 0:
                eq = _compute_equity(state)
                ret = (eq / state["initial_capital"] - 1) * 100
                log(f"Alive: {cycle_count} cycles, {len(state['positions'])} positions, "
                     f"capital=${state['capital']:.2f}, equity=${eq:.2f} ({ret:+.2f}%)")

            time.sleep(120)
        except KeyboardInterrupt:
            break
        except Exception as e:
            log(f"ERROR in cycle {cycle_count}: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(60)

    _save_state(state)
    log(f"Shutdown. Capital: ${state['capital']:.2f}, "
         f"Trades: {len(state['trades'])}, Positions: {len(state['positions'])}")


def _main_cycle(state: dict, df_cache: pd.DataFrame, factors: list[str]) -> pd.DataFrame:
    """One cycle: fetch latest → score → enter/exit. Returns updated df_cache."""
    from crypto.features import compute_features

    new_df = _fetch_all_new_bars(state.get("last_bar_ts", ""))
    if new_df.empty:
        return df_cache

    latest_ts = new_df["timestamp"].max()
    latest_ts_str = latest_ts.isoformat()
    if latest_ts_str == state.get("last_bar_ts", ""):
        return df_cache
    state["last_bar_ts"] = latest_ts_str
    # Cooldown timebase: bar sequence (matches grid_backtest's `i`). Using
    # next_batch_id here was a bug — batch ids only advance on entries, so a
    # quiet market froze cooldown forever and silently blocked new entries.
    state["bar_seq"] = state.get("bar_seq", 0) + 1
    log(f"New bar: {latest_ts} (seq={state['bar_seq']})")

    # Merge & recompute features
    df_cache = _merge_into_cache(df_cache, new_df)
    # Safety: ensure columns exist after merge
    for col in ["symbol", "timeframe"]:
        if col not in df_cache.columns:
            log(f"WARNING: '{col}' missing after merge, re-fetching cache")
            from crypto.data import build_dataset
            df_cache = build_dataset(limit=FEATURE_WINDOW * 3, force_refresh=False)
            df_cache = compute_features(df_cache, forward=None, threshold=None)
            break
    else:
        df_cache = compute_features(df_cache, forward=None, threshold=None)
    _fill_factors(df_cache, factors)

    # Get latest 2h bar per symbol
    df_2h = df_cache[df_cache["timeframe"] == "2h"].dropna(subset=factors).copy()
    if df_2h.empty:
        return df_cache
    latest = df_2h.groupby("symbol", sort=False).last().reset_index()

    # Score (long + short)
    import xgboost as xgb
    _ensure_model()
    X = latest[factors].values
    dmat = xgb.DMatrix(X)
    probs_l = _model_l.predict(dmat)
    probs_s = _model_s.predict(dmat) if (C.USE_SHORT_MODEL and _model_s is not None) else None

    # Process each symbol
    for i, row in latest.iterrows():
        sym = row["symbol"]
        price = float(row["close"])
        prob_l = float(probs_l[i])
        prob_s = float(probs_s[i]) if probs_s is not None else 0.0
        ts = row["timestamp"] if isinstance(row["timestamp"], pd.Timestamp) else latest_ts
        state["last_price_by_sym"][sym] = price

        # 1. Exits (same symbol)
        closed = _check_exits(state, sym, price, ts)
        for ct in closed:
            state["trades"].append(ct)
            state["total_exits"] += 1
            state["capital"] = _recalc_capital(state)
            sym_s = ct["symbol"].replace("/USDT:USDT", "")
            log(f"  EXIT  {sym_s} batch#{ct['batch_id']} "
                f"pnl={ct['pnl_pct']*100:+.2f}% ${ct['pnl_usdt']:+.2f} ({ct['exit_reason']})")

    # 2. Entries (second pass, after exits processed)
    trend_cache: dict = {}
    for i, row in latest.iterrows():
        sym = row["symbol"]
        price = float(row["close"])
        prob_l = float(probs_l[i])
        prob_s = float(probs_s[i]) if probs_s is not None else 0.0
        ts = row["timestamp"] if isinstance(row["timestamp"], pd.Timestamp) else latest_ts
        atr_pct = float(row.get("atr_pct", 0)) if "atr_pct" in row else None

        # SMC Layer ① — compute multi-timeframe trend direction for this symbol
        trend, trend_score, trend_breakdown = "chop", 0.0, {}
        if C.SMC_ENABLED:
            trend, trend_score, trend_breakdown = trend_state(df_cache, sym, latest_ts)
            trend_cache[sym] = {"trend": trend, "score": trend_score, "breakdown": trend_breakdown}

        _try_entry(state, sym, price, prob_l, prob_s, ts, atr_pct=atr_pct,
                   trend=trend, trend_breakdown=trend_breakdown)

    if C.SMC_ENABLED and trend_cache:
        log(f"SMC trends: " + "; ".join(
            f"{s.replace('/USDT:USDT','')}={v['trend']}" for s, v in trend_cache.items()
        )[:300])
        state.setdefault("smc", {}).setdefault("last_trends", {})
        for s, v in trend_cache.items():
            state["smc"]["last_trends"][s] = v
        state["smc"]["asof"] = latest_ts_str

    # Update & save
    state["capital"] = _recalc_capital(state)
    eq = _compute_equity(state)
    state["equity_curve"].append(eq)
    _save_state(state)
    _equity_log_line(state, eq)

    return df_cache


def _fill_factors(df: pd.DataFrame, factors: list[str]):
    """Fill NaN factors with group median (in-place)."""
    for col in factors:
        if col in df.columns:
            df[col] = df.groupby(["symbol", "timeframe"])[col].transform(
                lambda s: s.fillna(s.median())
            )


def _merge_into_cache(cache: pd.DataFrame, new_data: pd.DataFrame) -> pd.DataFrame:
    if cache.empty:
        return new_data
    combined = pd.concat([cache, new_data], ignore_index=True)
    combined = combined.drop_duplicates(subset=["symbol", "timeframe", "timestamp"], keep="last")
    combined = combined.sort_values(["symbol", "timeframe", "timestamp"]).reset_index(drop=True)
    # Trim to last FEATURE_WINDOW * 3 per (symbol, timeframe) — safe approach
    result = []
    for sym in combined["symbol"].unique():
        sym_data = combined[combined["symbol"] == sym]
        for tf in sym_data["timeframe"].unique():
            chunk = sym_data[sym_data["timeframe"] == tf].tail(FEATURE_WINDOW * 3)
            result.append(chunk)
    trimmed = pd.concat(result, ignore_index=True) if result else combined
    trimmed = trimmed.sort_values(["symbol", "timeframe", "timestamp"]).reset_index(drop=True)
    return trimmed


def _equity_log_line(state: dict, equity: float):
    line = json.dumps({
        "ts": datetime.now().isoformat(),
        "capital": round(state["capital"], 2),
        "equity": round(equity, 2),
        "positions": len(state["positions"]),
        "trades": len(state["trades"]),
    })
    with open(str(EQUITY_LOG), "a") as f:
        f.write(line + "\n")


# ─── CLI ───

def print_status():
    state = _load_state()
    eq = _compute_equity(state)
    ret = (eq / state["initial_capital"] - 1) * 100 if state["initial_capital"] > 0 else 0

    print(f"\n{'='*55}")
    print(f"Paper Trader Status — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*55}")
    print(f"  Initial Capital: ${state['initial_capital']:.2f}")
    print(f"  Current Capital: ${state['capital']:.2f}")
    print(f"  Equity (w/UPnL): ${eq:.2f}")
    print(f"  Return:          {ret:+.2f}%")
    print(f"  Open Positions:  {len(state['positions'])}")
    print(f"  Closed Trades:   {len(state['trades'])}")
    print(f"  Total Entries:   {state['total_entries']}")
    print(f"  Total Exits:     {state['total_exits']}")
    print(f"  Last Bar:        {state.get('last_bar_ts','N/A')}")

    if state["trades"]:
        wins = [t for t in state["trades"] if t.get("pnl_usdt", 0) > 0]
        losses = [t for t in state["trades"] if t.get("pnl_usdt", 0) <= 0]
        wr = len(wins) / len(state["trades"]) * 100 if state["trades"] else 0
        avg_w = np.mean([t["pnl_pct"] * 100 for t in wins]) if wins else 0
        avg_l = np.mean([t["pnl_pct"] * 100 for t in losses]) if losses else 0
        gw = sum(t.get("pnl_usdt", 0) for t in wins) if wins else 0
        gl = sum(abs(t.get("pnl_usdt", 0)) for t in losses) if losses else 0
        pf = gw / (gl + 1e-10) if losses else float("inf")
        print(f"  Win Rate:        {wr:.1f}%")
        print(f"  Avg Win:         {avg_w:+.2f}%")
        print(f"  Avg Loss:        {avg_l:+.2f}%")
        print(f"  Profit Factor:   {pf:.3f}")

    if state["positions"]:
        print(f"\n  {'Symbol':10s} {'Dir':6s} {'Entry':>10s} {'Size':>8s} {'Age':>5s} {'UPnL':>8s}")
        print(f"  {'-'*52}")
        for p in state["positions"]:
            sym_s = p["symbol"].replace("/USDT:USDT", "")
            px = state.get("last_price_by_sym", {}).get(p["symbol"], p["entry_price"])
            upnl = (px / p["entry_price"] - 1) * 100 * (1 if p["direction"] == "long" else -1)
            try:
                entry_ts = pd.Timestamp(p["entry_time"])
                age = (datetime.now() - entry_ts).total_seconds() / 3600
            except Exception:
                age = 0
            print(f"  {sym_s:10s} {p['direction']:6s} ${p['entry_price']:>8.2f} "
                  f"${p['batch_size']:>7.2f} {age:4.0f}h {upnl:>+7.2f}%")


if __name__ == "__main__":
    if "--status" in sys.argv or "-s" in sys.argv:
        print_status()
    elif "--reset" in sys.argv:
        if STATE_PATH.exists():
            STATE_PATH.unlink()
            log("State reset")
        if EQUITY_LOG.exists():
            EQUITY_LOG.unlink()
            log("Equity log reset")
    else:
        _main_loop()
