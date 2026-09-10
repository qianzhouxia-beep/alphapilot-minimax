#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""factor IC evaluator + weight tuner (HK pool, Cursor 2026-09-10).

对池内每只票、每个交易日：算各因子横截面值 vs 前瞻 H 日收益的 rank IC，
聚合 meanIC / ICIR / t。据此生成 factor_weights.json（只留显著因子，方向取符号），
再跑 run_paper 对比基线。

用法:
  python3 _factor_ic.py            # 评估 + 写 data/factor_weights.json
  python3 _factor_ic.py --dry      # 只评估不写
"""
import argparse
import json
import math
import os
import statistics as st

import config as C
import dataio as io
import factors as F


def _ranks(vals: list[float]) -> list[float]:
    """平均秩（处理并列）。"""
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    r = [0.0] * len(vals)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def spearman(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 10:
        return None
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = st.mean(rx), st.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    return num / (dx * dy) if dx and dy else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--h", type=int, default=C.HOLD_DAYS)
    ap.add_argument("--tmin", type=float, default=2.0, help="选因子的 |t| 阈")
    ap.add_argument("--train-frac", type=float, default=1.0,
                    help="仅用前 N 比例的交易日做因子选择（用于样本外检验）")
    ap.add_argument("--start", default=None, help="评估起始交易日")
    ap.add_argument("--end", default=None, help="评估结束交易日")
    args = ap.parse_args()

    kline = io.load(C.F_KLINE, {}) or {}
    south = io.load(C.F_SOUTH, {}) or {}
    pool = io.load(C.F_POOL, {}) or {}
    codes = pool.get("codes") or list(south[max(south.keys())].keys())
    ctx = F.Context(kline, south, codes)
    days = io.trading_days(kline)
    H = args.h

    factors = list(F.REGISTRY.keys())
    ics = {f: [] for f in factors}

    sd = ctx.south_dates
    pit0 = sd[20] if len(sd) > 20 else None
    valid = [di for di in range(len(days) - 1 - H)
             if (pit0 is None or days[di] > pit0)]
    if args.train_frac < 1.0:
        valid = valid[:int(len(valid) * args.train_frac)]
    if valid:
        mid = days[valid[len(valid) // 2]]
        print(f"[ic] valid_days={len(valid)} range={days[valid[0]]}->{days[valid[-1]]} mid={mid}")
    for di in valid:
        d = days[di]
        if args.start and d < args.start:
            continue
        if args.end and d > args.end:
            break
        # 前瞻收益：D+1 开盘买 → D+1+H 收盘卖（按全局交易日对齐）
        buy_d, sell_d = days[di + 1], days[di + 1 + H]
        pit = ctx.pool_for(d)
        fwd = {}
        for c in pit:
            km = ctx.kidx.get(c)
            if not km or buy_d not in km or sell_d not in km:
                continue
            o = kline[c][km[buy_d]]["o"]
            cl = kline[c][km[sell_d]]["c"]
            if o and cl:
                fwd[c] = cl / o - 1.0
        if len(fwd) < 30:
            continue
        for f in factors:
            vals = F.REGISTRY[f]["fn"](ctx, d)
            xs, ys = [], []
            for c, v in vals.items():
                if c in fwd and v is not None:
                    xs.append(v)
                    ys.append(fwd[c])
            ic = spearman(xs, ys)
            if ic is not None:
                ics[f].append(ic)

    # 聚合
    print(f"== factor IC vs fwd{H} (pool n={len(codes)}, days={len(days)}) ==")
    print(f"{'factor':16s} {'n_day':>6s} {'meanIC':>8s} {'ICIR':>7s} {'t':>7s} {'pos%':>6s} {'dir':>4s}")
    weights = {}
    rows = []
    for f in factors:
        s = ics[f]
        if len(s) < 8:
            print(f"{f:16s}   skip (n_day={len(s)})")
            continue
        mu = st.mean(s)
        sd = st.stdev(s) if len(s) > 1 else 0.0
        icir = mu / sd if sd else 0.0
        tt = mu / sd * math.sqrt(len(s)) if sd else 0.0
        pos = sum(1 for x in s if x > 0) / len(s) * 100
        d = 1 if mu > 0 else -1
        mark = "***" if abs(tt) >= args.tmin else ""
        print(f"{f:16s} {len(s):6d} {mu:8.4f} {icir:7.2f} {tt:7.2f} {pos:5.1f}% {d:+d} {mark}")
        rows.append((f, mu, tt, len(s)))
        if abs(tt) >= args.tmin:
            weights[f] = {"w": round(abs(mu), 4), "dir": d, "t": round(tt, 2)}

    # 归一到 max
    if weights:
        mx = max(v["w"] for v in weights.values())
        for v in weights.values():
            v["w"] = round(v["w"] / mx, 4)
    print(f"\n[tuned] {len(weights)} factors pass |t|>={args.tmin}: "
          f"{sorted(weights.keys(), key=lambda k:-weights[k]['w'])}")

    # split-half 稳定性（防过拟合）
    print("\n== split-half meanIC (first/second) for selected ==")
    for f in weights:
        s = ics[f]
        h = len(s) // 2
        print(f"{f:16s} first={st.mean(s[:h]):+.4f} second={st.mean(s[h:]):+.4f}")

    if not args.dry and weights:
        io.save_atomic(weights, C.F_WEIGHTS)
        print(f"\n[tuned] weights -> {C.F_WEIGHTS}")


if __name__ == "__main__":
    main()
