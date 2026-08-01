"""Hyperparameter optimization + feature selection for crypto XGBoost.

Runs grid search over:
- label forward windows: [2, 4, 8]
- label thresholds: [0.01, 0.02, 0.03]
- feature subsets: all, top-20-ICIR, top-10-ICIR
- XGBoost params: max_depth [3,4,5,6], lr [0.03,0.05,0.08,0.12]
"""
from __future__ import annotations

import itertools
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .config import DATA_DIR, MODEL_DIR

_DEBUG = os.environ.get("DEBUG_OPTUNA") is not None


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ── Feature pipeline helpers ──
def _prepare_data(limit=2000, force_fetch=False):
    from .data import build_dataset

    df = build_dataset(limit=limit, force_refresh=force_fetch)
    return df


def _compute_and_label(df, forward, threshold):
    from .features import compute_features, list_factors

    df = compute_features(df, forward=forward, threshold=threshold)
    factors = list_factors()
    return df, factors


def _fill_and_filter(df, factors, top_n=None, icir_weights=None):
    """Fill NaN and optionally filter to top-N ICIR factors."""
    targets = ["label_long", "label_short"]
    t = df.dropna(subset=targets).copy().sort_values("timestamp")

    for col in factors:
        t[col] = t.groupby(["symbol", "timeframe"])[col].transform(
            lambda s: s.fillna(s.median())
        )

    # Drop dead factors (still all NaN)
    dead = [c for c in factors if t[c].isna().any()]
    if dead:
        t = t.drop(columns=dead)
        factors = [c for c in factors if c not in dead]

    # Filter to top-N by ICIR weights
    if top_n is not None and top_n > 0 and icir_weights:
        sorted_f = sorted(icir_weights.items(), key=lambda x: -abs(x[1]))
        keep = {f for f, _ in sorted_f[:top_n]}
        factors = [f for f in factors if f in keep]
        t = t[["timestamp", "symbol", "timeframe", "close"] + factors + targets]

    t = t.dropna(subset=factors)
    return t, factors


