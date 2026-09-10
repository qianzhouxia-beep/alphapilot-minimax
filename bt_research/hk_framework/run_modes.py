#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_modes: 在扩展样本上对比 长多 / 多空 / 多头+指数对冲 三模式。

用法:
  python3 run_modes.py [--start YYYY-MM-DD] [--top 10]
"""
import argparse
import json

import config as C
import dataio as io
import factors as F
import signals as S
from paper_ls import LongShortEngine


def build_ctx():
    kline = io.load(C.F_KLINE, {}) or {}
    south = io.load(C.F_SOUTH, {}) or {}
    pool = io.load(C.F_POOL, {}) or {}
    codes = pool.get("codes") or list(south[max(south.keys())].keys())
    return F.Context(kline, south, codes), kline


def warm_start(days, ctx, start=None):
    idx = 130
    sd = ctx.south_dates
    if sd:
        need = sd[min(20, len(sd) - 1)]
        while idx < len(days) and days[idx] <= need:
            idx += 1
    hist_start = 130  # kline 120d + buffer
    idx = max(idx, hist_start)
    if start and start in days:
        idx = days.index(start)
    return idx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=None)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--bottom", type=int, default=10)
    ap.add_argument("--hold", type=int, default=C.HOLD_DAYS)
    args = ap.parse_args()

    ctx, kline = build_ctx()
    days = io.trading_days(kline)
    si = warm_start(days, ctx, args.start)
    print(f"[modes] universe={len(ctx.pool)} days={len(days)} "
          f"window={days[si]}→{days[-1]} hold={args.hold}d top={args.top}", flush=True)

    results = {}
    modes = [
        ("long_only",  dict(mode="long_only", top_n=args.top, bottom_n=0,
                            max_pos=args.top)),
        ("long_short", dict(mode="long_short", top_n=args.top, bottom_n=args.bottom,
                            max_pos=args.top + args.bottom, borrow_annual=0.03)),
        ("long_hedge", dict(mode="long_hedge", top_n=args.top, bottom_n=0,
                            max_pos=args.top + 1, hedge_code="02800", hedge_borrow=0.01)),
    ]
    for name, kw in modes:
        eng = LongShortEngine(hold_days=args.hold, **kw)
        summ = eng.run(ctx, days, lambda c, d: S.pick(c, d, top_n=500), start_idx=si)
        results[name] = summ
        print(f"\n== {name} ==\n{json.dumps(summ, ensure_ascii=False, indent=1)}", flush=True)

    # 汇总表
    print("\n== 对比 ==")
    print(f"{'mode':12s} {'tot_ret':>9s} {'sharpe':>7s} {'maxDD':>8s} {'trades':>7s} {'win':>6s} {'long_avg':>9s} {'short_avg':>10s}")
    for name, s in results.items():
        print(f"{name:12s} {s['total_return']*100:8.2f}% {s['sharpe']:7.2f} {s['max_dd']*100:7.2f}% "
              f"{s['n_trades']:7d} {s['win_rate']*100:5.0f}% {s['long_avg']*100:8.2f}% {s['short_avg']*100:9.2f}%")
    io.save_atomic(results, C.OUT + "/modes_result.json")
    print(f"\n[modes] -> {C.OUT}/modes_result.json")


if __name__ == "__main__":
    main()
