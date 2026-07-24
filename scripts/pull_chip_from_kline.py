#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从服务器落盘 K 线（含换手率）本地推演筹码分布，写入 chip_data_all.json。

背景：
  - 云主机访问东财 stock_cyq_em 常被断开
  - 筹码本质是日K+换手率算法，无需外网接口
  - 输出字段对齐现有 chip_data_all.json，供 train_v25 / vm25_scorer 使用

用法:
  python3 -u scripts/pull_chip_from_kline.py
  python3 -u scripts/pull_chip_from_kline.py --lookback 120 --workers 4
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/ubuntu/alphapilot")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)

KLINE = ROOT / "data/kline_cache/kline_all.parquet"
OUT = ROOT / "chip_data_all.json"
OUT2 = ROOT / "data/chip_data_all.json"


def bare(sym: str) -> str:
    s = str(sym).strip()
    if "." in s:
        s = s.split(".")[0]
    for p in ("sh", "sz", "bj", "SH", "SZ", "BJ"):
        s = s.replace(p, "")
    return s.zfill(6)[-6:]


def _prefix(code: str) -> str:
    return "sh" if code.startswith(("5", "6", "9")) else "sz"


def calc_chip_snapshot(df: pd.DataFrame, lookback: int = 120, n_bins: int = 150) -> dict | None:
    """简化版东财 CYQ：衰减旧筹码 + 当日三角分布。"""
    if df is None or len(df) < 30:
        return None
    g = df.sort_values("date").tail(lookback).copy()
    need = ["open", "high", "low", "close", "turnover"]
    if any(c not in g.columns for c in need):
        return None
    for c in need:
        g[c] = pd.to_numeric(g[c], errors="coerce")
    g = g.dropna(subset=need)
    if len(g) < 30:
        return None

    lo = float(g["low"].min())
    hi = float(g["high"].max())
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return None
    # 价格网格
    edges = np.linspace(lo, hi, n_bins + 1)
    centers = (edges[:-1] + edges[1:]) / 2.0
    chips = np.zeros(n_bins, dtype=float)

    for _, row in g.iterrows():
        turn = float(row["turnover"] or 0.0)
        turn = float(np.clip(turn, 0.0, 0.5))  # 极端换手保护
        chips *= 1.0 - turn
        l = float(row["low"])
        h = float(row["high"])
        o = float(row["open"])
        c = float(row["close"])
        if h < l:
            l, h = h, l
        if h <= l + 1e-8:
            # 一字板：全部堆在收盘
            idx = int(np.clip(np.searchsorted(edges, c) - 1, 0, n_bins - 1))
            chips[idx] += turn
            continue
        peak = (o + c + h + l) / 4.0
        # 三角权重落在 [l,h]
        mask = (centers >= l) & (centers <= h)
        if not mask.any():
            idx = int(np.clip(np.searchsorted(edges, c) - 1, 0, n_bins - 1))
            chips[idx] += turn
            continue
        x = centers[mask]
        # 三角：峰在 peak
        left = np.maximum(0.0, (x - l) / max(peak - l, 1e-8))
        right = np.maximum(0.0, (h - x) / max(h - peak, 1e-8))
        w = np.where(x <= peak, left, right)
        s = float(w.sum())
        if s <= 1e-12:
            chips[mask] += turn / mask.sum()
        else:
            chips[mask] += turn * (w / s)

    total = float(chips.sum())
    if total <= 1e-12:
        return None
    close = float(g.iloc[-1]["close"])
    avg_cost = float(np.sum(centers * chips) / total)
    profit_rate = float(np.sum(chips[centers <= close]) / total)

    # 集中度：覆盖 q 比例筹码的最短价格区间相对宽度
    def concentration(q: float) -> float:
        target = total * q
        # 前缀和找最短窗口
        csum = np.cumsum(chips)
        best = None
        j = 0
        for i in range(n_bins):
            while j < n_bins and (csum[j] - (csum[i - 1] if i > 0 else 0.0)) < target:
                j += 1
            if j >= n_bins:
                break
            width = centers[j] - centers[i]
            mid = (centers[j] + centers[i]) / 2.0
            if mid <= 1e-8:
                continue
            conc = width / mid * 100.0
            if best is None or conc < best:
                best = conc
        return float(best if best is not None else 0.0)

    date = str(g.iloc[-1]["date"])[:10]
    code = bare(g.iloc[-1].get("symbol", ""))
    return {
        "code": f"{_prefix(code)}{code}",
        "name": "",
        "date": date,
        "closePrice": round(close, 2),
        "chipProfitRate": round(profit_rate, 4),
        "chipAvgCost": round(avg_cost, 2),
        "chipConcentration90": round(concentration(0.90), 2),
        "chipConcentration70": round(concentration(0.70), 2),
    }


def _one(args):
    sym, sdf, lookback = args
    try:
        snap = calc_chip_snapshot(sdf, lookback=lookback)
        if not snap:
            return None
        return bare(sym), snap
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lookback", type=int, default=120)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0, help="调试：只跑前 N 只")
    args = ap.parse_args()

    if not KLINE.exists():
        print(f"missing {KLINE}", flush=True)
        sys.exit(1)

    print(f"load {KLINE}", flush=True)
    t0 = time.time()
    df = pd.read_parquet(KLINE)
    df["symbol"] = df["symbol"].map(bare)
    df["date"] = df["date"].astype(str).str[:10]
    syms = sorted(df["symbol"].unique())
    if args.limit > 0:
        syms = syms[: args.limit]
    print(f"symbols={len(syms)} lookback={args.lookback}", flush=True)

    out = {}
    # 按股票切片（串行稳；workers>1 时用进程）
    grouped = {s: g for s, g in df[df["symbol"].isin(syms)].groupby("symbol")}
    if args.workers <= 1:
        for i, sym in enumerate(syms):
            r = _one((sym, grouped[sym], args.lookback))
            if r:
                out[r[0]] = r[1]
            if (i + 1) % 500 == 0:
                print(f"  {i+1}/{len(syms)} ok={len(out)}", flush=True)
    else:
        jobs = [(sym, grouped[sym], args.lookback) for sym in syms]
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(_one, j) for j in jobs]
            for i, fut in enumerate(as_completed(futs)):
                r = fut.result()
                if r:
                    out[r[0]] = r[1]
                if (i + 1) % 500 == 0:
                    print(f"  {i+1}/{len(syms)} ok={len(out)}", flush=True)

    if args.limit > 0:
        debug = ROOT / "output" / f"chip_data_sample_{args.limit}.json"
        debug.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        print(
            f"DEBUG limit={args.limit} → 写入 {debug}（不覆盖生产 chip_data_all.json） n={len(out)}",
            flush=True,
        )
        return

    OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    OUT2.parent.mkdir(exist_ok=True)
    OUT2.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(
        f"saved {OUT} n={len(out)} elapsed={time.time()-t0:.0f}s "
        f"asof={datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        flush=True,
    )


if __name__ == "__main__":
    main()
