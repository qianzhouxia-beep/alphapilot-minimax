#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ICIR Factor Weighting Scorer
=============================
Replaces XGBoost ensemble with explicit ICIR-weighted factor alpha.

alpha = sum_i( w_i * zscore(factor_i) ),  w_i = ICIR_i / sum(ICIR)

Usage (in-memory batch):
  scorer = ICIRScorer()
  scorer.load()
  alphas = scorer.compute_alpha(factor_df)  # DataFrame: index=stocks, cols=factor_names

Integrated into pipeline via recommend.py:
  1. Parallel: build_features() for all stocks
  2. Batch: compute_alpha() cross-sectionally
  3. Result: ICIR alpha becomes the new score
"""
from __future__ import annotations

import json
import os
import time
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT = Path(os.environ.get("ALPHAPILOT_ROOT") or "/home/ubuntu/alphapilot")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent
os.chdir(str(ROOT))

# 27 positive-ICIR factors with ICIR > 0 from regime-weighted production run
# weight_i = ICIR_i / sum(ICIR)
DEFAULT_WEIGHTS_PATH = ROOT / "output" / "icir_prod" / "icir_weights.json"


class ICIRScorer:
    """ICIR-based factor weighting scorer — batch cross-sectional alpha."""

    def __init__(self, weights_path: str | Path | None = None):
        self.weights_path = Path(weights_path or DEFAULT_WEIGHTS_PATH)
        self.weights: list[dict] = []       # [{factor, icir, weight}, ...]
        self.factor_names: list[str] = []   # ordered list of factors with weights
        self.loaded = False
        self._vm25 = None

    # ── Loading ────────────────────────────────────────────

    def load(self) -> bool:
        """Load ICIR weights from JSON and initialise VM25Scorer for feature building."""
        try:
            data = json.loads(self.weights_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"  ICIRScorer: weights not found at {self.weights_path}: {e}", flush=True)
            return False

        scheme = data.get("regime_weighted") or data.get("equal_regime")
        if not scheme:
            print("  ICIRScorer: no valid weight scheme found", flush=True)
            return False

        self.weights = scheme.get("weights", [])
        self.factor_names = [w["factor"] for w in self.weights]
        print(f"  ICIRScorer: {len(self.weights)} factors loaded from {self.weights_path}", flush=True)
        self.loaded = True

        # Load VM25Scorer for feature building
        self._ensure_vm25()

        return True

    def _ensure_vm25(self):
        """Lazy-load VM25Scorer for feature building."""
        if self._vm25 is not None:
            return
        try:
            from vm25_scorer import VM25Scorer

            vm = VM25Scorer(prefer="opt")
            ok = vm.load()
            if ok:
                self._vm25 = vm
                print(f"  ICIRScorer: VM25Scorer loaded ({len(vm.feature_names)} features)", flush=True)
            else:
                print("  ICIRScorer: VM25Scorer load failed", flush=True)
        except Exception as e:
            print(f"  ICIRScorer: VM25Scorer import error: {e}", flush=True)

    # ── Feature building ───────────────────────────────────

    def build_stock_features(self, kline_df: pd.DataFrame, symbol: str) -> dict[str, float] | None:
        """Build VM2.5 features for a single stock and return the latest factor vector."""
        if self._vm25 is None:
            self._ensure_vm25()
        if self._vm25 is None:
            return None
        try:
            full = self._vm25.build_features(kline_df, symbol)
            if full is None or len(full) < 1:
                return None
            row = full.iloc[-1]
            return {c: float(row.get(c, 0.0) or 0.0) for c in self._vm25.feature_names}
        except Exception as e:
            return None

    def build_stock_features_and_meta(
        self, kline_df: pd.DataFrame, symbol: str,
    ) -> dict[str, Any] | None:
        """Build features + compute metadata (close, atr). Returns dict or None."""
        fv = self.build_stock_features(kline_df, symbol)
        if fv is None:
            return None
        try:
            close = float(kline_df.iloc[-1]["close"])
            atr_val = float(
                (kline_df["high"] - kline_df["low"]).rolling(14).mean().iloc[-1]
            )
            if close > 0 and atr_val > 0:
                t_pct = max(0.03, min(0.12, 1.5 * atr_val / close))
                s_pct = min(max(1.5 * atr_val / close, 0.02), 0.07)
            else:
                t_pct, s_pct = 0.04, 0.03
            target_price = round(close * (1.0 + t_pct), 2)
            stop_price = round(close * (1.0 - s_pct), 2)
            if target_price <= close:
                target_price = round(close * 1.04, 2)
            if stop_price >= close:
                stop_price = round(close * 0.97, 2)
        except Exception:
            close = 0.0
            target_price = 0.0
            stop_price = 0.0

        return {
            "factor_vec": fv,
            "close": close,
            "target_price": target_price,
            "stop_price": stop_price,
        }

    # ── Batch ICIR alpha ───────────────────────────────────

    def compute_alpha(self, factor_df: pd.DataFrame) -> np.ndarray:
        """Compute ICIR alpha for a batch of stocks.

        Args:
            factor_df: DataFrame, index=stock symbols, columns=factor names.
                       Values are raw factor values.

        Returns:
            Array of ICIR alpha values (same order as factor_df.index).
        """
        assert self.loaded, "ICIRScorer not loaded"
        alpha = np.zeros(len(factor_df), dtype=float)
        n_used = 0
        for w in self.weights:
            fn = w["factor"]
            if fn not in factor_df.columns:
                continue
            vals = factor_df[fn].values.astype(float)
            # Replace inf/nan
            vals = np.where(np.isfinite(vals), vals, 0.0)
            mu = np.mean(vals)
            sigma = np.std(vals) + 1e-12
            z = (vals - mu) / sigma
            alpha += z * w["weight"]
            n_used += 1
        if n_used == 0:
            print("  ICIRScorer: no matching factors in data — all alpha = 0", flush=True)
        return alpha

    def compute_alpha_from_batch(
        self, build_results: list[dict[str, Any]]
    ) -> np.ndarray:
        """Convenience: extract factor vectors from build results and compute alpha.

        Args:
            build_results: list of dicts from build_stock_features_and_meta()

        Returns:
            Array of ICIR alpha values matching the order of build_results.
        """
        valid = [(i, r) for i, r in enumerate(build_results) if r is not None]
        if not valid:
            return np.array([])
        symbols = [r["symbol"] for _, r in valid]
        # Build factor DataFrame
        rows = {}
        for fn in self.factor_names:
            rows[fn] = [r["factor_vec"].get(fn, 0.0) for _, r in valid]
        df = pd.DataFrame(rows, index=symbols)
        alphas = self.compute_alpha(df)
        # Map back to original order (return NaN for None entries)
        result = np.full(len(build_results), np.nan)
        for (i, _), a in zip(valid, alphas):
            result[i] = a
        return result


# ── Global singleton (for recommend.py) ────────────────────
_global_icir_scorer: ICIRScorer | None = None


def get_scorer() -> ICIRScorer:
    global _global_icir_scorer
    if _global_icir_scorer is None:
        _global_icir_scorer = ICIRScorer()
        _global_icir_scorer.load()
    return _global_icir_scorer


# ── Standalone test ────────────────────────────────────────
if __name__ == "__main__":
    print("Testing ICIRScorer...")
    s = get_scorer()
    print(f"  Loaded: {s.loaded}")
    print(f"  Factors: {s.factor_names[:5]}... ({len(s.factor_names)} total)")
    print(f"  Weights: {[round(w['weight'], 4) for w in s.weights[:5]]}...")
    # Demo: random factor values => compute alpha
    rng = np.random.default_rng(42)
    n_demo = 100
    demo_data = {fn: rng.normal(0, 1, n_demo) for fn in s.factor_names}
    demo_df = pd.DataFrame(demo_data, index=[f"demo_{i:04d}" for i in range(n_demo)])
    alphas = s.compute_alpha(demo_df)
    print(f"  Demo alpha: mean={np.mean(alphas):.4f} std={np.std(alphas):.4f}")
    print(f"  Range: [{np.min(alphas):.4f}, {np.max(alphas):.4f}]")
    print("  OK")
