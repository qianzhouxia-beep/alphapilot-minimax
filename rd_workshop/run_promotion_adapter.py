#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""晋升适配器：RD-Workshop 因子 → candidate train_v25 → 可交易 OOS → 人工审核报告。

边界（ADR-0001）:
  - 只写入 rd_workshop/candidates/<run_id>/
  - 绝不修改生产 models/、cron、paper_trading
  - 报告结论最多到 READY_FOR_HUMAN_REVIEW；无自动 Promotion

用法:
  python3 -u rd_workshop/run_promotion_adapter.py --factors path/to/raw_or_normalized.parquet
  python3 -u rd_workshop/run_promotion_adapter.py --factors ... --skip-train   # 已有候选模型
  python3 -u rd_workshop/run_promotion_adapter.py --factors ... --max-stocks 80 --opt-only  # smoke
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WS = ROOT / "rd_workshop"
CAND_ROOT = WS / "candidates"
INBOUND = WS / "data_support" / "inbound"
PROD_OOS = ROOT / "output" / "oos_tradable_top2.json"
PROD_META = ROOT / "models" / "v25_meta.json"

MIN_DAYS = 40
MIN_FILL = 0.70
MIN_HIT3 = 0.35
PRODUCTION_ARM = "A1_permission"


def _run(cmd: list[str], env: dict | None = None) -> None:
    print("RUN:", " ".join(cmd), flush=True)
    rc = subprocess.call(cmd, cwd=str(ROOT), env=env)
    if rc != 0:
        raise SystemExit(f"command failed rc={rc}: {' '.join(cmd)}")


def _load_json(path: Path, default=None):
    if default is None:
        default = {}
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _pick_arm(kpis: list, prefer: str) -> dict:
    by = {k.get("arm"): k for k in kpis or []}
    if prefer in by:
        return by[prefer]
    if "A1_permission" in by:
        return by["A1_permission"]
    return (kpis or [{}])[0]


def _gate(kpi: dict, n_days: int) -> dict:
    fill = float(kpi.get("fill_rate") or 0)
    hit3 = float(kpi.get("hit_3pct_rate") or 0)
    enough = n_days >= MIN_DAYS
    checks = {
        "enough_days": enough,
        "fill_rate_ok": (fill >= MIN_FILL) if enough else None,
        "hit_3pct_ok": (hit3 >= MIN_HIT3) if enough else None,
        "max_drawdown": float(kpi.get("max_drawdown") or 0),
    }
    if not enough:
        verdict = "INSUFFICIENT_OOS"
        reason = f"OOS days={n_days} < {MIN_DAYS}"
    elif checks["fill_rate_ok"] and checks["hit_3pct_ok"]:
        verdict = "PASS"
        reason = "fill & hit≥3% meet playbook"
    else:
        verdict = "FAIL"
        reason = "fill or hit≥3% below playbook"
    return {"verdict": verdict, "reason": reason, "checks": checks}


