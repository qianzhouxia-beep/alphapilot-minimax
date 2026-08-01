"""XGBoost training pipeline — adapted from train_v25.py for crypto."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from .features import compute_features, list_factors


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def train_model(
    df: pd.DataFrame,
    target: str = "label_long",
    test_ratio: float = 0.2,
    hyperparams: dict | None = None,
    factors: list[str] | None = None,
    model_path=None,
) -> dict:
    """Train XGBoost model on feature-engineered crypto data.

    Args:
        df: data with features already computed
        target: 'label_long' or 'label_short'
        factors: feature column names (auto-detected if None)
        model_path: save path (auto-generated if None)
    Returns:
        {metrics dict}
    """
    import xgboost as xgb
    from sklearn.metrics import roc_auc_score

    if factors is None:
        from .features import list_factors as _lf
        factors = _lf()
    if not factors:
        raise ValueError("No factors found — run compute_features first")

    df = df.dropna(subset=factors + [target]).copy()
    log(f"Training samples: {len(df)} ({target})")

    # Time-based split (respect chronological order within each timeframe)
    df = df.sort_values("timestamp")
    split_idx = int(len(df) * (1 - test_ratio))

    train_df = df.iloc[:split_idx]
    test_df = df.iloc[split_idx:]

    X_train = train_df[factors].values
    y_train = train_df[target].values
    X_test = test_df[factors].values
    y_test = test_df[target].values

    pos_ratio = y_train.mean()
    log(f"Positive ratio: train={pos_ratio:.4f}  test={y_test.mean():.4f}")

    params = {
        "max_depth": C.MODEL_PARAMS.get("max_depth", 4),
        "learning_rate": C.MODEL_PARAMS.get("learning_rate", 0.08),
        "subsample": C.MODEL_PARAMS.get("subsample", 0.6),
        "colsample_bytree": C.MODEL_PARAMS.get("colsample_bytree", 0.6),
        "scale_pos_weight": max(C.SCALE_POS_WEIGHT, (1 - pos_ratio) / (pos_ratio + 1e-10)),
        "tree_method": "hist",
        "objective": "binary:logistic",
        "eval_metric": "auc",
        "seed": 42,
    }
    if hyperparams:
        params.update(hyperparams)

    dtrain = xgb.DMatrix(X_train, label=y_train)
    dtest = xgb.DMatrix(X_test, label=y_test)

    model = xgb.train(
        params,
        dtrain,
        num_boost_round=C.N_BOOST,
        evals=[(dtrain, "train"), (dtest, "test")],
        early_stopping_rounds=C.EARLY_STOP,
        verbose_eval=50,
    )

    # Predict and evaluate
    y_pred = model.predict(dtest)
    auc = float(roc_auc_score(y_test, y_pred))
    log(f"Test AUC: {auc:.4f}")

    # Save model
    save_path = Path(model_path) if model_path else C.MODEL_PATH
    save_path.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(str(save_path))
    log(f"Model saved: {save_path}")

    # Feature importance
    importance = model.get_score(importance_type="gain")
    sorted_imp = sorted(importance.items(), key=lambda x: -x[1])
    top_f = sorted_imp[:20]
    log("Top 20 features by gain:")
    for f, g in top_f:
        log(f"  {f:30s} {g:.4f}")

    metrics = {
        "auc": auc,
        "n_train": len(X_train),
        "n_test": len(X_test),
        "pos_ratio_train": float(pos_ratio),
        "pos_ratio_test": float(y_test.mean()),
        "n_features": len(factors),
        "params": params,
    }

    # Save metrics
    meta_path = save_path.with_suffix(".json")
    meta_path.write_text(
        json.dumps({**metrics, "top_features": top_f}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return metrics


def train_both_targets(df: pd.DataFrame) -> dict:
    """Train models. Short model only trained if USE_SHORT_MODEL=True."""
    from .config import USE_SHORT_MODEL
    long_path = C.MODEL_PATH.with_name(C.MODEL_PATH.stem + "_long" + C.MODEL_PATH.suffix)
    long_metrics = train_model(df, target="label_long", model_path=str(long_path))
    result = {"long": long_metrics}

    if USE_SHORT_MODEL:
        short_path = C.MODEL_PATH.with_name(C.MODEL_PATH.stem + "_short" + C.MODEL_PATH.suffix)
        short_metrics = train_model(df, target="label_short", model_path=str(short_path))
        result["short"] = short_metrics
    else:
        result["short"] = {"note": "disabled — USE_SHORT_MODEL=False"}
    return result


def run_training_pipeline(force_fetch: bool = False) -> dict:
    """End-to-end: fetch → features → train."""
    from .data import build_dataset

    df = build_dataset(force_refresh=force_fetch)
    log(f"Data loaded: {len(df)} rows")
    df = compute_features(df, forward=4, threshold=0.02)
    log(f"Features computed: {len(list_factors())} factors")
    return train_both_targets(df)


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)
    metrics = run_training_pipeline()
    print("\n=== Training Complete ===")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
