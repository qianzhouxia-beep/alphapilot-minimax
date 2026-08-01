"""Crypto quant paper trading — main entry point.

Run paper pipeline:
    python -m crypto.run_paper fetch     # download fresh data
    python -m crypto.run_paper analyze   # ICIR factor analysis
    python -m crypto.run_paper train     # train models
    python -m crypto.run_paper backtest  # run backtest
    python -m crypto.run_paper report    # full pipeline + canvas
"""
from __future__ import annotations

import json
import sys
from datetime import datetime

from .config import ICIR_PATH, MODEL_PATH, SIGNAL_PATH


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def cmd_fetch():
    from .data import build_dataset

    df = build_dataset(force_refresh=True)
    print(f"\n✅ Fetched: {len(df)} rows, {df['symbol'].nunique()} symbols")


def cmd_analyze():
    from .icir import run_icir_pipeline

    result = run_icir_pipeline(force_fetch=False)
    print(f"\n✅ ICIR analysis: {result['n_factors']} factors evaluated")
    print("\nTop 10 factors by |ICIR|:")
    for f in result["top_factors"][:10]:
        print(f"  {f['factor']:30s}  IC={f['ic_mean']:+.6f}  |ICIR|={f['abs_icir']:.4f}")


def cmd_train():
    from .train import run_training_pipeline

    metrics = run_training_pipeline(force_fetch=False)
    print(f"\n✅ Training complete")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


def cmd_backtest():
    from .backtest import run_backtest_pipeline, print_result

    result = run_backtest_pipeline(force_fetch=False)
    print_result(result)
    return result


def cmd_report():
    """Full pipeline + save report + optionally open canvas."""
    log("Starting full crypto paper pipeline...")
    from .data import build_dataset

    df = build_dataset()
    log(f"Data: {len(df)} rows")

    from .features import compute_features

    df = compute_features(df, forward=4, threshold=0.02)
    log(f"Features: done")

    from .icir import run_icir_analysis

    icir_result = run_icir_analysis(df)
    log(f"ICIR: {icir_result['n_factors']} factors")

    from .train import train_both_targets

    train_metrics = train_both_targets(df)
    log(f"Training: done")

    from .backtest import backtest

    bt = backtest(df)
    from .backtest import print_result

    print_result(bt)

    # Save summary
    report = {
        "asof": datetime.now().isoformat(),
        "data": {"rows": len(df), "symbols": df["symbol"].nunique(), "tfs": df["timeframe"].unique().tolist()},
        "icir": {"n_factors": icir_result["n_factors"], "top": icir_result["top_factors"][:10]},
        "train": train_metrics,
        "backtest": {
            "n_trades": bt.n_trades,
            "total_return_pct": bt.total_return,
            "sharpe": bt.sharpe,
            "max_dd_pct": bt.max_drawdown,
            "win_rate_pct": bt.win_rate,
            "profit_factor": bt.profit_factor,
            "avg_win_pct": bt.avg_win,
            "avg_loss_pct": bt.avg_loss,
        },
    }

    report_path = MODEL_PATH.parent / "paper_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Report saved: {report_path}")
    return report


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)

    cmds = {
        "fetch": cmd_fetch,
        "analyze": cmd_analyze,
        "train": cmd_train,
        "backtest": cmd_backtest,
        "report": cmd_report,
    }
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print(f"Usage: python -m crypto.run_paper <{'|'.join(cmds.keys())}>")
        sys.exit(1)
    cmds[sys.argv[1]]()
