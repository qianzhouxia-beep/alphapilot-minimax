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
  · 对照：同截断、同配方、**不含**增量因子的现场重训（默认 `--control retrain`）
    （`--control frozen` 读冻结 `.ubj`，仅当模型训练早于测试窗才合法；否则标前视）

输出逐折 AUC / RankIC / TopK 超额，以及**配对差（候选 − 对照）**与逐日
配对差的块自举噪声带 ⇒ 得到「多少提升才算超过噪声」的**数据驱动**门槛，
替代拍脑袋的 40 天。

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
    # ── 内存（2026-09-13 二次 OOM 修复）──
    # 不再累积 per-symbol DataFrame 再 pd.concat（concat 峰值 = 双份 float64 ≈ 3.6GB，实测被 OOM 杀）。
    # 改为逐股只保留 float32 numpy 块，最后 np.concatenate。
    feat_blocks: list[np.ndarray] = []
    y_blocks: list[np.ndarray] = []
    ret_blocks: list[np.ndarray] = []
    date_blocks: list[np.ndarray] = []
    sym_blocks: list[np.ndarray] = []
    n_rows = 0
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

            keep = ["date", "ret_fwd", "label"] + needed
            vo = full[keep].dropna(subset=["ret_fwd", "label"] + needed)
            if len(vo) >= 10:
                feat_blocks.append(vo[needed].to_numpy(dtype=np.float32))
                y_blocks.append(vo["label"].to_numpy(dtype=np.float32))
                ret_blocks.append(vo["ret_fwd"].to_numpy(dtype=np.float32))
                date_blocks.append(vo["date"].to_numpy(dtype="<U10"))
                sym_blocks.append(np.full(len(vo), code, dtype=object))
                n_rows += len(vo)
            else:
                skipped += 1
        except Exception as exc:  # noqa: BLE001
            skipped += 1
            if skipped <= 3:
                print(f"  [skip] {sym}: {exc}", flush=True)
        if (i + 1) % 500 == 0:
            print(f"  面板 {i+1}/{len(symbols)} | 已收 {len(feat_blocks)} 只 | skip {skipped} | "
                  f"累计 {n_rows} 行 RSS={_rss_gb():.2f}GB", flush=True)
            gc.collect()

    if not feat_blocks:
        raise SystemExit("no panels built")
    del kdf, fundamentals, fund_flow, margin, event, lhb_hist
    gc.collect()
    Xall = np.concatenate(feat_blocks) if len(feat_blocks) > 1 else feat_blocks[0]
    y_all = np.concatenate(y_blocks)
    ret_all = np.concatenate(ret_blocks)
    date_arr = np.concatenate(date_blocks)
    sym_arr = np.concatenate(sym_blocks)
    del feat_blocks, y_blocks, ret_blocks, date_blocks, sym_blocks
    gc.collect()
    _dts = date_arr.tolist()  # numpy 2.x 对 '<U10' 不支持 .min()/.max()
    print(f"  面板合计 {len(Xall)} 行 / {len(np.unique(sym_arr))} 只 / "
          f"{min(_dts)}~{max(_dts)} | 特征 {len(needed)} 列 "
          f"| 矩阵 {Xall.nbytes / 1e9:.2f} GB | RSS={_rss_gb():.2f}GB", flush=True)
    return Xall, y_all, ret_all, date_arr, sym_arr, needed, extra_cols


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


def _daily_paired_delta(date_sub: np.ndarray, y_ret: np.ndarray, pred_a, pred_b):
    """按**交易日**配对：逐日算 a−b 的 RankIC 差 与 Top10 超额差（百分点）。

    为什么按日：折内样本高度同期相关，跨折只有 6 个点 ⇒ 「1.96×折间 SE」的
    独立性假设不成立。逐日配对差保留时间序列结构，交给块自举估计噪声带。
    """
    from scipy.stats import spearmanr

    ic, ex = [], []
    for d in pd.unique(date_sub):
        m = date_sub == d
        n = int(m.sum())
        if n < 20:
            continue
        yr = y_ret[m]
        pa, pb = pred_a[m], pred_b[m]
        ra = spearmanr(pa, yr).correlation
        rb = spearmanr(pb, yr).correlation
        if np.isfinite(ra) and np.isfinite(rb):
            ic.append(float(ra - rb))
        k = max(1, int(n * 0.10))
        base = float(np.mean(yr))
        ea = float(np.mean(yr[np.argsort(-pa)[:k]])) - base
        eb = float(np.mean(yr[np.argsort(-pb)[:k]])) - base
        ex.append((ea - eb) * 100.0)
    return np.array(ic, float), np.array(ex, float)