def _run_icir(df, factors) -> dict:
    """Quick ICIR calculation for feature selection."""
    from scipy.stats import spearmanr

    results = {}
    for tf in df["timeframe"].unique():
        tf_df = df[df["timeframe"] == tf]
        fwd = tf_df["fwd_ret"]
        n_periods = min(10, max(2, len(tf_df) // 100))
        period_size = len(tf_df) // n_periods

        for col in factors:
            ics = []
            for i in range(n_periods):
                lo, hi = i * period_size, (i + 1) * period_size
                seg = tf_df.iloc[lo:hi]
                valid = seg[col].notna() & seg["fwd_ret"].notna()
                if valid.sum() < 15:
                    continue
                corr, _ = spearmanr(seg[col][valid], seg["fwd_ret"][valid])
                if not np.isnan(corr):
                    ics.append(corr)
            ic_arr = np.array(ics)
            valid_ics = ic_arr[~np.isnan(ic_arr)]
            if len(valid_ics) < 2:
                continue
            ic_mean = float(np.mean(valid_ics))
            ic_std = float(np.std(valid_ics, ddof=1)) if len(valid_ics) > 1 else 1.0
            results.setdefault(col, []).append(ic_mean / (ic_std + 1e-10))

    weights = {}
    for col, icirs in results.items():
        weights[col] = abs(float(np.mean(icirs)))
    total = sum(weights.values()) + 1e-10
    return {k: v / total for k, v in weights.items()}


def _train_eval(train_df, test_df, factors, target, params) -> dict:
    """Train one model and return metrics."""
    import xgboost as xgb
    from sklearn.metrics import roc_auc_score

    X_tr = train_df[factors].values
    y_tr = train_df[target].values
    X_te = test_df[factors].values
    y_te = test_df[target].values

    pos_ratio = y_tr.mean()
    scale_pos = max(2.0, (1 - pos_ratio) / (pos_ratio + 1e-10))

    p = {
        "max_depth": 4,
        "learning_rate": 0.05,
        "subsample": 0.7,
        "colsample_bytree": 0.7,
        "scale_pos_weight": scale_pos,
        "tree_method": "hist",
        "objective": "binary:logistic",
        "eval_metric": "auc",
        "seed": 42,
    }
    p.update(params)

    dtrain = xgb.DMatrix(X_tr, label=y_tr)
    dtest = xgb.DMatrix(X_te, label=y_te)

    model = xgb.train(
        p,
        dtrain,
        num_boost_round=300,
        evals=[(dtrain, "train"), (dtest, "test")],
        early_stopping_rounds=30,
        verbose_eval=0 if _DEBUG else False,
    )

    y_pred = model.predict(dtest)
    auc = float(roc_auc_score(y_te, y_pred))

    # Also calc precision@top20% for signal quality
    sorted_idx = np.argsort(-y_pred)
    top_k = max(1, len(y_pred) // 5)
    top_precision = float(y_te[sorted_idx[:top_k]].mean())

    return {"auc": auc, "top_precision": top_precision, "n_train": len(X_tr), "n_test": len(X_te), "pos_ratio": float(pos_ratio)}


def run_grid_search(
    force_fetch=False,
    limit=2000,
    test_ratio=0.2,
):
    """Run grid search over label configs + feature subsets + XGBoost params."""
    results = []

    # 1. Fetch data once
    df = _prepare_data(limit=limit, force_fetch=force_fetch)
    log(f"Data: {len(df)} rows")

    # Label configs
    label_configs = [
        {"forward": 2, "threshold": 0.01, "label": "label_long"},
        {"forward": 2, "threshold": 0.01, "label": "label_short"},
        {"forward": 4, "threshold": 0.02, "label": "label_long"},
        {"forward": 4, "threshold": 0.02, "label": "label_short"},
        {"forward": 8, "threshold": 0.03, "label": "label_long"},
        {"forward": 8, "threshold": 0.03, "label": "label_short"},
    ]
    # XGBoost variants
    xgb_grid = [
        {"max_depth": 3, "learning_rate": 0.05, "subsample": 0.6, "colsample_bytree": 0.6},
        {"max_depth": 4, "learning_rate": 0.05, "subsample": 0.7, "colsample_bytree": 0.7},
        {"max_depth": 5, "learning_rate": 0.03, "subsample": 0.8, "colsample_bytree": 0.6},
        {"max_depth": 6, "learning_rate": 0.03, "subsample": 0.7, "colsample_bytree": 0.7},
        {"max_depth": 4, "learning_rate": 0.08, "subsample": 0.6, "colsample_bytree": 0.6},
        {"max_depth": 3, "learning_rate": 0.12, "subsample": 0.8, "colsample_bytree": 0.8},
    ]

    # 2. Compute features for each label config
    log("Computing features for all label configs...")
    feature_cache = {}
    for lc in label_configs:
        key = (lc["forward"], lc["threshold"])
        if key not in feature_cache:
            fdf, factors = _compute_and_label(df, lc["forward"], lc["threshold"])
            feature_cache[key] = (fdf, factors)
            log(f"  forward={lc['forward']} threshold={lc['threshold']} → {len(factors)} factors")

    total_trials = len(label_configs) * len(xgb_grid)
    trial = 0

    for lc in label_configs:
        fdf, all_factors = feature_cache[(lc["forward"], lc["threshold"])]
        target = lc["label"]

        # ICIR weights for feature selection
        icir_w = _run_icir(fdf, all_factors)
        top20_factors = sorted(icir_w, key=lambda x: -abs(icir_w[x]))[:20]
        top10_factors = top20_factors[:10]

        feature_subsets = {
            "all": all_factors,
            "top20": top20_factors,
            "top10": top10_factors,
        }

        for fset_name, fset in feature_subsets.items():
            # Prepare filled+filtered data
            t, factors_used = _fill_and_filter(fdf, all_factors, top_n=None)  # fill all first
            # Then filter to subset
            keep = [c for c in fset if c in t.columns]
            factors_used = keep
            t = t[["timestamp", "symbol", "timeframe", "close"] + keep + [target]].dropna(subset=keep)

            if len(t) < 200:
                log(f"  SKIP {lc['forward']}/{lc['threshold']}/{fset_name}: only {len(t)} rows")
                continue

            # Time split
            split_idx = int(len(t) * (1 - test_ratio))
            train_set = t.iloc[:split_idx]
            test_set = t.iloc[split_idx:]

            if len(train_set) < 50 or len(test_set) < 20:
                continue

            for xgb_params in xgb_grid:
                trial += 1
                log(f"Trial {trial}/{total_trials}: fwd={lc['forward']} thr={lc['threshold']} "
                    f"feat={fset_name}({len(factors_used)}) "
                    f"md={xgb_params['max_depth']} lr={xgb_params['learning_rate']}")

                try:
                    metrics = _train_eval(train_set, test_set, factors_used, target, xgb_params)
                    row = {
                        "forward": lc["forward"],
                        "threshold": lc["threshold"],
                        "target": target,
                        "feature_set": fset_name,
                        "n_features": len(factors_used),
                        **xgb_params,
                        **metrics,
                    }
                    results.append(row)
                    log(f"  → AUC={metrics['auc']:.4f} prec@20%={metrics['top_precision']:.4f}")
                except Exception as e:
                    log(f"  → FAILED: {e}")

    # 5. Save results
    report = {
        "asof": datetime.now().isoformat(),
        "n_trials": len(results),
        "best_by_auc": sorted(results, key=lambda x: -x["auc"])[:10],
        "best_by_precision": sorted(results, key=lambda x: -x["top_precision"])[:10],
        "all_results": results,
    }

    out_path = MODEL_DIR / "grid_search.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Grid search results saved: {out_path}")
    return report


def train_best_config(report, force_fetch=False):
    """Train the best config found by grid search."""
    if not report.get("best_by_auc"):
        log("No best config found")
        return

    best = report["best_by_auc"][0]
    log(f"Training best config: fwd={best['forward']} thr={best['threshold']} "
        f"feat={best['feature_set']} md={best['max_depth']} lr={best['learning_rate']}")

    from .train import train_model

    from .data import build_dataset
    from .features import compute_features, list_factors

    df = build_dataset(limit=2000, force_refresh=force_fetch)
    df = compute_features(df, forward=best["forward"], threshold=best["threshold"])
    all_factors = list_factors()

    # Filter to top-N
    icir_w = _run_icir(df, all_factors)
    top_n = 20 if best["feature_set"] == "top20" else (10 if best["feature_set"] == "top10" else len(all_factors))
    sorted_f = sorted(icir_w, key=lambda x: -abs(icir_w[x]))
    keep = {f for f, _ in sorted_f[:top_n]} if top_n < len(all_factors) else set(all_factors)
    factors = [f for f in all_factors if f in keep]

    # Prepare
    targets = ["label_long", "label_short"]
    t = df.dropna(subset=targets).copy().sort_values("timestamp")
    for col in factors:
        t[col] = t.groupby(["symbol", "timeframe"])[col].transform(lambda s: s.fillna(s.median()))
    dead = [c for c in factors if t[c].isna().any()]
    if dead:
        t = t.drop(columns=dead)
        factors = [c for c in factors if c not in dead]
    t = t.dropna(subset=factors)

    xgb_params = {k: best[k] for k in ["max_depth", "learning_rate", "subsample", "colsample_bytree"]}
    long_m = train_model(t, target="label_long", factors=factors, hyperparams=xgb_params)
    short_m = train_model(t, target="label_short", factors=factors, hyperparams=xgb_params)

    return long_m, short_m


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)

    os.environ["HTTP_PROXY"] = "http://127.0.0.1:7890"
    os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7890"

    report = run_grid_search(force_fetch=False)
    print(f"\n=== Best 5 by AUC ===")
    for r in report["best_by_auc"][:5]:
        print(f"  AUC={r['auc']:.4f} fwd={r['forward']} thr={r['threshold']} "
              f"feat={r['feature_set']}({r['n_features']}) "
              f"md={r['max_depth']} lr={r['learning_rate']} "
              f"prec@20={r['top_precision']:.4f}")
