#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""历史 walk-forward OOS 评估器 —— 候选模型 vs 冻结生产模型，同折配对比较。

## 它解决什么问题（2026-09-13 老板提出）

现行晋升门要求「训练截止之后 ≥40 个**真实**交易日」的样本外表现：
  · `rd_workshop/run_promotion_adapter.py`  → `MIN_DAYS = 40`
  · `scripts/run_oos_tradable_top2.py`      → `MIN_DAYS = 40`

于是每逢周末重训，OOS 计数从 0 重新开始（实测：09-12 训练的候选
`OOS days=0 < 40 → INSUFFICIENT_OOS`）。要等 40 天，可那时环境又变、
又该重训 —— 永远追不上。这不是模型问题，是**验证机制的死循环**。

本工具用**历史数据**把「训练→样本外」这个过程重放 N 次（滚动 walk-forward），
把「等 40 个真实交易日」压缩成「一次跑完过去 N 个月的多折」。

每折在**同一批测试样本**上同时评估两臂：
  · 候选：只用「该折测试窗之前」的数据现场训练（含可选 RD 增量因子）
  · 生产：读 `models/v25_opt_ensemble_{1,2,3}.ubj` 冻结模型，不重训

输出逐折 AUC / RankIC / TopK 超额，以及**配对差（候选 − 生产）**与折间
离散度 ⇒ 得到「多少提升才算超过噪声」的**数据驱动**门槛，替代拍脑袋的 40 天。

## 边界（ADR-0001）

  · 只读 `models/` 与 `data/`；只写 `rd_workshop/walkforward_runs/<run_id>/`
  · 不写生产 `models/`、不改 cron、不改 paper_trading、不自动晋升
  · 结论只到报告；晋升仍需人工

## 用法

  # 标准：最近 6 折，每折 21 个交易日
  python3 -u rd_workshop/walkforward_oos.py --folds 6 --test-days 21

  # smoke（小样本、少折，确认管线跑通）
  python3 -u rd_workshop/walkforward_oos.py --max-stocks 200 --folds 2 --test-days 10

  # 评估带 RD 增量因子的候选
  python3 -u rd_workshop/walkforward_oos.py --extra-factors <normalized.parquet>

  # 只评并行基线（候选=同折现场重训，等于「数据更新」的对照）
  python3 -u rd_workshop/walkforward_oos.py --folds 6 --test-days 21
