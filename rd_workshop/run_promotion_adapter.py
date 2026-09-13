#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""晋升适配器：RD-Workshop 因子 → candidate train_v25 → 可交易 OOS → 人工审核报告。

边界（ADR-0001）:
  - 只写入 rd_workshop/candidates/<run_id>/
  - 绝不修改生产 models/、cron、paper_trading
  - 报告结论最多到 READY_FOR_HUMAN_REVIEW；无自动 Promotion

OOS 天数不足时（2026-09-13 起）:
  - 不再「干等 40 天」—— 走历史 walk-forward（--walkforward / --walkforward-report）
  - 全量请在新加坡沙箱跑（上海 3.6GB 会 OOM）；见 PROMOTION_CHECKLIST.md

用法:
  python3 -u rd_workshop/run_promotion_adapter.py --factors path/to/raw_or_normalized.parquet
  python3 -u rd_workshop/run_promotion_adapter.py --factors ... --skip-train   # 已有候选模型
  python3 -u rd_workshop/run_promotion_adapter.py --factors ... --max-stocks 80 --opt-only  # smoke
  python3 -u rd_workshop/run_promotion_adapter.py --factors ... --skip-train --skip-normalize --walkforward
  python3 -u rd_workshop/run_promotion_adapter.py --factors ... --skip-train --skip-normalize \\
      --walkforward-report rd_workshop/walkforward_runs/wf_<id>/report.json
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

# 历史 walk-forward 运气阈值（2026-09-13 安慰剂全量 sg_placebo_full_0913b 校准）
# 详见 knowledge/decisions/2026-09-13-promotion-gate-redesign.md §6.3.3
WF_MIN_WINS = 5          # 折间 wins ≥ 5/6
WF_REQUIRE_AUC_BN = True  # AUC beyond_noise
WF_REQUIRE_IC_LO95 = True # 块自举 RankIC lo95 > 0
WF_MIN_MEM_GB = 8.0       # 低于此内存拒绝本地全量（上海 3.6GB 会 OOM → 去新加坡）


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


def _mem_available_gb() -> float:
    try:
        with open("/proc/meminfo", encoding="ascii") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / 1e6
    except Exception:  # noqa: BLE001
        pass
    return 0.0


def _sg_walkforward_cmd(norm_path: Path, run_id: str) -> str:
    rel = norm_path
    try:
        rel = norm_path.relative_to(ROOT)
    except ValueError:
        pass
    return (
        f"python3 scripts/sg_sandbox.py --sync --run "
        f"\"rd_workshop/walkforward_oos.py --folds 6 --test-days 21 --control retrain "
        f"--extra-factors {rel} --run-id wf_{run_id}\""
    )


def _eval_walkforward(report: dict) -> dict:
    """用安慰剂校准的运气阈值判 walk-forward 报告。"""
    agg = report.get("aggregate") or {}
    boot = report.get("block_bootstrap") or {}
    auc = agg.get("auc") or {}
    ric = agg.get("rank_ic") or {}
    ric_boot = boot.get("rank_ic") or {}
    t10_boot = boot.get("top10_excess_pct") or {}

    wins = int(auc.get("wins") or 0)
    n = int(auc.get("n") or agg.get("n_folds") or 0)
    auc_bn = bool(auc.get("beyond_noise"))
    ric_bn = bool(ric.get("beyond_noise"))
    lo95 = ric_boot.get("lo95")
    lo95_ok = lo95 is not None and float(lo95) > 0

    checks = {
        "auc_beyond_noise": auc_bn,
        "rank_ic_beyond_noise": ric_bn,
        "rank_ic_lo95_gt0": lo95_ok,
        "wins_ge_5": wins >= WF_MIN_WINS,
        "wins": wins,
        "n_folds": n,
        "auc_mean_delta": auc.get("mean_delta"),
        "rank_ic_mean_delta": ric.get("mean_delta"),
        "rank_ic_lo95": lo95,
        "rank_ic_hi95": ric_boot.get("hi95"),
        "top10_lo95": t10_boot.get("lo95"),
        "top10_hi95": t10_boot.get("hi95"),
        "control_arm": (report.get("config") or {}).get("control_arm"),
        "lookahead_folds": (report.get("production_model") or {}).get("lookahead_folds") or [],
    }
    fail_reasons = []
    if WF_REQUIRE_AUC_BN and not auc_bn:
        fail_reasons.append("AUC not beyond_noise")
    if not ric_bn:
        fail_reasons.append("RankIC not beyond_noise")
    if WF_REQUIRE_IC_LO95 and not lo95_ok:
        fail_reasons.append(f"RankIC lo95={lo95} ≤ 0")
    if wins < WF_MIN_WINS:
        fail_reasons.append(f"wins {wins}/{n} < {WF_MIN_WINS}")
    if checks["lookahead_folds"]:
        fail_reasons.append(f"lookahead folds {checks['lookahead_folds']}")

    if fail_reasons:
        return {
            "verdict": "WALKFORWARD_FAIL",
            "reason": "; ".join(fail_reasons),
            "checks": checks,
            "thresholds": {
                "source": "sg_placebo_full_0913b",
                "min_wins": WF_MIN_WINS,
                "require_auc_beyond_noise": WF_REQUIRE_AUC_BN,
                "require_rank_ic_lo95_gt0": WF_REQUIRE_IC_LO95,
            },
        }
    return {
        "verdict": "WALKFORWARD_PASS",
        "reason": "beyond_noise + RankIC lo95>0 + wins≥5/6 (vs placebo)",
        "checks": checks,
        "thresholds": {
            "source": "sg_placebo_full_0913b",
            "min_wins": WF_MIN_WINS,
            "require_auc_beyond_noise": WF_REQUIRE_AUC_BN,
            "require_rank_ic_lo95_gt0": WF_REQUIRE_IC_LO95,
        },
    }


