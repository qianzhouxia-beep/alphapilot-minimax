#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A2: 按行情 regime 计算因子条件 IC

对抽样股票 × 交易日：
  - 构建 VM2.5 同款特征行
  - 标签1: fwd1d ret（与训练对齐）
  - 标签2: T+1开→T+2收 可交易收益
  - regime: 上证 5d 收益分桶 severe/weak/normal
  - 输出每个 regime × 因子的 mean IC / ICIR

用法:
  python3 -u scripts/factor_ic_by_regime.py --start 2026-01-01 --end 2026-07-17 --sample 800
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path("/home/ubuntu/alphapilot")
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from vm25_scorer import VM25Scorer  # noqa: E402


def bare(sym: str) -> str:
    s = str(sym).strip()
    if "." in s:
        s = s.split(".")[0]
    return s.zfill(6)[-6:]


def sh_regime_map() -> dict[str, str]:
    out = {}
    try:
        import requests

        r = requests.get(
            "https://push2his.eastmoney.com/api/qt/stock/kline/get",
            params={
                "secid": "1.000001",
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                "klt": 101,
                "fqt": 1,
                "end": "20500101",
                "lmt": 200,
            },
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"},
        )
        rows = (r.json().get("data") or {}).get("klines") or []
        dates, closes = [], []
        for row in rows:
            p = str(row).split(",")
            dates.append(p[0][:10])
            closes.append(float(p[2]))
        s = pd.Series(closes, index=dates)
        ret5 = s.pct_change(5)
        for d, v in ret5.items():
            if pd.isna(v):
                continue
            if v <= -0.05:
                out[d] = "severe"
            elif v <= -0.02:
                out[d] = "weak"
            else:
                out[d] = "normal"
    except Exception as e:
        print("regime warn", e)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-01-01")
    ap.add_argument("--end", default="2026-07-17")
    ap.add_argument("--sample", type=int, default=600)
    ap.add_argument("--step", type=int, default=2, help="每隔几天采一个截面")
    args = ap.parse_args()

    kdf = pd.read_parquet(ROOT / "data/kline_cache/kline_all.parquet")
    kdf["date"] = kdf["date"].astype(str).str[:10]
    kdf["symbol"] = kdf["symbol"].map(bare)
    syms = sorted(kdf["symbol"].unique())
    rng = np.random.default_rng(42)
    sample = list(rng.choice(syms, size=min(args.sample, len(syms)), replace=False))
    by = {
        s: g.sort_values("date").reset_index(drop=True)
        for s, g in kdf[kdf["symbol"].isin(sample)].groupby("symbol")
    }
    dates = sorted(d for d in kdf["date"].unique() if args.start <= d <= args.end)
    dates = dates[:: max(args.step, 1)]
    regimes = sh_regime_map()

    scorer = VM25Scorer(prefer="opt")
    assert scorer.load()
    feats_names = list(scorer.feature_names)

    # regime -> date -> list of (factor_vec dict, y1, y2)
    buckets = defaultdict(lambda: defaultdict(list))

    for di, d in enumerate(dates):
        reg = regimes.get(d, "unknown")
        n_ok = 0
        for sym, g in by.items():
            if d not in set(g["date"].values):
                continue
            ai = int(g.index[g["date"] == d][0])
            if ai < 80 or ai + 2 >= len(g):
                continue
            sub = g.iloc[: ai + 1].tail(180).copy()
            full = scorer.build_features(sub, sym)
            if full is None or len(full) < 1:
                continue
            row = full.iloc[-1]
            # labels
            y1 = float(g.iloc[ai + 1]["close"] / g.iloc[ai]["close"] - 1.0)
            buy = float(g.iloc[ai + 1]["open"])
            sell = float(g.iloc[ai + 2]["close"])
            y2 = sell / buy - 1.0 if buy > 0 else np.nan
            if np.isnan(y2):
                continue
            vec = {c: float(row.get(c, 0.0) or 0.0) for c in feats_names}
            buckets[reg][d].append((vec, y1, y2))
            n_ok += 1
        print(f"  {d} regime={reg} cross={n_ok}", flush=True)

    def ic_table(label_idx: int):
        # label_idx 1 or 2
        result = {}
        for reg, by_date in buckets.items():
            ics = defaultdict(list)
            for d, rows in by_date.items():
                if len(rows) < 30:
                    continue
                ys = np.array([r[label_idx] for r in rows], dtype=float)
                for f in feats_names:
                    xs = np.array([r[0][f] for r in rows], dtype=float)
                    if np.nanstd(xs) < 1e-12:
                        continue
                    corr, _ = spearmanr(xs, ys)
                    if corr == corr:  # not nan
                        ics[f].append(float(corr))
            rows_out = []
            for f, arr in ics.items():
                if len(arr) < 5:
                    continue
                mu = float(np.mean(arr))
                sd = float(np.std(arr)) + 1e-12
                rows_out.append(
                    {
                        "factor": f,
                        "n_days": len(arr),
                        "mean_ic": round(mu, 4),
                        "icir": round(mu / sd, 4),
                        "pos_ic_rate": round(float(np.mean([x > 0 for x in arr])), 4),
                    }
                )
            rows_out.sort(key=lambda x: -abs(x["mean_ic"]))
            result[reg] = rows_out[:40]
        return result

    out = {
        "window": {"start": args.start, "end": args.end},
        "sample_symbols": len(sample),
        "n_feat": len(feats_names),
        "ic_fwd1d": ic_table(1),
        "ic_t1open_t2close": ic_table(2),
        "note": "Top40 |IC| per regime; full unused factors appear with low n_days or absent",
    }
    path = ROOT / "output" / "factor_ic_by_regime.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved", path)
    # print top5 per regime for tradable label
    for reg, rows in out["ic_t1open_t2close"].items():
        print(f"\n=== {reg} tradable IC top8 ===")
        for r in rows[:8]:
            print(f"  {r['factor']}: IC={r['mean_ic']} ICIR={r['icir']}")


if __name__ == "__main__":
    main()
