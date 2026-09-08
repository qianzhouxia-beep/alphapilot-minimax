#!/usr/bin/env python3
"""A/B backtest: static histogram lookup vs ML incremental learner for Kelly.

If real backtest files exist, loads them; otherwise generates synthetic trades
to validate model behavior end-to-end.

Usage:
  python scripts/backtest_kelly_learner.py
"""
import json, sys, os
from pathlib import Path
import numpy as np

ROOT = Path(os.environ.get("ALPHAPILOT_ROOT") or Path(__file__).resolve().parent.parent)
os.chdir(str(ROOT))
sys.path.insert(0, str(ROOT))

# ── Static lookup bins (from kelly_sizing._SCORE_BINS) ──
STATIC_BINS = [(0.95, 0.58, 2.10), (0.90, 0.55, 1.90), (0.80, 0.52, 1.80), (0.00, 0.50, 1.80)]

def _static_lookup(pct):
    for thr, p, b in STATIC_BINS:
        if pct >= thr:
            return p, b
    return 0.50, 1.8

def _static_kelly(pct):
    p, b = _static_lookup(pct)
    q = 1.0 - p
    k = max(0.0, (p * b - q) / b) if b > 0 else 0.0
    return k * 0.5  # Half-Kelly

def _ml_kelly(pct, learner):
    if learner is None:
        return _static_kelly(pct)
    p_ml = learner.predict_win_rate(pct, vol=0.30, expo=0)
    p_ml = max(0.05, min(0.95, p_ml))
    b = 1.8
    q = 1.0 - p_ml
    k = max(0.0, (p_ml * b - q) / b) if b > 0 else 0.0
    return k * 0.5

def _generate_synthetic_trades(n=200):
    np.random.seed(42)
    trades = []
    for i in range(n):
        score = np.random.uniform(0.30, 0.95)
        win_prob = 0.35 + score * 0.35
        is_win = np.random.rand() < win_prob
        ret = np.random.uniform(0.02, 0.15) if is_win else np.random.uniform(-0.10, -0.02)
        trades.append({
            "symbol": f"stock{i:04d}",
            "score": round(float(score), 4),
            "ret": round(float(ret), 4),
            "win": int(is_win),
            "buy_date": f"2026-0{1+i//30:02d}-0{1+i%28:02d}",
        })
    trades.sort(key=lambda t: t["buy_date"])
    return trades


def simulate():
    # ── Load data ──
    candidates = [
        ROOT / "output" / "v3_tradable_gated_sleeve_backtest.json",
        ROOT / "output" / "v3_tradable_gated_backtest.json",
        ROOT / "output" / "v3_tradable_top3_backtest.json",
    ]
    bt_path = next((p for p in candidates if p.exists()), None)

    if bt_path:
        data = json.loads(bt_path.read_text(encoding="utf-8"))
        trades = data.get("trades") or []
        if isinstance(trades, dict):
            trades = next(iter(trades.values()), [])
        trades = [t for t in trades if not t.get("skipped") and t.get("score") is not None]
        print(f"\nLoaded {len(trades)} real trades from {bt_path.name}")
    else:
        print("\nNo real backtest file found — generating 200 synthetic trades")
        trades = _generate_synthetic_trades(200)

    if len(trades) < 50:
        print("Too few trades, skipping")
        return

    # ── Simulation ──
    def _simulate(use_ml=False, learner=None):
        pnls = []
        for t in trades:
            score = float(t.get("score", 0))
            all_scores = [float(x.get("score", 0)) for x in trades]
            pct = (sum(1 for s in all_scores if s <= score) / max(len(all_scores), 1)
                   if score > 0 else 0.5)
            k = _ml_kelly(pct, learner) if use_ml else _static_kelly(pct)
            w = k * 0.01  # 1% base risk per trade
            ret = float(t.get("ret") or 0) * w
            pnls.append(ret)

            if learner is not None:
                learner.add_trade(
                    symbol=str(t.get("symbol", "")),
                    entry_score=score,
                    entry_score_pct=pct,
                    entry_vol=0.30,
                    expo=0,
                    pnl=ret,
                    held_days=int(t.get("trading_days_held") or 1),
                    sell_action="backtest",
                    buy_date=str(t.get("buy_date") or ""),
                    sell_date=str(t.get("sell_date") or ""),
                )
        return np.array(pnls)

    # Static
    static_pnls = _simulate(use_ml=False)

    # ML online
    try:
        from kelly_learner import KellyLearner
        ml_learner = KellyLearner()
        ml_learner.trades = []
        ml_pnls = _simulate(use_ml=True, learner=ml_learner)
        ml_ok = True
    except Exception as e:
        print(f"  KellyLearner error: {e}")
        ml_pnls = None
        ml_ok = False

    # ── Compare ──
    print("\n" + "=" * 60)
    print("A/B Comparison: Static Lookup vs Online Incremental ML")
    print("=" * 60)

    def _metrics(arr, label):
        total = float(arr.sum())
        wins = arr[arr > 0]
        losses = arr[arr < 0]
        wr = len(wins) / max(len(arr), 1)
        avg_w = float(wins.mean()) if len(wins) > 0 else 0
        avg_l = float(abs(losses.mean())) if len(losses) > 0 else 0
        payoff = avg_w / avg_l if avg_l > 0 else 0
        cum = np.cumsum(arr)
        dd = float((np.maximum.accumulate(cum) - cum).max())
        sharpe = float(arr.mean() / arr.std() * np.sqrt(252)) if arr.std() > 0 else 0
        print(f"\n{label}:")
        print(f"  Total Return:  {total:>10.4f}")
        print(f"  Win Rate:      {wr:>10.1%}")
        print(f"  Payoff Ratio:  {payoff:>10.2f}")
        print(f"  Max DD:        {dd:>10.4f}")
        print(f"  Sharpe:        {sharpe:>10.2f}")
        print(f"  Trades:        {len(arr):>10d}")
        return {"total": total, "wr": wr, "payoff": payoff, "dd": dd, "sharpe": sharpe}

    s = _metrics(static_pnls, "Static Table Lookup")
    if ml_pnls is not None:
        m = _metrics(ml_pnls, "Online Incremental ML (KellyLearner)")
        print("\n--- Difference (ML - Static) ---")
        for k in ("total", "wr", "payoff", "dd", "sharpe"):
            diff = m[k] - s[k]
            print(f"  {k}: {diff:+.4f}")
        print(f"\nML Model final steps: {ml_learner.model.steps}")
        print(f"ML Weights (score_pct, vol_norm, expo_norm): "
              f"{[round(w, 4) for w in ml_learner.model.w.tolist()]}")
    else:
        print("\nML simulation skipped")

    # Cleanup test artifacts
    for p in [ROOT / "data" / "kelly_learner_trades.json",
              ROOT / "data" / "kelly_learner_model.json"]:
        if p.exists():
            p.unlink()

    print("\n--- Done ---")
    print(f"Source: {Path(__file__).resolve()}")
    print(f"On Shanghai: python scripts/backtest_kelly_learner.py")


if __name__ == "__main__":
    simulate()