def _block_bootstrap(delta: np.ndarray, block: int, iters: int, seed: int = 7):
    """循环块自举：块长 block ≥ 标签持有期，保住自相关结构。

    返回 dict(mean, se, lo95, hi95, p_beyond0)。`lo95>0` ⇒ 配对差在 95% 下仍为正。
    """
    n = int(delta.size)
    if n < max(4, 2 * block):
        return None
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    off = np.arange(block)[None, :]
    means = np.empty(iters, float)
    for i in range(iters):
        starts = rng.integers(0, n, size=nb)
        idx = (starts[:, None] + off).ravel() % n
        means[i] = delta[idx[:n]].mean()
    lo, hi = np.percentile(means, [2.5, 97.5])
    return {
        "n_days": n,
        "mean": round(float(delta.mean()), 5),
        "se": round(float(means.std(ddof=1)), 5),
        "lo95": round(float(lo), 5),
        "hi95": round(float(hi), 5),
        "p_beyond0": float(np.mean(means > 0)),
    }


def _prod_trained_at() -> str | None:
    """生产冻结模型训练时间（前视护栏用）。"""
    for name in ("v25_meta.json",):
        p = PROD_MODELS / name
        if p.exists():
            try:
                return str(json.loads(p.read_text(encoding="utf-8")).get("trained_at") or "")[:10] or None
            except Exception:  # noqa: BLE001
                return None
    return None


