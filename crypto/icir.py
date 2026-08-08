"""ICIR factor analysis — adapted from icir_scorer.py for crypto."""
from __future__ import annotations

import json
from datetime import datetime

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from .config import ICIR_PATH, TRAIN_TEST_SPLIT
from .features import compute_features, list_factors


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def compute_ic(series: pd.Series, fwd_ret: pd.Series) -> float:
    """Rank IC (Spearman correlation) between factor value and forward return."""
    valid = series.notna() & fwd_ret.notna()
    if valid.sum() < 20:
        return 0.0
    corr, _ = spearmanr(series[valid], fwd_ret[valid])
    return float(corr) if not np.isnan(corr) else 0.0


def run_icir_analysis(
    df: pd.DataFrame,
    min_samples: int = 30,
) -> dict:
    """Run ICIR analysis across all factors and time regimes.

    Returns:
        {factor_name: {ic_mean, ic_std, icir, ic_half_life, ...}}
    """
    df = df.copy()
    # Hard-exclude any look-ahead / label-ish columns (defense in depth).
    _hard_exclude = {
        "timestamp", "symbol", "timeframe", "open", "high", "low", "close", "volume",
        "funding_rate", "open_interest", "oi_value_usdt",
        "label_long", "label_short", "label_mid", "label_multiclass", "fwd_ret",
    }
    factors = [c for c in df.columns if c not in _hard_exclude
               and "fwd_ret" not in c
               and df[c].dtype in ("float64", "float32", "int64")]
    
    # group by timeframe for separate analysis
    results = {}
    for tf in df["timeframe"].unique():
        tf_df = df[df["timeframe"] == tf].copy()
        fwd = tf_df["fwd_ret"]

        ics = {}
        for col in factors:
            ic_series = []
            # Split into ~10 equal periods for IC time series
            n_periods = min(10, max(1, len(tf_df) // min_samples))
            if n_periods < 2:
                continue
            period_size = len(tf_df) // n_periods
            for i in range(n_periods):
                lo, hi = i * period_size, (i + 1) * period_size
                seg = tf_df.iloc[lo:hi]
                ic_val = compute_ic(seg[col], seg["fwd_ret"])
                ic_series.append(ic_val)

            ic_arr = np.array(ic_series)
            valid_ics = ic_arr[~np.isnan(ic_arr)]
            if len(valid_ics) < 2:
                continue
            
            ic_mean = float(np.mean(valid_ics))
            ic_std = float(np.std(valid_ics, ddof=1)) if len(valid_ics) > 1 else 1.0
            icir_val = ic_mean / (ic_std + 1e-10)
            ics[col] = {
                "ic_mean": round(ic_mean, 6),
                "ic_std": round(ic_std, 6),
                "icir": round(icir_val, 4),
                "n_periods": len(valid_ics),
            }

        if ics:
            results[tf] = ics

    # Aggregate: rank by average |ICIR| across timeframes
    summary = {}
    for col in factors:
        tfs_icir = [(tf, results[tf].get(col, {}).get("icir", 0)) for tf in results]
        tfs_ic = [(tf, results[tf].get(col, {}).get("ic_mean", 0)) for tf in results]
        avg_icir = float(np.mean([abs(v) for _, v in tfs_icir])) if tfs_icir else 0
        avg_ic = float(np.mean([v for _, v in tfs_ic])) if tfs_ic else 0
        summary[col] = {
            "ic_mean": round(avg_ic, 6),
            "abs_icir": round(avg_icir, 4),
            "per_tf": {tf: results.get(tf, {}).get(col, {}) for tf in results},
        }

    # Build weight map
    ranked = sorted(summary.items(), key=lambda x: -x[1]["abs_icir"])
    total_icir = sum(max(r["abs_icir"], 0.01) for _, r in ranked)
    weights = {}
    for col, r in ranked:
        weights[col] = round(max(r["abs_icir"], 0.01) / total_icir, 6)

    out = {
        "asof": datetime.now().isoformat(),
        "n_factors": len(summary),
        "n_timeframes": list(results.keys()),
        "top_factors": [{"factor": col, "ic_mean": r["ic_mean"], "abs_icir": r["abs_icir"]}
                         for col, r in ranked[:20]],
        "summary": summary,
        "weights": weights,
    }

    ICIR_PATH.parent.mkdir(parents=True, exist_ok=True)
    ICIR_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"ICIR analysis saved: {ICIR_PATH}")
    return out


def run_icir_pipeline(force_fetch: bool = False) -> dict:
    """End-to-end: fetch data → compute features → run ICIR."""
    from .data import build_dataset

    df = build_dataset(force_refresh=force_fetch)
    log(f"Computing features on {len(df)} rows...")
    df = compute_features(df, forward=4, threshold=0.02)
    log(f"Factors: {len(list_factors())}")
    result = run_icir_analysis(df)
    return result


if __name__ == "__main__":
    result = run_icir_pipeline()
    print("\nTop 10 factors by |ICIR|:")
    for f in result["top_factors"][:10]:
        print(f"  {f['factor']:30s}  IC={f['ic_mean']:+.6f}  |ICIR|={f['abs_icir']:.4f}")
