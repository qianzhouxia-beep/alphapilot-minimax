#!/usr/bin/env python3
"""Compare ICIR with new OR/POC factors vs baseline."""
import sys, warnings, json, time
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/ubuntu/alphapilot")
from datetime import datetime
import pandas as pd
import numpy as np

def log(m): print(f"[{datetime.now().strftime('%H:%M:%S')}] {m}", flush=True)

log("=" * 60)
log("Fabio-inspired factors test — OR + Volume Profile")
log("=" * 60)

from crypto.data import build_dataset
from crypto.features import compute_features, list_factors
from crypto.icir import run_icir_analysis
from crypto.config import MODEL_DIR, SYMBOLS, ICIR_TOP_K, MODEL_PARAMS

# 1. Fetch & feature
log("Fetching data...")
df = build_dataset(limit=2000, force_refresh=True)
log(f"Data: {len(df)} rows, {df['symbol'].nunique()} symbols")

log("Computing features (fwd=2)...")
df = compute_features(df, forward=2, threshold=0.01)
all_factors = list_factors()
log(f"All factors: {len(all_factors)}")

# 2. Show new factor ICIR
log("Running ICIR...")
icir = run_icir_analysis(df)
summary = icir["summary"]

# New factor names
new_factors = [f for f in all_factors if f.startswith("or_") or f.startswith(("poc_", "vwap_", "dist_vwap", "dist_poc", "in_poc"))]
print(f"\n{'='*70}")
print(f"NEW FACTORS ICIR ({len(new_factors)} factors)")
print(f"{'='*70}")
print(f"{'Factor':<28} {'|ICIR|':>8} {'ICIR':>8}  Rank")
rows = []
for f in new_factors:
    info = summary.get(f, {})
    rows.append((f, info.get("abs_icir", 0), info.get("icir", 0)))
rows.sort(key=lambda x: -x[1])
ranked = sorted(summary.items(), key=lambda x: -x[1].get("abs_icir", 0))
rank_of = {f: i + 1 for i, (f, _) in enumerate(ranked)}
for f, a, i in rows:
    print(f"{f:<28} {a:>8.4f} {i:>+8.4f}  #{rank_of.get(f, 999)}")

# 3. Train baseline (top-60 without new) vs augmented (top-60 with new)
log("\nPreparing training sets...")
targets = ["label_long"]
t_2h = df[df["timeframe"] == "2h"].dropna(subset=targets).copy().sort_values("timestamp")

base_factors = [f for f in all_factors if not (f.startswith("or_") or f.startswith(("poc_", "vwap_", "dist_vwap", "dist_poc", "in_poc")))]

def prep_train(t, factors):
    for col in factors:
        t[col] = t.groupby("symbol")[col].transform(lambda s: s.fillna(s.median()))
    dead = [c for c in factors if t[c].isna().any()]
    if dead:
        t = t.drop(columns=dead)
        factors = [c for c in factors if c not in dead]
    return t.dropna(subset=factors), factors

def icir_top(t, factors, k=60):
    ic = run_icir_analysis(t)
    ranked = sorted(ic["summary"].items(), key=lambda x: -x[1]["abs_icir"])
    return [f[0] for f in ranked[:k] if f[0] in t.columns]

def train_and_eval(t, factors, label="model"):
    from crypto.train import train_model
    split = int(len(t) * 0.8)
    train_set = t.iloc[:split]
    test_set = t.iloc[split:]
    lm = train_model(train_set, target="label_long", factors=factors,
                     hyperparams=MODEL_PARAMS,
                     model_path=str(MODEL_DIR / "model_long.ubj"))
    log(f"{label}: AUC={lm['auc']:.4f}, n_train={lm['n_train']}")
    return lm

# Baseline: ICIR on original 95 factors → top 60
log("\n--- Baseline (original factors, ICIR top-60) ---")
t_base = t_2h.copy()
t_base, base_factors = prep_train(t_base, base_factors)
base_top = icir_top(t_base, base_factors, 60)
log(f"Base top-60 selected, n={len(base_top)}")
lm_base = train_and_eval(t_base, base_top, "Baseline")

# Augmented: ICIR on all 107+ factors → top 60 (allow new ones in)
log("\n--- Augmented (all factors incl OR/POC, ICIR top-60) ---")
t_aug = t_2h.copy()
all_f = [f for f in all_factors]
t_aug, all_f = prep_train(t_aug, all_f)
aug_top = icir_top(t_aug, all_f, 60)
new_in = [f for f in aug_top if f.startswith("or_") or f.startswith(("poc_", "vwap_", "dist_vwap", "dist_poc", "in_poc"))]
log(f"Aug top-60 selected, n={len(aug_top)}, new factors in top-60: {len(new_in)} → {new_in}")
lm_aug = train_and_eval(t_aug, aug_top, "Augmented")

# 4. Grid backtests
log("\n--- Grid backtests ---")
from crypto.grid_backtest import grid_backtest, print_grid_result as pg

log("Grid: Baseline model + baseline factors")
gr_base = grid_backtest(df, factors=base_top, min_score=0.50,
                         per_signal_risk=0.10, entry_timeframe="2h",
                         use_atr_sizing=True, atr_risk_pct=0.002, atr_max_batch_pct=0.25)
pg(gr_base)

log("Grid: Augmented model + augmented factors")
gr_aug = grid_backtest(df, factors=aug_top, min_score=0.50,
                        per_signal_risk=0.10, entry_timeframe="2h",
                        use_atr_sizing=True, atr_risk_pct=0.002, atr_max_batch_pct=0.25)
pg(gr_aug)

# 5. Summary
print(f"\n{'='*80}")
print(f"{'Metric':<22} {'Baseline':>16} {'Augmented':>16}")
print("-" * 54)
for name, b, a in [
    ("AUC", f"{lm_base['auc']:.4f}", f"{lm_aug['auc']:.4f}"),
    ("Win Rate", f"{gr_base.win_rate:.1f}%", f"{gr_aug.win_rate:.1f}%"),
    ("Total Return", f"{gr_base.total_return:+.2f}%", f"{gr_aug.total_return:+.2f}%"),
    ("Sharpe", f"{gr_base.sharpe:.3f}", f"{gr_aug.sharpe:.3f}"),
    ("Max DD", f"{gr_base.max_drawdown:.2f}%", f"{gr_aug.max_drawdown:.2f}%"),
    ("Profit Factor", f"{gr_base.profit_factor:.3f}", f"{gr_aug.profit_factor:.3f}"),
    ("N Trades", str(gr_base.n_trades), str(gr_aug.n_trades)),
]:
    print(f"{name:<22} {b:>16} {a:>16}")
b_rdd = gr_base.total_return / abs(gr_base.max_drawdown) if gr_base.max_drawdown else 0
a_rdd = gr_aug.total_return / abs(gr_aug.max_drawdown) if gr_aug.max_drawdown else 0
print(f"{'ROI/DD Ratio':<22} {b_rdd:>15.2f}x {a_rdd:>15.2f}x")
print(f"{'='*80}")
