#!/usr/bin/env python3
"""Full crypto pipeline for Singapore server — v2 optimized."""
import sys, warnings, json
from datetime import datetime

warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/ubuntu/alphapilot")


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


log("=" * 50)
log("AlphaPilot Crypto v2 — Singapore Server Pipeline")
log("=" * 50)

from crypto.config import MODEL_DIR, MODEL_PARAMS, ICIR_TOP_K, USE_SHORT_MODEL, PAPER

# 1. Fetch
log("Fetching Binance data (2000 bars)...")
from crypto.data import build_dataset
df = build_dataset(limit=2000, force_refresh=True)
log(f"Data: {len(df)} rows, {df['symbol'].nunique()} symbols")

# 2. Features
log("Computing features (fwd=2, thr=0.01)...")
from crypto.features import compute_features, list_factors
df = compute_features(df, forward=2, threshold=0.01)
all_factors = list_factors()
log(f"All factors: {len(all_factors)}")

# 3. ICIR → top-60 factor selection
log(f"Running ICIR (top-{ICIR_TOP_K})...")
from crypto.icir import run_icir_analysis
icir = run_icir_analysis(df)
ranked = sorted(icir["summary"].items(), key=lambda x: -x[1]["abs_icir"])
top_factors = [f[0] for f in ranked[:ICIR_TOP_K]]
factors = [f for f in top_factors if f in df.columns]
log(f"Selected {len(factors)} factors")
for f in icir["top_factors"][:10]:
    log(f"  {f['factor']:30s}  |ICIR|={f['abs_icir']:.4f}")

# 4. Prepare 2h training data
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

# 5. Train with best params
import shutil
from crypto.train import train_model
# Guardrail: backup current live models so a rejected retrain can be rolled back
for _name in ["model_long.ubj", "model_short.ubj"]:
    _src = MODEL_DIR / _name
    if _src.exists():
        shutil.copy2(_src, MODEL_DIR / f"{_name}.bak")
        log(f"Backed up {_name} -> {_name}.bak")
# Pass full t_2h — train_model does its own 80/20 time split (test = latest 20%)
train_set = t_2h
split = int(len(t_2h) * 0.8)
test_set = t_2h.iloc[split:]

log(f"Training long model (params: {MODEL_PARAMS})...")
lm = train_model(
    train_set, target="label_long", factors=factors,
    hyperparams=MODEL_PARAMS,
    model_path=str(MODEL_DIR / "model_long.ubj"),
)
log(f"Long AUC: {lm['auc']:.4f}")

sm = None
if USE_SHORT_MODEL:
    log(f"Training short model (params: {MODEL_PARAMS})...")
    sm = train_model(
        train_set, target="label_short", factors=factors,
        hyperparams=MODEL_PARAMS,
        model_path=str(MODEL_DIR / "model_short.ubj"),
    )
    log(f"Short AUC: {sm['auc']:.4f}")
else:
    log("Short model disabled (USE_SHORT_MODEL=False)")

# 5b. Walk-forward guardrail — validate OOS before keeping the new models
log("Running walk-forward OOS guardrail...")
from crypto.walkforward import run_walkforward, check_guardrail, append_guardrail_history
wf_long = run_walkforward(t_2h, factors, "label_long", hyperparams=MODEL_PARAMS, n_folds=4)
guard_long = check_guardrail(wf_long)
log(f"WFO long: oos_auc={wf_long.get('oos_auc')} n_oos={wf_long.get('n_oos')} -> {guard_long['decision']}")
append_guardrail_history(guard_long, "long")
wf_short = guard_short = None
if USE_SHORT_MODEL and sm is not None:
    wf_short = run_walkforward(t_2h, factors, "label_short", hyperparams=MODEL_PARAMS, n_folds=4)
    guard_short = check_guardrail(wf_short)
    log(f"WFO short: oos_auc={wf_short.get('oos_auc')} n_oos={wf_short.get('n_oos')} -> {guard_short['decision']}")
    append_guardrail_history(guard_short, "short")

_guards_ok = guard_long["pass"] and (guard_short is None or guard_short["pass"])
if not _guards_ok:
    log("GUARDRAIL REJECTED the retrained model(s) — restoring previous models")
    for _name in ["model_long.ubj", "model_short.ubj"]:
        _bak = MODEL_DIR / f"{_name}.bak"
        if _bak.exists():
            shutil.copy2(_bak, MODEL_DIR / _name)
            log(f"Restored {_name} from .bak")
else:
    log("Guardrail passed — keeping retrained models")
    for _name in ["model_long.ubj", "model_short.ubj"]:
        _bak = MODEL_DIR / f"{_name}.bak"
        if _bak.exists():
            _bak.unlink()
            log(f"Removed {_name}.bak")

# 6. OOS peel backtest (2h entry, same TF)
log("Running OOS peel backtest (all data, 2h entry)...")
from crypto.backtest import backtest, print_result
bt = backtest(df, factors=factors, min_score=PAPER.min_signal_score,
              min_score_short=PAPER.min_signal_score_short, per_trade_risk=0.10, entry_timeframe="2h",
              short_model=USE_SHORT_MODEL)
