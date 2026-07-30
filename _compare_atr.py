#!/usr/bin/env python3
"""Compare fixed grid vs ATR-adaptive grid sizing on the same dataset."""
import sys, warnings, json, time
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/ubuntu/alphapilot")
from datetime import datetime
import pandas as pd
import numpy as np

def log(m): print(f"[{datetime.now().strftime('%H:%M:%S')}] {m}", flush=True)

log("=" * 60)
log("Grid Sizing Comparison — Fixed vs ATR-Adaptive")
log("=" * 60)

from crypto.data import build_dataset
from crypto.features import compute_features, list_factors
from crypto.icir import run_icir_analysis
from crypto.config import MODEL_DIR, SYMBOLS, ICIR_TOP_K, MODEL_PARAMS
from crypto.train import train_model

# 1. Fetch & feature
log("Fetching data...")
df = build_dataset(limit=2000, force_refresh=True)
log(f"Data: {len(df)} rows, {df['symbol'].nunique()} symbols")

log("Computing features (fwd=2)...")
df = compute_features(df, forward=2, threshold=0.01)
all_factors = list_factors()
log(f"All factors: {len(all_factors)}")

# 2. ICIR
log("Running ICIR...")
icir = run_icir_analysis(df)
ranked = sorted(icir["summary"].items(), key=lambda x: -x[1]["abs_icir"])
top_factors = [f[0] for f in ranked[:ICIR_TOP_K]]
factors = [f for f in top_factors if f in df.columns]
log(f"Selected {len(factors)} factors")

# 3. Train
targets = ["label_long"]
t_2h = df[df["timeframe"] == "2h"].dropna(subset=targets).copy().sort_values("timestamp")
for col in factors:
    t_2h[col] = t_2h.groupby("symbol")[col].transform(lambda s: s.fillna(s.median()))
dead = [c for c in factors if t_2h[c].isna().any()]
if dead:
    t_2h = t_2h.drop(columns=dead)
    factors = [c for c in factors if c not in dead]
t_2h = t_2h.dropna(subset=factors)
log(f"Training (2h): {len(t_2h)} rows, {len(factors)} factors")

split = int(len(t_2h) * 0.8)
train_set = t_2h.iloc[:split]
lm = train_model(train_set, target="label_long", factors=factors,
                 hyperparams=MODEL_PARAMS,
                 model_path=str(MODEL_DIR / "model_long.ubj"))
log(f"Long AUC: {lm['auc']:.4f}")

# 4. Backtest: Fixed 10% risk
log("\n" + "=" * 60)
log("Backtest: Fixed 10% risk per signal")
from crypto.grid_backtest import grid_backtest, print_grid_result as pg
gr_fixed = grid_backtest(df, factors=factors, min_score=0.50,
                          per_signal_risk=0.10, entry_timeframe="2h",
                          use_atr_sizing=False)
pg(gr_fixed)

# 5. Backtest: ATR-adaptive (0.2% per ATR unit)
log("\n" + "=" * 60)
log("Backtest: ATR-adaptive (atr_risk_pct=0.002)")
gr_atr = grid_backtest(df, factors=factors, min_score=0.50,
                        per_signal_risk=0.10, entry_timeframe="2h",
                        use_atr_sizing=True, atr_risk_pct=0.002, atr_max_batch_pct=0.25)
pg(gr_atr)

# 6. Sweep atr_risk_pct for best value
log("\n" + "=" * 60)
log("Sweep: atr_risk_pct from 0.001 to 0.005")
sweep_results = []
for rp in [0.001, 0.0015, 0.002, 0.0025, 0.003, 0.004, 0.005]:
    gr = grid_backtest(df, factors=factors, min_score=0.50,
                        per_signal_risk=0.10, entry_timeframe="2h",
                        use_atr_sizing=True, atr_risk_pct=rp, atr_max_batch_pct=0.25)
    sweep_results.append((rp, gr))
    log(f"  atr_risk_pct={rp:.4f}: return={gr.total_return:+.2f}%  sharpe={gr.sharpe:.3f}  "
        f"max_dd={gr.max_drawdown:.2f}%  n_trades={gr.n_trades}")

# 7. Summary comparison
print(f"\n{'='*80}")
print(f"{'Metric':<25} {'Fixed 10%':>15} {'ATR 0.2%':>15}")
print("-" * 55)
metrics = [
    ("Win Rate", f"{gr_fixed.win_rate:.1f}%", f"{gr_atr.win_rate:.1f}%"),
    ("Total Return", f"{gr_fixed.total_return:+.2f}%", f"{gr_atr.total_return:+.2f}%"),
    ("Sharpe", f"{gr_fixed.sharpe:.3f}", f"{gr_atr.sharpe:.3f}"),
    ("Max DD", f"{gr_fixed.max_drawdown:.2f}%", f"{gr_atr.max_drawdown:.2f}%"),
    ("Profit Factor", f"{gr_fixed.profit_factor:.3f}", f"{gr_atr.profit_factor:.3f}"),
    ("N Trades", str(gr_fixed.n_trades), str(gr_atr.n_trades)),
    ("Avg Hold (h)", f"{gr_fixed.avg_hold_hours:.1f}", f"{gr_atr.avg_hold_hours:.1f}"),
    ("End Value", f"${1000*(1+gr_fixed.total_return/100):.2f}",
                  f"${1000*(1+gr_atr.total_return/100):.2f}"),
]
for name, f, a in metrics:
    print(f"{name:<25} {f:>15} {a:>15}")

# ROI/DD
f_rdd = gr_fixed.total_return / abs(gr_fixed.max_drawdown) if gr_fixed.max_drawdown != 0 else float('inf')
a_rdd = gr_atr.total_return / abs(gr_atr.max_drawdown) if gr_atr.max_drawdown != 0 else float('inf')
print(f"\n{'ROI/DD Ratio':<25} {f_rdd:>14.2f}x {a_rdd:>14.2f}x")
print(f"{'='*80}")

# Best sweep result
if sweep_results:
    best = max(sweep_results, key=lambda x: x[1].total_return)
    print(f"\nBest sweep: atr_risk_pct={best[0]:.4f} → return={best[1].total_return:+.2f}% "
          f"sharpe={best[1].sharpe:.3f} max_dd={best[1].max_drawdown:.2f}%")