"""
from __future__ import annotations

import argparse
import gc
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import TimeSeriesSplit

ROOT = Path(os.environ.get("ALPHAPILOT_ROOT") or "/home/ubuntu/alphapilot")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

# 生产权威特征管线（与 train_v25.py 同源，绝不另起一套）
from train_v25 import (  # noqa: E402
    CHIP,
    CHIP_FACTORS,
    DERIVED_COLS,
    EARLY_STOPPING,
    FORWARD_DAYS,
    N_BOOST_ROUND,
    N_MODELS,
    RAW,
    THRESHOLD,
    apply_lhb_dates,
    bare_code,
    compute_chip_factors,
    compute_optimized_tech,
    load_v3_side_data,
    merge_chip,
    tech_col_names,
)
from auto_factor_engine import derive_factors  # noqa: E402
import features_v2 as ft  # noqa: E402

RUNS_DIR = ROOT / "rd_workshop" / "walkforward_runs"
PROD_MODELS = ROOT / "models"

CAND_PARAMS = {
    "max_depth": 4, "learning_rate": 0.05, "subsample": 0.6, "colsample_bytree": 0.6,
    "min_child_weight": 5, "tree_method": "hist",
    "scale_pos_weight": 8.0, "eval_metric": "auc", "objective": "binary:logistic",
}


def _rss_gb() -> float:
    """当前进程 RSS（GB），用于诊断内存峰值；读取失败返回 0。"""
    try:
        with open("/proc/self/statm", encoding="ascii") as fh:
            pages = int(fh.read().split()[1])
        return pages * os.sysconf("SC_PAGE_SIZE") / 1e9
    except Exception:  # noqa: BLE001
        return 0.0


# ────────────────────────────── 面板构建 ──────────────────────────────

def _kline_frame() -> pd.DataFrame:
    for p in (ROOT / "data" / "kline_cache" / "kline_all.parquet", ROOT / "kline_all.parquet"):
        if p.exists():
            df = pd.read_parquet(p)
            df["symbol"] = df["symbol"].astype(str).str[-6:]
            df["date"] = df["date"].astype(str).str[:10]
            return df
    raise SystemExit("missing kline_all.parquet")


def build_panel(max_stocks: int, extra_path: str | None, forward_days: int, threshold: float):
    """一次性建好带标签的横截面面板；特征列口径 = 生产 opt_set。"""
    fund_flow, margin, event, fundamentals, lhb_hist = load_v3_side_data()

    extra_df, extra_cols = None, []
    if extra_path:
        from rd_workshop.normalize_factors import load_and_normalize

        extra_df = load_and_normalize(Path(extra_path))
        extra_cols = [c for c in extra_df.columns if c not in ("date", "symbol")]
        print(f"  额外 RD 因子: {len(extra_cols)} 列", flush=True)

    kdf = _kline_frame()
    symbols = sorted(kdf["symbol"].unique())
    if max_stocks and max_stocks < len(symbols):
        rng = np.random.default_rng(42)
        symbols = sorted(rng.choice(symbols, size=max_stocks, replace=False).tolist())

    tech_cols = tech_col_names()
    panels: list[pd.DataFrame] = []
    base_cols: list[str] | None = None
    skipped = 0

    for i, sym in enumerate(symbols):
        sdf = kdf[kdf["symbol"] == sym].sort_values("date").reset_index(drop=True)
        if len(sdf) < 120:
            skipped += 1
            continue
        code = bare_code(sym)
        try:
            ev = event.get(code)
            feats = ft.build_full_features_v2(
                sdf,
                fundamentals=fundamentals.get(code),
                fund_hist=fund_flow.get(code),
                margin_data=margin.get(code),
                event_data=ev,
                has_forecast=bool(ev and ev.get("has_forecast")),
                yjyg_max_change=float((ev or {}).get("yjyg_max_change", 0) or 0),
            )
            if feats is None or len(feats) < 40:
                skipped += 1
                continue
            feats = apply_lhb_dates(feats, lhb_hist.get(code))
            feats = merge_chip(feats, code)
            if base_cols is None:
                base_cols = [c for c in feats.columns if c not in RAW]
                print(f"  动态基础特征: {len(base_cols)}", flush=True)

            feats = compute_optimized_tech(feats)
            derived = derive_factors(feats)
            full = pd.concat([feats, derived], axis=1)
            full = full.loc[:, ~full.columns.duplicated()]
            full = compute_chip_factors(full)
            if extra_cols:
                from rd_workshop.normalize_factors import merge_extra_factors

                full = merge_extra_factors(full, code, extra_df, extra_cols)

            needed = list(dict.fromkeys(base_cols + DERIVED_COLS + CHIP_FACTORS + tech_cols + extra_cols))
            for c in needed:
                if c not in full.columns:
                    full[c] = 0.0
                else:
                    full[c] = full[c].fillna(0)

            full["date"] = full["date"].astype(str).str[:10]
            full["symbol"] = code
            full["ret_fwd"] = full["close"].shift(-forward_days) / full["close"] - 1
            full["label"] = (full["ret_fwd"] > threshold).astype(float)
            full = full.replace([np.inf, -np.inf], np.nan)

            keep = ["date", "symbol", "close", "open", "ret_fwd", "label"] + needed
            vo = full[keep].dropna(subset=["ret_fwd", "label"] + needed)
            if len(vo) >= 10:
                panels.append(vo)
            else:
                skipped += 1
        except Exception as exc:  # noqa: BLE001
            skipped += 1
            if skipped <= 3:
                print(f"  [skip] {sym}: {exc}", flush=True)
        if (i + 1) % 500 == 0:
            print(f"  面板 {i+1}/{len(symbols)} | 已收 {len(panels)} 只 | skip {skipped}", flush=True)
            gc.collect()

    if not panels:
        raise SystemExit("no panels built")
    panel = pd.concat(panels, ignore_index=True)
    panel["date"] = panel["date"].astype(str).str[:10]
    # ── 内存优化（2026-09-13 OOM 修复）──
    # 原实现保留 float64 全表（2.0M 行 × 106 列 ≈ 1.7GB），叠加每折整表副本后在
    # 3.6GB 机器上触发 OOM（实测 anon-rss 3.14GB 被杀）。这里只留必要列并降 float32。
    keep_cols = ["date", "symbol", "ret_fwd", "label"] + [c for c in needed if c in panel.columns]
    panel = panel[keep_cols].copy()
    for c in needed:
        if c in panel.columns and panel[c].dtype != np.float32:
            panel[c] = panel[c].astype(np.float32)
    print(f"  面板合计 {len(panel)} 行 / {panel['symbol'].nunique()} 只 / "
          f"{panel['date'].min()}~{panel['date'].max()} | 特征 {len(needed)} 列 "
          f"| 表内存 {panel.memory_usage(deep=True).sum() / 1e9:.2f} GB", flush=True)
    return panel, needed, extra_cols


# ────────────────────────────── 折 / 训练 ──────────────────────────────

def make_folds(all_dates: list[str], end: str, n_folds: int, test_days: int):
    ds = [d for d in all_dates if d <= end]
    folds = []
    for k in range(n_folds):
        hi = len(ds) - k * test_days
        lo = hi - test_days
        if lo < 0:
            break
        chunk = ds[lo:hi]
        if chunk:
            folds.append({"test_start": chunk[0], "test_end": chunk[-1], "days": chunk})
    return list(reversed(folds))


def _train_cutoff(all_dates: list[str], test_start: str, purge_days: int) -> str | None:
    """训练截止日 = 测试窗之前、再去掉 purge_days 个交易日（防 T+H 标签越界）。

    日期为 'YYYY-MM-DD'，字符串比较即时序比较；返回 None 表示无可用训练日。
    """
    prior = [d for d in all_dates if d < test_start]
    if not prior:
        return None
    if purge_days > 0:
        if len(prior) <= purge_days:
            return None
        prior = prior[:-purge_days]
    return prior[-1]


def _train_positions(
    date_arr: np.ndarray, sym_arr: np.ndarray, cutoff: str, train_tail: int
) -> np.ndarray:
    """返回训练集的行位索引：date<=cutoff，且每股只保留最后 train_tail 行。

    面板已按 symbol 连续排列（build_panel 逐 symbol concat），故同一 symbol 的行在
    `idx` 中是一段连续区间，直接对每段取尾部即可 —— 无需 groupby / 整表复制。
    """
    idx = np.flatnonzero(date_arr <= cutoff)
    if idx.size == 0 or not train_tail or train_tail <= 0:
        return idx
    s = sym_arr[idx]
    bnd = np.flatnonzero(s[1:] != s[:-1]) + 1
    starts = np.concatenate(([0], bnd))
    ends = np.concatenate((bnd, [idx.size]))
    keep = []
    for a, b in zip(starts, ends):
        if (b - a) > train_tail:
            a = b - train_tail
        keep.append(idx[a:b])
    return np.concatenate(keep) if keep else idx[:0]


def _fit_candidate(X: np.ndarray, y: np.ndarray, n_models: int):
    """复刻 train_v25.train_ensemble 的口径，但把模型留在内存（不影响生产 models/）。"""
    tscv = TimeSeriesSplit(n_splits=n_models)
    boosters, aucs = [], []
    for i, (tr, va) in enumerate(tscv.split(X)):
        p = dict(CAND_PARAMS)
        p["seed"] = 42 + i * 100
        dtrain = xgb.DMatrix(X[tr], label=y[tr])
        dval = xgb.DMatrix(X[va], label=y[va])
        b = xgb.train(p, dtrain, num_boost_round=N_BOOST_ROUND,
                      evals=[(dval, "val")], early_stopping_rounds=EARLY_STOPPING,
                      verbose_eval=False)
        pred = b.predict(dval)
        if len(set(y[va])) > 1:
            aucs.append(float(roc_auc_score(y[va], pred)))
        boosters.append(b)
    return boosters, aucs


def _predict_ensemble(
    boosters: list[xgb.Booster],
    X: np.ndarray,
    feature_names: list[str],
) -> np.ndarray | None:
    """对一组 booster 取均值预测（输入已是按 `feature_names` 排好的 float32 矩阵）。

    生产冻结模型 `.ubj` 自带特征名，必须按名取列并回填 `feature_names=`，
    否则 xgboost 会因「DMatrix 无特征名」直接抛 ValueError。
    候选模型用 numpy 训练、自身无名，回退用传入的 `feature_names` 顺序。
    """
    if not boosters:
        return None
    posmap = {c: i for i, c in enumerate(feature_names)}
    total, n = None, 0
    for b in boosters:
        cols = list(getattr(b, "feature_names", None) or []) or list(feature_names)
        if any(c not in posmap for c in cols):
            return None
        pos = [posmap[c] for c in cols]
        dmat = xgb.DMatrix(X[:, pos], feature_names=cols)
        pred = b.predict(dmat)
        total = pred if total is None else total + pred
        n += 1
    return total / n if n else None


def _load_prod_boosters() -> tuple[list[xgb.Booster], str]:
    bs, tag = [], "missing"
    for i in (1, 2, 3):
        p = PROD_MODELS / f"v25_opt_ensemble_{i}.ubj"
        if p.exists():
            b = xgb.Booster()
            b.load_model(str(p))
            bs.append(b)
    if bs:
        tag = f"{len(bs)} models"
    return bs, tag


def _metrics(y_bin: np.ndarray, y_ret: np.ndarray, pred: np.ndarray) -> dict:
    from scipy.stats import spearmanr

    out: dict = {"n": int(len(pred))}
    out["auc"] = float(roc_auc_score(y_bin, pred)) if len(set(y_bin.tolist())) > 1 else None
    r = spearmanr(pred, y_ret).correlation
    out["rank_ic"] = float(r) if np.isfinite(r) else None
    base = float(np.mean(y_ret) * 100)
    out["base_ret_pct"] = base
    for tag, frac in (("top5", 0.05), ("top10", 0.10)):
        k = max(1, int(len(pred) * frac))
        idx = np.argsort(-pred)[:k]
        out[f"{tag}_ret_pct"] = float(np.mean(y_ret[idx]) * 100)
        out[f"{tag}_excess_pct"] = out[f"{tag}_ret_pct"] - base
    return out


# ────────────────────────────── 主流程 ──────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="历史 walk-forward OOS：候选 vs 冻结生产（同折配对）")
    ap.add_argument("--folds", type=int, default=6, help="滚动折数")
    ap.add_argument("--test-days", type=int, default=21, help="每折测试交易日数")
    ap.add_argument("--end", default="", help="最后测试日（默认=数据最大日）")
    ap.add_argument("--train-tail", type=int, default=180, help="每折训练每股截尾（对齐生产 tail(180)）")
    ap.add_argument("--max-stocks", type=int, default=0, help="限股票数（smoke）")
    ap.add_argument("--extra-factors", default="", help="RD 增量因子（归一化 parquet/csv）")
    ap.add_argument("--forward-days", type=int, default=FORWARD_DAYS)
    ap.add_argument("--threshold", type=float, default=THRESHOLD)
    ap.add_argument("--run-id", default="")
    args = ap.parse_args()

    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = RUNS_DIR / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=== 历史 walk-forward OOS（候选 vs 冻结生产）===", flush=True)
    panel, needed, extra_cols = build_panel(
        args.max_stocks, args.extra_factors or None, args.forward_days, args.threshold)

    all_dates = sorted(panel["date"].unique())
    end = args.end or all_dates[-1]
    folds = make_folds(all_dates, end, args.folds, args.test_days)
    if not folds:
        raise SystemExit("no folds (数据不足以切出测试窗)")
    print(f"  折数 {len(folds)} | 测试窗 {folds[0]['test_start']}~{folds[-1]['test_end']} | end={end}", flush=True)

    prod_boosters, prod_tag = _load_prod_boosters()
    print(f"  生产冻结模型: {prod_tag}", flush=True)

    # ── 内存优化（2026-09-13 OOM 修复）──
    # 一次性抽出 float32 特征矩阵与元数据，之后按「行位索引」取折，不再每折整表复制。
    Xall = panel[needed].to_numpy(dtype=np.float32)
    y_all = panel["label"].to_numpy(dtype=np.float32)
    ret_all = panel["ret_fwd"].to_numpy(dtype=np.float32)
    date_arr = panel["date"].to_numpy()
    # 面板由 per-symbol 帧按 symbol 顺序 concat 而来 ⇒ 每个 symbol 的行连续、内部按日期升序
    sym_arr = panel["symbol"].to_numpy()
    panel = None
    gc.collect()
    print(f"  特征矩阵 {Xall.shape} float32 = {Xall.nbytes / 1e9:.2f} GB", flush=True)

    fold_reports = []
    for fi, f in enumerate(folds, 1):
        cutoff = _train_cutoff(all_dates, f["test_start"], args.forward_days)
        if cutoff is None:
            print(f"  折{fi} 跳过：无可用训练日", flush=True)
            continue
        tr_idx = _train_positions(date_arr, sym_arr, cutoff, args.train_tail)
        te_mask = (date_arr >= f["test_start"]) & (date_arr <= f["test_end"])
        n_tr, n_te = int(tr_idx.size), int(te_mask.sum())
        if n_tr == 0 or n_te == 0:
            print(f"  折{fi} 跳过：train={n_tr} test={n_te}", flush=True)
            continue
        y_tr = y_all[tr_idx]
        if len(np.unique(y_tr)) < 2:
            print(f"  折{fi} 跳过：训练标签单类", flush=True)
            continue

        Xtr = Xall[tr_idx]
        Xte = Xall[te_mask]
        boosters, val_aucs = _fit_candidate(Xtr, y_tr.astype(float), N_MODELS)
        cand_pred = _predict_ensemble(boosters, Xte, needed)
        prod_pred = _predict_ensemble(prod_boosters, Xte, needed)
        del Xtr
        gc.collect()

        y_bin = y_all[te_mask].astype(float)
        y_ret = ret_all[te_mask].astype(float)
        rep = {
            "fold": fi,
            "test_start": f["test_start"], "test_end": f["test_end"], "test_days": len(f["days"]),
            "train_cutoff": cutoff,
            "n_train": n_tr, "n_test": n_te,
            "candidate_val_auc": [round(a, 4) for a in val_aucs],
            "candidate": _metrics(y_bin, y_ret, cand_pred) if cand_pred is not None else None,
            "incumbent": _metrics(y_bin, y_ret, prod_pred) if prod_pred is not None else None,
        }
        if rep["candidate"] and rep["incumbent"]:
            rep["delta"] = {
                k: (None if rep["candidate"].get(k) is None or rep["incumbent"].get(k) is None
                    else round(rep["candidate"][k] - rep["incumbent"][k], 5))
                for k in ("auc", "rank_ic", "top5_excess_pct", "top10_excess_pct")
            }
        fold_reports.append(rep)
        c, p = rep["candidate"] or {}, rep["incumbent"] or {}
        print(f"  折{fi} {f['test_start']}~{f['test_end']} n={rep['n_test']} | "
              f"cand AUC={c.get('auc')} IC={c.get('rank_ic')} top10ex={c.get('top10_excess_pct')} || "
              f"prod AUC={p.get('auc')} IC={p.get('rank_ic')} top10ex={p.get('top10_excess_pct')} || "
              f"ΔAUC={rep.get('delta', {}).get('auc')} | RSS={_rss_gb():.2f}GB", flush=True)
        del boosters, cand_pred, prod_pred, Xte
        gc.collect()

    # 聚合：配对差均值 + 折间标准误（噪声带）
    agg: dict = {"n_folds": len(fold_reports)}
    for metric in ("auc", "rank_ic", "top5_excess_pct", "top10_excess_pct"):
        diffs = [r["delta"][metric] for r in fold_reports
                 if r.get("delta") and r["delta"].get(metric) is not None]
        if not diffs:
            continue
        arr = np.array(diffs, dtype=float)
        se = float(arr.std(ddof=1) / np.sqrt(len(arr))) if len(arr) > 1 else float("nan")
        agg[metric] = {
            "mean_delta": round(float(arr.mean()), 5),
            "std": round(float(arr.std(ddof=1)), 5) if len(arr) > 1 else None,
            "se": round(se, 5) if np.isfinite(se) else None,
            "noise_band_95": round(1.96 * se, 5) if np.isfinite(se) else None,
            "wins": int((arr > 0).sum()), "n": len(arr),
            "beyond_noise": bool(np.isfinite(se) and arr.mean() > 1.96 * se),
        }

    report = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "run_id": run_id,
        "boundary": {
            "writes_production_models": False, "auto_promotion": False,
            "reads": ["models/*.ubj", "data/kline_cache/kline_all.parquet"],
            "writes": [str(out_dir)],
        },
        "config": {
            "folds": args.folds, "test_days": args.test_days, "end": end,
            "train_tail": args.train_tail, "max_stocks": args.max_stocks,
            "extra_factors": args.extra_factors or None, "extra_factor_cols": extra_cols,
            "forward_days": args.forward_days, "threshold": args.threshold,
            "n_features": len(needed),
        },
        "production_model": {"n_boosters": len(prod_boosters), "tag": prod_tag},
        "folds": fold_reports,
        "aggregate": agg,
        "note": ("历史 walk-forward，用于替代『等 40 个真实交易日』的死循环；"
                 "结论仍是历史 OOS，不自动晋升。"),
    }
    rp = out_dir / "report.json"
    rp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n======== WALK-FORWARD 汇总 ========")
    print(json.dumps(agg, ensure_ascii=False, indent=2))
    print(f"report={rp}")
    print("AUTO_PROMOTION=FORBIDDEN — 仅历史证据，晋升仍需人工")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