print_result(bt)

# 7. Grid backtest (2h entry, same TF)
log("Running grid backtest (all data, 2h entry)...")
from crypto.grid_backtest import grid_backtest, print_grid_result
gr = grid_backtest(df, factors=factors, min_score=PAPER.min_signal_score,
                    min_score_short=PAPER.min_signal_score_short, per_signal_risk=0.10, entry_timeframe="2h",
                    use_atr_sizing=PAPER.use_atr_sizing, atr_risk_pct=PAPER.atr_risk_pct,
                    atr_max_batch_pct=PAPER.atr_max_batch_pct,
                    max_positions_per_sym=3, cooldown_bars=4)
print_grid_result(gr)

# 8. Current signals
log("Generating live signals...")
from crypto.simulate import run_simulation, print_signals
sig = run_simulation(force_fetch=False)
print_signals(sig)

# 9. Self-improvement: attribute recent paper trades → adapt thresholds
log("Running self-improvement loop (attribution → adaptive thresholds)...")
from crypto.learning import run_learning_loop
_state_path = MODEL_DIR / "paper_state.json"
_trades = []
if _state_path.exists():
    _state = json.loads(_state_path.read_text(encoding="utf-8"))
    _trades = _state.get("trades", [])
_lrep, _ldec, _lpath = run_learning_loop(_trades)
log(f"Learning: {len(_trades)} trades, flags={len(_lrep.flags)}")
for _fl in _lrep.flags[:10]:
    log(f"  FLAG [{_fl['type']}] {_fl['bucket']}: n={_fl['n']} pnl={_fl['pnl']:+.2f} wr={_fl['win_rate']}%")
for _n in _ldec.notes[:10]:
    log(f"  {_n}")
log(f"Learning report: {_lpath}")

# 10. Save report
report = {
    "asof": datetime.now().isoformat(),
    "server": "Singapore",
    "config": {
        "symbols": list(df["symbol"].unique()),
        "timeframes": list(df["timeframe"].unique()),
        "n_factors": len(factors),
        "model_params": MODEL_PARAMS,
        "training_tf": "2h",
        "entry_tf": "2h",
        "forward": 2,
        "per_signal_risk": 0.10,
        "min_score": PAPER.min_signal_score,
        "min_score_short": PAPER.min_signal_score_short,
        "atr_risk_pct": PAPER.atr_risk_pct,
        "atr_max_batch_pct": PAPER.atr_max_batch_pct,
    },
    "data": {"rows": len(df), "train": len(train_set), "test": len(test_set)},
    "long_auc": lm["auc"],
    "short_auc": sm["auc"] if sm else None,
    "guardrail": {
        "long_oos_auc": wf_long.get("oos_auc") if wf_long else None,
        "long_decision": guard_long["decision"] if guard_long else None,
        "short_oos_auc": wf_short.get("oos_auc") if wf_short else None,
        "short_decision": guard_short["decision"] if guard_short else None,
        "floor": (guard_long or {}).get("floor"),
    },
    "oos_backtest": {
        "n_trades": bt.n_trades, "total_return_pct": bt.total_return,
        "sharpe": bt.sharpe, "max_dd_pct": bt.max_drawdown,
        "win_rate_pct": bt.win_rate, "profit_factor": bt.profit_factor,
    },
    "grid_backtest": {
        "n_trades": gr.n_trades, "total_return_pct": gr.total_return,
        "win_rate_pct": gr.win_rate, "profit_factor": gr.profit_factor,
        "avg_hold_hours": gr.avg_hold_hours, "max_dd_pct": gr.max_drawdown,
    },
    "learning": {
        "n_trades": _lrep.n_trades,
        "overall_pnl": _lrep.overall_pnl,
        "overall_win_rate": _lrep.overall_win_rate,
        "by_direction": _lrep.by_direction,
        "by_session": _lrep.by_session,
        "by_hold_bucket": _lrep.by_hold_bucket,
        "flags": _lrep.flags,
        "adaptive": {
            "baseline_long": _ldec.baseline_long,
            "baseline_short": _ldec.baseline_short,
            "per_symbol": _ldec.per_symbol,
            "session_gates": _ldec.session_gates,
        },
    },
}
rp = MODEL_DIR / "sg_server_report.json"
rp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
log(f"Report: {rp}")

with open(str(MODEL_DIR / "train_history.jsonl"), "a") as f:
    f.write(json.dumps({
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "long_auc": lm["auc"], "short_auc": sm["auc"] if sm else None,
        "n_factors": len(factors),
        "n_train": lm["n_train"],
        "guard_long": guard_long["decision"] if guard_long else None,
        "guard_short": guard_short["decision"] if guard_short else None,
        "n_flags": len(_lrep.flags),
    }) + "\n")

log("DONE")