def _compare(cand: dict, prod: dict | None) -> dict:
    if not prod:
        return {"available": False, "note": "no production OOS baseline on disk"}
    keys = ["fill_rate", "hit_3pct_rate", "win_rate", "max_drawdown", "total_return", "avg_return"]
    delta = {}
    for k in keys:
        try:
            delta[k] = float(cand.get(k) or 0) - float(prod.get(k) or 0)
        except (TypeError, ValueError):
            delta[k] = None
    better_hit = (cand.get("hit_3pct_rate") or 0) >= (prod.get("hit_3pct_rate") or 0)
    better_fill = (cand.get("fill_rate") or 0) >= (prod.get("fill_rate") or 0) - 0.02
    not_worse_dd = (cand.get("max_drawdown") or 0) <= (prod.get("max_drawdown") or 0) + 0.02
    return {
        "available": True,
        "delta": delta,
        "suggest_better_or_equal": bool(better_hit and better_fill and not_worse_dd),
        "rules": {
            "hit_3pct_ge_prod": better_hit,
            "fill_within_2pp": better_fill,
            "maxdd_within_2pp": not_worse_dd,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="RD-Workshop promotion adapter (no production writes)")
    ap.add_argument("--factors", required=True, help="raw or normalized factor file")
    ap.add_argument("--run-id", default="", help="default: timestamp")
    ap.add_argument("--start", default="", help="OOS start YYYY-MM-DD")
    ap.add_argument("--end", default="", help="OOS end YYYY-MM-DD")
    ap.add_argument("--top-n", type=int, default=2)
    ap.add_argument("--opt-only", action="store_true", default=True)
    ap.add_argument("--train-base", action="store_true", help="also train v25_base")
    ap.add_argument("--max-stocks", type=int, default=0)
    ap.add_argument("--skip-train", action="store_true")
    ap.add_argument("--skip-oos", action="store_true")
    ap.add_argument("--skip-normalize", action="store_true", help="factors already normalized")
    args = ap.parse_args()

    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = CAND_ROOT / run_id
    model_dir = run_dir / "models"
    report_path = run_dir / "promotion_report.json"
    gated_out = run_dir / "v3_tradable_gated_sleeve_backtest.json"
    norm_path = run_dir / "normalized_factors.parquet"

    # 安全闸：禁止指向生产 models
    prod_models = (ROOT / "models").resolve()
    if model_dir.resolve() == prod_models:
        raise SystemExit("refusing to write candidate into production models/")

    run_dir.mkdir(parents=True, exist_ok=True)
    INBOUND.mkdir(parents=True, exist_ok=True)

    factor_src = Path(args.factors)
    if not factor_src.is_absolute():
        factor_src = (ROOT / factor_src).resolve()
    if not factor_src.exists():
        raise SystemExit(f"factors not found: {factor_src}")

    # 1) normalize
    if args.skip_normalize:
        shutil.copy2(factor_src, norm_path)
    else:
        _run(
            [
                sys.executable,
                "-u",
                str(WS / "normalize_factors.py"),
                "--input",
                str(factor_src),
                "--output",
                str(norm_path),
            ]
        )

    env = os.environ.copy()
    env["ALPHAPILOT_ROOT"] = str(ROOT)
    env["ALPHAPILOT_MODEL_DIR"] = str(model_dir)
    env["ALPHAPILOT_EXTRA_FACTORS"] = str(norm_path)
    env["ALPHAPILOT_GATED_OUT"] = str(gated_out)

    # 2) train candidate
    train_meta = {}
    if not args.skip_train:
        cmd = [
            sys.executable,
            "-u",
            str(ROOT / "train_v25.py"),
            "--model-dir",
            str(model_dir),
            "--extra-factors",
            str(norm_path),
        ]
        if args.opt_only and not args.train_base:
            cmd.append("--opt-only")
        if args.max_stocks:
            cmd.extend(["--max-stocks", str(args.max_stocks)])
        _run(cmd, env=env)
    train_meta = _load_json(model_dir / "v25_meta.json")
    if not train_meta:
        raise SystemExit(f"missing candidate meta: {model_dir / 'v25_meta.json'}")

    # 3) OOS tradable gated (candidate models via env)
    cand_kpi = {}
    cand_gate = {}
    oos_window = {}
    if not args.skip_oos:
        trained = str(train_meta.get("trained_at") or "")[:10]
        end = args.end or datetime.now().strftime("%Y-%m-%d")
        if args.start:
            start = args.start
        elif trained:
            start = (datetime.strptime(trained, "%Y-%m-%d") + timedelta(days=1)).strftime(
                "%Y-%m-%d"
            )
        else:
            start = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
        oos_window = {"start": start, "end": end, "top_n": args.top_n}
        _run(
            [
                sys.executable,
                "-u",
                str(ROOT / "backtest_v3_tradable_gated.py"),
                "--start",
                start,
                "--end",
                end,
                "--top-n",
                str(args.top_n),
                "--sleeve-top-n",
                str(args.top_n),
            ],
            env=env,
        )
        gated = _load_json(gated_out)
        cand_kpi = _pick_arm(gated.get("kpi") or [], PRODUCTION_ARM)
        n_days = int(cand_kpi.get("n_days") or 0)
        cand_gate = _gate(cand_kpi, n_days)

    # 4) compare production baseline (read-only)
    prod_oos = _load_json(PROD_OOS)
    prod_arm = None
    k = prod_oos.get("kpi")
    if isinstance(k, dict) and k:
        prod_arm = k
    elif isinstance(k, list):
        prod_arm = _pick_arm(k, PRODUCTION_ARM)
    if not prod_arm:
        prod_arm = prod_oos.get("arm") or None
    prod_meta = _load_json(PROD_META)
    comparison = _compare(cand_kpi, prod_arm if prod_arm else None)

    # 5) human-review packet — never auto promote
    ready = (
        cand_gate.get("verdict") == "PASS"
        and comparison.get("suggest_better_or_equal") is True
    )
    track = (
        "track_a_current_model"
        if "track_a" in run_id
        else ("track_b_rdagent_self_dev" if "track_b" in run_id else "manual")
    )
    report = {
        "track": track,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "run_id": run_id,
        "department": "Model R&D Workshop",
        "boundary": {
            "writes_production_models": False,
            "touches_production_task_chain": False,
            "auto_promotion": False,
            "requires_human_review": True,
        },
        "inputs": {
            "factors_src": str(factor_src),
            "normalized_factors": str(norm_path),
            "track": track,
        },
        "candidate": {
            "model_dir": str(model_dir),
            "trained_at": train_meta.get("trained_at"),
            "extra_factor_columns": train_meta.get("extra_factor_columns")
            or (train_meta.get("features") or {}).get("extra_rd_factors"),
            "ab_test": train_meta.get("ab_test"),
        },
        "oos": {
            "window": oos_window,
            "arm": PRODUCTION_ARM,
            "kpi": cand_kpi,
            "gate": cand_gate,
            "gated_path": str(gated_out),
        },
        "production_baseline": {
            "meta_trained_at": (prod_meta or {}).get("trained_at"),
            "oos_path": str(PROD_OOS),
            "kpi": prod_arm or None,
        },
        "comparison": comparison,
        "verdict": {
            "backtest": cand_gate.get("verdict"),
            "ready_for_human_review": bool(
                ready or cand_gate.get("verdict") in ("PASS", "FAIL", "INSUFFICIENT_OOS")
            ),
            "suggest_promotion_discussion": bool(ready),
            "next_step": (
                "HUMAN_REVIEW: compare packet vs production; if approved, manually install "
                "candidate artifacts into production models/ (Promotion). Adapter will not do it."
                if cand_gate.get("verdict") != "INSUFFICIENT_OOS"
                else "Accumulate more OOS days; do not promote."
            ),
        },
        "checklist": [
            "Candidate models only under rd_workshop/candidates/",
            "Backtest Validation completed (this report.oos.gate)",
            "Human Review required before any production install",
            "Compare Candidate vs Production Model metrics",
            "No cron / paper_trading / live scorer path changed by this adapter",
        ],
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    # also drop a copy under inbound for Data Support visibility
    shutil.copy2(report_path, INBOUND / f"promotion_report_{run_id}.json")

    print("\n======== PROMOTION ADAPTER ========")
    print(f"track={track} run_id={run_id}")
    print(f"candidate_dir={model_dir}")
    print(f"backtest={cand_gate.get('verdict')} suggest_discuss={ready}")
    print(f"report={report_path}")
    print("AUTO_PROMOTION=FORBIDDEN — await Human Review")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
