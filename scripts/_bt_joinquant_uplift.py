# -*- coding: utf-8 -*-
"""聚宽候选因子 V25 增量重训对比（服务器跑，一次全跑三组）
组别:
  A. baseline  : 现有 106 维 v25_opt（无 extra）
  B. plus3     : + tvstd20 / corr_ret_vol_20 / vol_ma_ratio（首选）
  C. plus_all  : + 首选3 + turnover_vol_ratio（候选）
对比指标: v25_opt AUC (3-fold) + 样本数/维度
全部写入 rd_workshop/candidates/，不碰生产 models/。
"""
import json, os, subprocess, sys
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
ROOT = Path(os.environ.get("ALPHAPILOT_ROOT") or "/home/ubuntu/alphapilot")
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

GEN = ROOT / "scripts" / "_gen_joinquant_factors.py"
FACTOR_FULL = ROOT / "rd_workshop" / "data_support" / "inbound" / "joinquant_factors_20260830.parquet"
OUT = ROOT / "output" / "bt_joinquant_uplift.json"

PRIMARY = ["rd_tvstd20", "rd_corr_ret_vol_20", "rd_vol_ma_ratio"]
CANDIDATE = ["rd_turnover_vol_ratio", "rd_turnover_ratio"]

RUNS = [
    ("baseline", None),
    ("plus3", PRIMARY),
    ("plus_all", PRIMARY + CANDIDATE),
]


def run(cmd: list[str]) -> None:
    print("RUN:", " ".join(str(c) for c in cmd), flush=True)
    rc = subprocess.call(cmd, cwd=str(ROOT))
    if rc != 0:
        raise SystemExit(f"command failed rc={rc}")


def main() -> int:
    import pandas as pd

    # 1) 生成因子表（若未生成）
    if not FACTOR_FULL.exists():
        run([sys.executable, "-u", str(GEN)])
    full = pd.read_parquet(FACTOR_FULL)
    print(f"factor table: {len(full)} rows, cols={list(full.columns)[2:]}", flush=True)

    # 2) 生成 plus3 子表（只留首选3）
    plus3_path = FACTOR_FULL.with_name("joinquant_factors_plus3_20260830.parquet")
    full[["date", "symbol"] + PRIMARY].to_parquet(plus3_path, index=False)

    results = {}
    for tag, cols in RUNS:
        run_dir = ROOT / "rd_workshop" / "candidates" / f"jq_{tag}_20260830"
        model_dir = run_dir / "models"
        cmd = [
            sys.executable, "-u",
            str(ROOT / "train_v25.py"),
            "--model-dir", str(model_dir),
            "--opt-only",
        ]
        if cols:
            fpath = FACTOR_FULL if len(cols) > len(PRIMARY) else plus3_path
            cmd += ["--extra-factors", str(fpath)]
        run(cmd)
        meta = json.loads((model_dir / "v25_meta.json").read_text(encoding="utf-8"))
        ab = meta.get("ab_test", {})
        results[tag] = {
            "auc_opt": ab.get("v25_opt_auc"),
            "aucs_opt": ab.get("v25_opt_model_aucs"),
            "dim_opt": ab.get("v25_opt_dim"),
            "dim_base": ab.get("v25_base_dim"),
            "n_samples": meta.get("training", {}).get("n_samples"),
            "positive_rate": meta.get("training", {}).get("positive_rate"),
            "extra_cols": meta.get("features", {}).get("extra_rd_factors", []),
            "trained_at": meta.get("trained_at"),
        }
        print(f"\n[{tag}] AUC={results[tag]['auc_opt']} dim={results[tag]['dim_opt']} "
              f"extra={results[tag]['extra_cols']}", flush=True)

    # 3) 汇总 + 边际
    summary = {
        "generated_at": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "note": "poly宽社区候选因子 V25 增量重训对比; baseline=现有106维 opt; plus3=+首选3; plus_all=+全部",
        "runs": results,
    }
    base_auc = results["baseline"].get("auc_opt")
    if base_auc:
        summary["marginal"] = {
            "plus3_vs_baseline": round((results["plus3"]["auc_opt"] or 0) - base_auc, 4),
            "plus_all_vs_baseline": round((results["plus_all"]["auc_opt"] or 0) - base_auc, 4),
            "plus_all_vs_plus3": round((results["plus_all"]["auc_opt"] or 0) - (results["plus3"]["auc_opt"] or 0), 4),
        }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nSUMMARY:", json.dumps(summary.get("marginal", {}), ensure_ascii=False), flush=True)
    print("saved:", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
