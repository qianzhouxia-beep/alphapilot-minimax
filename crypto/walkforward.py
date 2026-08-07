"""Walk-forward OOS validation — the anti-overfitting guardrail.

Every daily retrain produces a fresh model. Before it replaces the live one,
we validate it with rolling walk-forward: split history into chronological
folds; for each fold train on everything before it and predict the fold out of
sample; accumulate OOS predictions → OOS AUC. If OOS AUC falls below the floor,
the guardrail rejects the new model and sg_pipeline rolls back to the previous
one, so a regime-change/blow-up model never reaches the live trader.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .config import MODEL_DIR, N_BOOST, EARLY_STOP, SCALE_POS_WEIGHT

OOS_AUC_FLOOR = 0.52   # below this, reject the retrained model


def run_walkforward(
    df: pd.DataFrame,
    factors: list[str],
    target: str = "label_long",
    hyperparams: dict | None = None,
    n_folds: int = 4,
    min_train: int = 500,
) -> dict:
    """Rolling walk-forward OOS AUC on a feature-computed dataframe.

    Args:
        df: feature-computed data (with label_* and factors).
        factors: feature columns.
        target: 'label_long' or 'label_short'.
        n_folds: number of chronological validation folds.
    Returns:
        {"oos_auc", "per_fold": [...], "n_oos", "asof"}
    """
    import xgboost as xgb
    from sklearn.metrics import roc_auc_score

    df = df.dropna(subset=factors + [target]).sort_values("timestamp").reset_index(drop=True)
    if len(df) < min_train * 2:
        return {"oos_auc": 0.5, "per_fold": [], "n_oos": 0, "note": "insufficient data",
                "asof": datetime.now().isoformat()}

    fold_size = len(df) // n_folds
    preds, labels = [], []
    per_fold = []

    for i in range(n_folds):
        test_lo = i * fold_size
        test_hi = len(df) if i == n_folds - 1 else (i + 1) * fold_size
        train_df = df.iloc[:test_lo]
        test_df = df.iloc[test_lo:test_hi]
        if len(train_df) < min_train or len(test_df) < 50:
            continue

        y_train = train_df[target].values
        y_test = test_df[target].values
        if len(set(y_test)) < 2:
            continue

        pos_ratio = y_train.mean()
        params = {
            "max_depth": hyperparams.get("max_depth", 4) if hyperparams else 4,
            "learning_rate": hyperparams.get("learning_rate", 0.08) if hyperparams else 0.08,
            "subsample": hyperparams.get("subsample", 0.6) if hyperparams else 0.6,
            "colsample_bytree": hyperparams.get("colsample_bytree", 0.6) if hyperparams else 0.6,
            "scale_pos_weight": max(SCALE_POS_WEIGHT, (1 - pos_ratio) / (pos_ratio + 1e-10)),
            "tree_method": "hist",
            "objective": "binary:logistic",
            "eval_metric": "auc",
            "seed": 42,
        }

        dtrain = xgb.DMatrix(train_df[factors].values, label=y_train)
        dtest = xgb.DMatrix(test_df[factors].values, label=y_test)
        model = xgb.train(params, dtrain, num_boost_round=N_BOOST,
                          evals=[(dtest, "test")], early_stopping_rounds=EARLY_STOP,
                          verbose_eval=False)
        p = model.predict(dtest)
        preds.extend(p.tolist())
        labels.extend(y_test.tolist())
        per_fold.append({
            "fold": i + 1,
            "auc": round(float(roc_auc_score(y_test, p)), 4),
            "n_train": int(len(train_df)), "n_test": int(len(test_df)),
        })

    if len(preds) < 50 or len(set(labels)) < 2:
        return {"oos_auc": 0.5, "per_fold": per_fold, "n_oos": len(preds),
                "note": "too few valid folds", "asof": datetime.now().isoformat()}

    return {
        "oos_auc": round(float(roc_auc_score(labels, preds)), 4),
        "per_fold": per_fold,
        "n_oos": len(preds),
        "asof": datetime.now().isoformat(),
    }


def check_guardrail(wf_result: dict) -> dict:
    """Decision: accept or reject the retrained model based on OOS AUC."""
    oos_auc = float(wf_result.get("oos_auc", 0.5))
    passed = oos_auc >= OOS_AUC_FLOOR and wf_result.get("n_oos", 0) >= 50
    return {
        "pass": passed,
        "oos_auc": oos_auc,
        "floor": OOS_AUC_FLOOR,
        "n_oos": wf_result.get("n_oos", 0),
        "decision": "accept" if passed else "reject",
    }


def append_guardrail_history(guard: dict, target: str):
    path = MODEL_DIR / "guardrail_history.jsonl"
    with open(str(path), "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "target": target,
            "oos_auc": guard.get("oos_auc"),
            "decision": guard.get("decision"),
        }) + "\n")


if __name__ == "__main__":
    # Quick self-test against cached data
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from crypto.data import build_dataset
    from crypto.features import compute_features, list_factors

    df = build_dataset(limit=2000, force_refresh=False)
    df = compute_features(df, forward=2, threshold=0.01)
    factors = list_factors()[:60]
    df = df[df["timeframe"] == "2h"].dropna(subset=factors + ["label_long"])
    wf = run_walkforward(df, factors, "label_long", n_folds=4)
    print(json.dumps(wf, indent=2))
    print("guardrail:", check_guardrail(wf))
