#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Track A — 基于当前 Production Model（VM2.5）的因子挖掘与候选提升。

目标：在现有 features_v2 / derive_factors 特征空间上，搜索增量变换因子，
按 IC 筛选后交给晋升适配器做 candidate train_v25 + 可交易 OOS。

不调用 RD-Agent；不写生产 models/。

用法:
  python3 -u rd_workshop/track_a_current_model_uplift.py
  python3 -u rd_workshop/track_a_current_model_uplift.py --sample 200 --top-k 12 --promote
  python3 -u rd_workshop/track_a_current_model_uplift.py --promote --max-stocks 80
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from rd_workshop.normalize_factors import bare_code, _safe_factor_name  # noqa: E402

OUT_DIR = ROOT / "rd_workshop" / "data_support" / "inbound"
TRACK = "track_a_current_model"


def _load_kline_cache() -> dict[str, pd.DataFrame]:
    kf = ROOT / "data" / "kline_cache" / "kline_all.parquet"
    if not kf.exists():
        kf = ROOT / "kline_all.parquet"
    if not kf.exists():
        raise SystemExit(f"missing kline parquet under {ROOT}")
    df = pd.read_parquet(kf)
    cache: dict[str, pd.DataFrame] = {}
    for sym, sdf in df.groupby("symbol"):
        code = bare_code(sym)
        sdf = sdf.sort_values("date").reset_index(drop=True)
        if len(sdf) >= 120:
            cache[code] = sdf
    return cache


def _candidate_transforms(feats: pd.DataFrame) -> pd.DataFrame:
    """在现有特征上行内变换，生成 Track A 候选列（不改生产特征定义）。"""
    out = pd.DataFrame(index=feats.index)
    base_cols = [
        c
        for c in feats.columns
        if c
        not in (
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
            "symbol",
            "outstanding_share",
            "turnover",
        )
        and pd.api.types.is_numeric_dtype(feats[c])
    ]
    # 优先资金/动量相关列
    prefer = [
        c
        for c in base_cols
        if any(
            k in c.lower()
            for k in (
                "main_net",
                "ret_",
                "vol_",
                "rsi",
                "macd",
                "turnover",
                "atr",
                "chip",
                "margin",
                "active",
            )
        )
    ]
    cols = (prefer or base_cols)[:24]
    for c in cols:
        s = pd.to_numeric(feats[c], errors="coerce")
        out[f"{c}__ma3"] = s.rolling(3, min_periods=1).mean()
        out[f"{c}__ma5"] = s.rolling(5, min_periods=1).mean()
        out[f"{c}__diff3"] = s.diff(3)
        out[f"{c}__z20"] = (s - s.rolling(20, min_periods=5).mean()) / (
            s.rolling(20, min_periods=5).std() + 1e-8
        )
    # 少量交叉
    pairs = [
        ("main_net_today", "ret_1d"),
        ("main_net_5d", "vol_ma_ratio"),
        ("rsi", "ret_5d"),
        ("turnover", "atr_pct"),
    ]
    for a, b in pairs:
        if a in feats.columns and b in feats.columns:
            sa = pd.to_numeric(feats[a], errors="coerce")
            sb = pd.to_numeric(feats[b], errors="coerce")
            out[f"{a}_x_{b}"] = sa * sb
    return out.replace([np.inf, -np.inf], np.nan)


def _ic(x: np.ndarray, y: np.ndarray) -> float:
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 30:
        return 0.0
    if np.nanstd(x[m]) < 1e-12 or np.nanstd(y[m]) < 1e-12:
        return 0.0
    r, _ = spearmanr(x[m], y[m])
    return float(r) if np.isfinite(r) else 0.0