def _run_walkforward(norm_path: Path, run_dir: Path, run_id: str, folds: int, test_days: int) -> dict:
    """在本机跑历史 walk-forward；内存不足则拒绝（应去新加坡沙箱）。"""
    mem = _mem_available_gb()
    if 0 < mem < WF_MIN_MEM_GB:
        return {
            "verdict": "NEED_WALKFORWARD_ON_SG",
            "reason": (
                f"MemAvailable={mem:.1f}GB < {WF_MIN_MEM_GB}GB — "
                f"full walk-forward OOMs on Shanghai; run on SG sandbox"
            ),
            "sg_command": _sg_walkforward_cmd(norm_path, run_id),
            "checks": {"mem_available_gb": mem},
        }
    wf_id = f"wf_{run_id}"
    out_dir = ROOT / "rd_workshop" / "walkforward_runs" / wf_id
    cmd = [
        sys.executable, "-u", str(WS / "walkforward_oos.py"),
        "--folds", str(folds), "--test-days", str(test_days),
        "--control", "retrain",
        "--extra-factors", str(norm_path),
        "--run-id", wf_id,
    ]
    print(f"[walkforward] mem_available={mem:.1f}GB → running locally", flush=True)
    _run(cmd)
    rp = out_dir / "report.json"
    if not rp.exists():
        return {"verdict": "WALKFORWARD_ERROR", "reason": f"missing {rp}", "checks": {}}
    # 拷贝进候选目录便于人工审
    dest = run_dir / "walkforward_report.json"
    shutil.copy2(rp, dest)
    evaluated = _eval_walkforward(_load_json(rp))
    evaluated["report_path"] = str(dest)
    evaluated["source_run_id"] = wf_id
    return evaluated


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
    ap.add_argument(
        "--walkforward",
        action="store_true",
        help="OOS 天数不足时自动跑历史 walk-forward（内存不足则提示去新加坡）",
    )
    ap.add_argument(
        "--walkforward-report",
        default="",
        help="已有 walk-forward report.json（例如在 SG 跑完后回填），直接用运气阈值判定",
    )
    ap.add_argument("--walkforward-folds", type=int, default=6)
    ap.add_argument("--walkforward-test-days", type=int, default=21)
    args = ap.parse_args()

    # 环境变量也可打开自动 walk-forward（cron / SG 沙箱）
    auto_wf = args.walkforward or os.environ.get("ALPHAPILOT_AUTO_WALKFORWARD", "").strip() in (
        "1", "true", "TRUE", "yes",
    )

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
        if factor_src.resolve() != norm_path.resolve():
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

    # 3b) 历史 walk-forward（替代「干等 40 天」死循环）
    # 依据：2026-09-13 ADR promotion-gate-redesign；安慰剂校准运气阈值
    wf_gate: dict = {}
    attach_wf = bool(args.walkforward_report)
    need_wf = cand_gate.get("verdict") == "INSUFFICIENT_OOS"
    if attach_wf or need_wf:
        if args.walkforward_report:
            wrp = Path(args.walkforward_report)
            if not wrp.is_absolute():
                wrp = (ROOT / wrp).resolve()
            if not wrp.exists():
                raise SystemExit(f"walkforward report not found: {wrp}")
            shutil.copy2(wrp, run_dir / "walkforward_report.json")
            wf_gate = _eval_walkforward(_load_json(wrp))
            wf_gate["report_path"] = str(run_dir / "walkforward_report.json")
            wf_gate["source"] = "attached"
        elif auto_wf:
            wf_gate = _run_walkforward(
                norm_path, run_dir, run_id, args.walkforward_folds, args.walkforward_test_days
            )
            wf_gate["source"] = "auto"
        else:
            wf_gate = {
                "verdict": "NEED_WALKFORWARD",
                "reason": (
                    "OOS days insufficient; do NOT wait 40 days — run historical walk-forward "
                    "(prefer Singapore sandbox if MemAvailable < 8GB)"
                ),
                "sg_command": _sg_walkforward_cmd(norm_path, run_id),
                "local_command": (
                    f"python3 -u rd_workshop/run_promotion_adapter.py --factors {norm_path} "
                    f"--run-id {run_id} --skip-train --skip-normalize --walkforward"
                ),
                "attach_command": (
                    f"python3 -u rd_workshop/run_promotion_adapter.py --factors {norm_path} "
                    f"--run-id {run_id} --skip-train --skip-normalize "
                    f"--walkforward-report rd_workshop/walkforward_runs/wf_{run_id}/report.json"
                ),
                "checks": {},
            }
        print(
            f"[walkforward] verdict={wf_gate.get('verdict')} reason={wf_gate.get('reason')}",
            flush=True,
        )

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
    wf_verdict = (wf_gate or {}).get("verdict")
    ready = (
        cand_gate.get("verdict") == "PASS"
        and comparison.get("suggest_better_or_equal") is True
    ) or (
        wf_verdict == "WALKFORWARD_PASS"
        and comparison.get("suggest_better_or_equal") is not False
    )
    # 综合 backtest 标签：有 walk-forward 结论时优先展示它
    backtest_label = cand_gate.get("verdict")
    if wf_verdict in ("WALKFORWARD_PASS", "WALKFORWARD_FAIL", "NEED_WALKFORWARD",
                      "NEED_WALKFORWARD_ON_SG", "WALKFORWARD_ERROR"):
        backtest_label = wf_verdict

    if wf_verdict == "WALKFORWARD_PASS":
        next_step = (
            "WALKFORWARD_PASS: historical paired uplift beyond placebo noise — "
            "Human Review + short canary (5~10d) before any production install. "
            "Adapter will not promote."
        )
    elif wf_verdict == "WALKFORWARD_FAIL":
        next_step = (
            "WALKFORWARD_FAIL: uplift within placebo noise (or worse) — "
            "do NOT wait for 40 OOS days; reject or redesign factors."
        )
    elif wf_verdict in ("NEED_WALKFORWARD", "NEED_WALKFORWARD_ON_SG"):
        next_step = (
            f"Run walk-forward (not wait 40d). SG: {(wf_gate or {}).get('sg_command')}"
        )
    elif cand_gate.get("verdict") == "INSUFFICIENT_OOS":
        next_step = "Accumulate more OOS days OR pass --walkforward / --walkforward-report."
    else:
        next_step = (
            "HUMAN_REVIEW: compare packet vs production; if approved, manually install "
            "candidate artifacts into production models/ (Promotion). Adapter will not do it."
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
        "walkforward": wf_gate or None,
        "production_baseline": {
            "meta_trained_at": (prod_meta or {}).get("trained_at"),
            "oos_path": str(PROD_OOS),
            "kpi": prod_arm or None,
        },
        "comparison": comparison,
        "verdict": {
            "backtest": backtest_label,
            "tradable_oos_gate": cand_gate.get("verdict"),
            "walkforward_gate": wf_verdict,
            "ready_for_human_review": bool(
                ready
                or cand_gate.get("verdict") in ("PASS", "FAIL")
                or wf_verdict in ("WALKFORWARD_PASS", "WALKFORWARD_FAIL",
                                  "NEED_WALKFORWARD", "NEED_WALKFORWARD_ON_SG")
            ),
            "suggest_promotion_discussion": bool(ready),
            "next_step": next_step,
        },
        "checklist": [
            "Candidate models only under rd_workshop/candidates/",
            "Backtest Validation completed (oos.gate and/or walkforward)",
            "If INSUFFICIENT_OOS: run walk-forward — do NOT wait 40 calendar days",
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
    print(f"tradable_oos={cand_gate.get('verdict')} walkforward={wf_verdict} suggest_discuss={ready}")
    print(f"next_step={next_step}")
    print(f"report={report_path}")
    print("AUTO_PROMOTION=FORBIDDEN — await Human Review")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
