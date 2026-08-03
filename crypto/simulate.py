"""Crypto paper simulation — periodic signal generation.

Runs every N hours via cron, outputs signal.json with trade recommendations.

Usage:
    python -m crypto.simulate                  # full cycle
    python -m crypto.simulate --fetch           # force data refresh
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .config import (
    MODEL_DIR,
    SIGNAL_PATH,
    SYMBOLS,
    TIMEFRAMES,
    PRIMARY_TF,
    PAPER,
    USE_SHORT_MODEL,
)

_models: dict = {}

def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _load_model(target: str) -> object:
    import xgboost as xgb

    key = f"model_{target}"
    if key not in _models:
        path = MODEL_DIR / f"model_{target}.ubj"
        if not path.exists():
            raise FileNotFoundError(f"Train model first: {path}")
        _models[key] = xgb.Booster()
        _models[key].load_model(str(path))
    return _models[key]


def run_simulation(force_fetch: bool = False) -> dict:
    """Fetch latest data → features → predict → output signal.json."""
    from .data import build_dataset
    from .features import compute_features, list_factors
    from .config import ICIR_TOP_K, ICIR_PATH

    # 1. Data (last 500 bars is enough for inference)
    df = build_dataset(limit=500, force_refresh=force_fetch)
    log(f"Data: {len(df)} rows")

    # 2. Features
    df = compute_features(df, forward=None, threshold=None)  # no labels needed for inference
    all_factors = list_factors()
    log(f"Features: {len(all_factors)} factors")

    # 3. Use ICIR-selected factors (must match training)
    if ICIR_PATH.exists():
        with open(ICIR_PATH) as f:
            icir_data = json.load(f)
        ranked = sorted(icir_data.get("summary", {}).items(), key=lambda x: -x[1]["abs_icir"])
        top = [f[0] for f in ranked[:ICIR_TOP_K]]
        factors = [f for f in top if f in df.columns]
        log(f"Using ICIR top-{len(factors)} factors ({ICIR_PATH.name})")
    else:
        factors = all_factors
        log("ICIR weights not found, using all factors")

    # 4. Fill NaN
    for col in factors:
        df[col] = df.groupby(["symbol", "timeframe"])[col].transform(
            lambda s: s.fillna(s.median())
        )
    df = df.dropna(subset=factors)

    # 4. Predict
    try:
        model_l = _load_model("long")
        model_s = _load_model("short") if USE_SHORT_MODEL else None
    except FileNotFoundError as e:
        log(f"ERROR: {e}")
        return {"error": str(e), "status": "no_model"}

    import xgboost as xgb

    # Use 2h data for entry signal timing (model trained on 2h labels, fwd=2)
    latest = df[df["timeframe"] == "2h"].groupby("symbol").last().reset_index()
    X = latest[factors].values
    dmat = xgb.DMatrix(X)

    latest["prob_long"] = model_l.predict(dmat)
    latest["prob_short"] = model_s.predict(dmat) if model_s is not None else 0.0

    # 5. Build signals
    signals = []
    for _, row in latest.iterrows():
        sym = row["symbol"]
        tf = row["timeframe"]
        price = row["close"]
        ts = row["timestamp"].isoformat() if hasattr(row["timestamp"], "isoformat") else str(row["timestamp"])

        prob_l = float(row["prob_long"])
        prob_s = float(row["prob_short"])

        action = "hold"
        direction = None
        confidence = 0.0

        if prob_l > PAPER.min_signal_score and prob_l > prob_s:
            action = "enter_long"
            direction = "long"
            confidence = round(prob_l, 4)
        elif prob_s > PAPER.min_signal_score_short and prob_s > prob_l:
            action = "enter_short"
            direction = "short"
            confidence = round(prob_s, 4)

        if action != "hold":
            signals.append({
                "symbol": sym,
                "timeframe": tf,
                "price": round(price, 2),
                "timestamp": ts,
                "action": action,
                "direction": direction,
                "confidence": confidence,
                "prob_long": round(prob_l, 4),
                "prob_short": round(prob_s, 4),
                "position_size_pct": PAPER.per_trade_risk * 100,
            })

    # 6. Build output
    output = {
        "asof": datetime.now().isoformat(),
        "symbols": SYMBOLS,
        "timeframe": PRIMARY_TF,
        "n_signals": len(signals),
        "capital_usdt": PAPER.initial_capital,
        "max_positions": PAPER.max_positions,
        "min_signal_score": PAPER.min_signal_score,
        "signals": signals,
        "status": "ok",
    }

    SIGNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    SIGNAL_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Signals: {len(signals)} — {SIGNAL_PATH}")
    return output


def print_signals(output: dict) -> None:
    print(f"\n{'='*50}")
    print(f"Crypto Paper Signals — {output['asof']}")
    print(f"{'='*50}")
    if output.get("status") != "ok":
        print(f"  Status: {output['status']}")
        return
    for s in output["signals"]:
        sym = s["symbol"].replace("/USDT:USDT", "")
        print(f"  {sym:10s} {s['action']:12s} conf={s['confidence']:.2f} @ {s['price']:.2f}")
    print(f"\n  Total signals: {output['n_signals']}")
    print(f"  Capital: ${output['capital_usdt']:.0f} USDT")


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)
    force = "--fetch" in sys.argv or "-f" in sys.argv
    result = run_simulation(force_fetch=force)
    print_signals(result)