def mine_factors(sample: int, min_abs_ic: float, top_k: int) -> tuple[pd.DataFrame, dict]:
    import features_v2 as ft
    from auto_factor_engine import derive_factors
    from train_v25 import (
        CHIP,
        apply_lhb_dates,
        compute_chip_factors,
        compute_optimized_tech,
        load_v3_side_data,
        merge_chip,
    )

    fund_flow, margin, event, fundamentals, lhb_hist = load_v3_side_data()
    cache = _load_kline_cache()
    codes = list(cache.keys())
    rng = np.random.default_rng(42)
    if sample and sample < len(codes):
        codes = list(rng.choice(codes, size=sample, replace=False))

    panels: list[pd.DataFrame] = []
    skipped = 0
    for i, code in enumerate(codes):
        try:
            kl = cache[code].copy()
            kl["date"] = kl["date"].astype(str).str[:10]
            kl = kl.tail(180).reset_index(drop=True)
            feats = ft.build_full_features_v2(
                kl,
                fundamentals=fundamentals.get(code),
                fund_hist=fund_flow.get(code),
                margin_data=margin.get(code),
                event_data=event.get(code),
                has_forecast=bool(event.get(code) and event.get(code).get("has_forecast")),
                yjyg_max_change=float((event.get(code) or {}).get("yjyg_max_change", 0) or 0),
            )
            if feats is None or len(feats) < 40:
                skipped += 1
                continue
            feats = apply_lhb_dates(feats, lhb_hist.get(code))
            feats = merge_chip(feats, code)
            feats = compute_optimized_tech(feats)
            derived = derive_factors(feats)
            full = pd.concat([feats, derived], axis=1)
            full = full.loc[:, ~full.columns.duplicated()]
            full = compute_chip_factors(full)
            cand = _candidate_transforms(full)
            close = pd.to_numeric(full["close"], errors="coerce")
            # 与训练标签对齐：次日涨幅
            y = (close.shift(-1) / close - 1.0).values
            # 可交易近似：T+1 开→T+2 收（用 open/close 近似）
            op = pd.to_numeric(full["open"], errors="coerce")
            y_tr = (close.shift(-2) / op.shift(-1) - 1.0).values
            block = cand.copy()
            block["date"] = full["date"].astype(str).str[:10].values
            block["symbol"] = code
            block["y_fwd1"] = y
            block["y_tradable"] = y_tr
            panels.append(block)
        except Exception:
            skipped += 1
            continue
        if (i + 1) % 50 == 0:
            print(f"  mined {i+1}/{len(codes)} panels={len(panels)} skip={skipped}", flush=True)

    if not panels:
        raise SystemExit("Track A: no panels built")

    panel = pd.concat(panels, ignore_index=True)
    factor_cols = [
        c
        for c in panel.columns
        if c not in ("date", "symbol", "y_fwd1", "y_tradable")
    ]
    rows = []
    for c in factor_cols:
        x = pd.to_numeric(panel[c], errors="coerce").values
        ic1 = _ic(x, panel["y_fwd1"].values)
        ict = _ic(x, panel["y_tradable"].values)
        score = 0.4 * abs(ic1) + 0.6 * abs(ict)
        rows.append(
            {
                "factor": c,
                "ic_fwd1": round(ic1, 4),
                "ic_tradable": round(ict, 4),
                "score": round(score, 4),
            }
        )
    rank = pd.DataFrame(rows).sort_values("score", ascending=False)
    picked = []
    for _, r in rank.iterrows():
        if abs(r["ic_tradable"]) < min_abs_ic and abs(r["ic_fwd1"]) < min_abs_ic:
            continue
        name = r["factor"]
        # 与已选相关去重
        ok = True
        for p in picked:
            a = pd.to_numeric(panel[name], errors="coerce").fillna(0).values
            b = pd.to_numeric(panel[p], errors="coerce").fillna(0).values
            corr = abs(_ic(a, b))
            if corr > 0.85:
                ok = False
                break
        if ok:
            picked.append(name)
        if len(picked) >= top_k:
            break

    if not picked:
        # 放宽：直接取 score top_k
        picked = rank["factor"].head(top_k).tolist()

    wide = panel[["date", "symbol"] + picked].copy()
    rename = {c: _safe_factor_name(f"a_{c}") for c in picked}
    wide = wide.rename(columns=rename)
    meta = {
        "track": TRACK,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sample_stocks": len(codes),
        "skipped": skipped,
        "n_rows": int(len(wide)),
        "picked": [
            {
                "raw": c,
                "export": rename[c],
                **{k: float(rank.loc[rank["factor"] == c, k].iloc[0]) for k in ("ic_fwd1", "ic_tradable", "score")},
            }
            for c in picked
        ],
        "rank_preview": rank.head(30).to_dict(orient="records"),
        "note": "Incremental transforms on current VM2.5 feature space; promotion still required.",
    }
    return wide, meta


def main() -> int:
    ap = argparse.ArgumentParser(description="Track A: uplift factors on current VM2.5")
    ap.add_argument("--sample", type=int, default=300)
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--min-abs-ic", type=float, default=0.01)
    ap.add_argument("--promote", action="store_true", help="chain into promotion adapter")
    ap.add_argument("--max-stocks", type=int, default=0, help="pass to promotion smoke")
    ap.add_argument("--skip-oos", action="store_true")
    args = ap.parse_args()

    print(f"=== {TRACK} ===", flush=True)
    wide, meta = mine_factors(args.sample, args.min_abs_ic, args.top_k)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    factor_path = OUT_DIR / f"{TRACK}_factors_{stamp}.parquet"
    meta_path = OUT_DIR / f"{TRACK}_mine_{stamp}.json"
    wide.to_parquet(factor_path, index=False)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"factors={list(wide.columns)[2:]}")
    print(f"wrote {factor_path}")
    print(f"wrote {meta_path}")

    if args.promote:
        cmd = [
            sys.executable,
            "-u",
            str(ROOT / "rd_workshop" / "run_promotion_adapter.py"),
            "--factors",
            str(factor_path),
            "--skip-normalize",
            "--run-id",
            f"{TRACK}_{stamp}",
        ]
        if args.max_stocks:
            cmd.extend(["--max-stocks", str(args.max_stocks)])
        if args.skip_oos:
            cmd.append("--skip-oos")
        print("RUN:", " ".join(cmd), flush=True)
        return subprocess.call(cmd, cwd=str(ROOT))
    print("Tip: add --promote to train candidate + OOS via promotion adapter")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