# ────────────────────────────── 主流程 ──────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="历史 walk-forward OOS：候选 vs 冻结生产（同折配对）")
    ap.add_argument("--folds", type=int, default=6, help="滚动折数")
    ap.add_argument("--test-days", type=int, default=21, help="每折测试交易日数")
    ap.add_argument("--end", default="", help="最后测试日（默认=数据最大日）")
    ap.add_argument("--train-tail", type=int, default=180, help="每折训练每股截尾（对齐生产 tail(180)）")
    ap.add_argument("--max-stocks", type=int, default=0, help="限股票数（smoke）")
    ap.add_argument("--extra-factors", default="", help="RD 增量因子（归一化 parquet/csv）")
    ap.add_argument("--control", choices=("retrain", "frozen"), default="retrain",
                    help="对照臂：retrain=同截断同配方重训（无前视，默认）；frozen=读冻结 .ubj（仅当训练早于测试窗才合法）")
    ap.add_argument("--boot-iters", type=int, default=2000, help="块自举次数")
    ap.add_argument("--boot-block", type=int, default=5, help="块自举块长（交易日，应 ≥ 标签持有期）")
    ap.add_argument("--forward-days", type=int, default=FORWARD_DAYS)
    ap.add_argument("--threshold", type=float, default=THRESHOLD)
    ap.add_argument("--run-id", default="")
    args = ap.parse_args()

    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = RUNS_DIR / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=== 历史 walk-forward OOS（候选 vs 冻结生产）===", flush=True)
    Xall, y_all, ret_all, date_arr, sym_arr, needed, extra_cols = build_panel(
        args.max_stocks, args.extra_factors or None, args.forward_days, args.threshold)

    all_dates = sorted(set(date_arr.tolist()))
    end = args.end or all_dates[-1]
    folds = make_folds(all_dates, end, args.folds, args.test_days)
    if not folds:
        raise SystemExit("no folds (数据不足以切出测试窗)")
    print(f"  折数 {len(folds)} | 测试窗 {folds[0]['test_start']}~{folds[-1]['test_end']} | end={end}", flush=True)

    prod_boosters, prod_tag = _load_prod_boosters()
    prod_trained = _prod_trained_at()
    ctrl_mode = args.control
    print(f"  生产冻结模型: {prod_tag} | trained_at={prod_trained} | 对照臂={ctrl_mode}", flush=True)
    gc.collect()

    fold_reports = []
    lookahead_folds: list[int] = []
    all_ic_delta: list[np.ndarray] = []
    all_ex_delta: list[np.ndarray] = []
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

        # 前视护栏：冻结生产模型若训练于本折 cutoff 之后 ⇒ 它见过测试期，本折不可用
        lookahead = bool(
            ctrl_mode == "frozen" and prod_trained and cutoff < prod_trained
        )
        if lookahead:
            lookahead_folds.append(fi)

        # 对照臂必须去掉增量因子列；候选保留全列 —— 唯一差别 = 待测因子
        # （2026-09-13 安慰剂全量曾因两臂同训含噪声的 109 维矩阵 ⇒ Δ≡0 假阴性）
        base_needed = [c for c in needed if c not in extra_cols]
        base_pos = [i for i, c in enumerate(needed) if c not in extra_cols]
        Xtr_full = Xall[tr_idx]
        Xte_full = Xall[te_mask]
        boosters, val_aucs = _fit_candidate(Xtr_full, y_tr.astype(float), N_MODELS)
        cand_pred = _predict_ensemble(boosters, Xte_full, needed)
        if ctrl_mode == "retrain":
            Xtr_base = Xtr_full[:, base_pos]
            Xte_base = Xte_full[:, base_pos]
            ctrl_boosters, _ = _fit_candidate(Xtr_base, y_tr.astype(float), N_MODELS)
            ctrl_pred = _predict_ensemble(ctrl_boosters, Xte_base, base_needed)
            del ctrl_boosters, Xtr_base, Xte_base
        else:
            # 冻结生产模型只认生产特征名；多余列在 _predict_ensemble 里按名对齐
            ctrl_pred = _predict_ensemble(prod_boosters, Xte_full, needed)
        del Xtr_full, Xte_full
        gc.collect()

        y_bin = y_all[te_mask].astype(float)
        y_ret = ret_all[te_mask].astype(float)
        rep = {
            "fold": fi,
            "test_start": f["test_start"], "test_end": f["test_end"], "test_days": len(f["days"]),
            "train_cutoff": cutoff,
            "n_train": n_tr, "n_test": n_te,
            "candidate_val_auc": [round(a, 4) for a in val_aucs],
            "lookahead_risk": lookahead,
            "candidate": _metrics(y_bin, y_ret, cand_pred) if cand_pred is not None else None,
            "incumbent": _metrics(y_bin, y_ret, ctrl_pred) if ctrl_pred is not None else None,
        }
        if rep["candidate"] and rep["incumbent"]:
            rep["delta"] = {
                k: (None if rep["candidate"].get(k) is None or rep["incumbent"].get(k) is None
                    else round(rep["candidate"][k] - rep["incumbent"][k], 5))
                for k in ("auc", "rank_ic", "top5_excess_pct", "top10_excess_pct")
            }
            if cand_pred is not None and ctrl_pred is not None:
                d_ic, d_ex = _daily_paired_delta(date_arr[te_mask], y_ret, cand_pred, ctrl_pred)
                if d_ic.size:
                    all_ic_delta.append(d_ic)
                if d_ex.size:
                    all_ex_delta.append(d_ex)
        fold_reports.append(rep)
        c, p = rep["candidate"] or {}, rep["incumbent"] or {}
        la = " ⚠LOOKAHEAD" if lookahead else ""
        print(f"  折{fi} {f['test_start']}~{f['test_end']} n={rep['n_test']} | "
              f"cand AUC={c.get('auc')} IC={c.get('rank_ic')} top10ex={c.get('top10_excess_pct')} || "
              f"ctrl AUC={p.get('auc')} IC={p.get('rank_ic')} top10ex={p.get('top10_excess_pct')} || "
              f"ΔAUC={rep.get('delta', {}).get('auc')} | RSS={_rss_gb():.2f}GB{la}", flush=True)
        del boosters, cand_pred, ctrl_pred
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

    # 块自举噪声带（不依赖「折独立」假设；块长 ≥ 标签持有期，保住自相关）
    boot: dict = {}
    for name, chunks in (("rank_ic", all_ic_delta), ("top10_excess_pct", all_ex_delta)):
        if chunks:
            b = _block_bootstrap(np.concatenate(chunks), args.boot_block, args.boot_iters)
            if b:
                boot[name] = b

    # 两臂等同性自检：无增量因子 + 同截断重训 ⇒ 候选与对照应逐位相同（Δ≡0）
    arm_parity_ok = None
    if ctrl_mode == "retrain" and not extra_cols:
        arm_parity_ok = all(
            r.get("delta") and all(abs(v) < 1e-9 for v in r["delta"].values() if v is not None)
            for r in fold_reports
        )

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
            "control_arm": ctrl_mode, "boot_block": args.boot_block, "boot_iters": args.boot_iters,
        },
        "production_model": {
            "n_boosters": len(prod_boosters), "tag": prod_tag, "trained_at": prod_trained,
            "lookahead_folds": lookahead_folds,
        },
        "arm_parity_ok": arm_parity_ok,
        "folds": fold_reports,
        "aggregate": agg,
        "block_bootstrap": boot,
        "note": ("历史 walk-forward：两臂同截断同配方，唯一差别 = 待测增量因子；"
                 "噪声带用逐日配对差的块自举（非折间 t 检验）。结论仍是历史 OOS，不自动晋升。"),
    }
    rp = out_dir / "report.json"
    rp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n======== WALK-FORWARD 汇总 ========")
    print(json.dumps(agg, ensure_ascii=False, indent=2))
    if boot:
        print("--- block bootstrap（逐日配对差）---")
        print(json.dumps(boot, ensure_ascii=False, indent=2))
    if lookahead_folds:
        print(f"⚠️ 前视风险折（冻结模型训练晚于该折 cutoff）: {lookahead_folds} —— 该模式下结论不可用")
    if arm_parity_ok is not None:
        print(f"两臂等同性自检（无增量因子）: {'PASS Δ≡0' if arm_parity_ok else 'FAIL 存在臂间偏差'}")
    print(f"report={rp}")
    print("AUTO_PROMOTION=FORBIDDEN — 仅历史证据，晋升仍需人工")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
