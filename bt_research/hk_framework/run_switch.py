#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_switch: 对比「多空常开」vs「市场风险开关（regime 切换）」在港股的净收益。

用法: python3 run_switch.py [--start YYYY-MM-DD] [--hold 15]
"""
import argparse
import json

import config as C
import dataio as io
import factors as F
import regime as R
import signals as S
from paper_ls import LongShortEngine


def build_ctx():
    kline = io.load(C.F_KLINE, {}) or {}
    south = io.load(C.F_SOUTH, {}) or {}
    pool = io.load(C.F_POOL, {}) or {}
    codes = pool.get("codes") or list(south[max(south.keys())].keys())
    return F.Context(kline, south, codes)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=None)
    ap.add_argument("--hold", type=int, default=15)
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()

    ctx = build_ctx()
    days = io.trading_days(ctx.kline)
    sd = ctx.south_dates
    need = sd[20] if len(sd) > 20 else days[0]
    idx = 130
    while idx < len(days) and days[idx] <= need:
        idx += 1
    if args.start and args.start in days:
        idx = days.index(args.start)
    print(f"[switch] window={days[idx]}→{days[-1]} hold={args.hold}", flush=True)

    # regime 分布
    on = off = 0
    for d in days[idx:]:
        tr, br = R.index_trend(ctx, d), R.breadth(ctx, d)
        risk_on = (tr == 1) or (tr == 0 and (br or 0) >= 0.5)
        on += 1 if risk_on else 0
        off += 0 if risk_on else 1
    print(f"[switch] regime days risk_on={on} risk_off={off}", flush=True)

    sc = lambda c, d: S.pick(c, d, top_n=500)
    cfgs = [
        ("LS_both",   dict(mode="long_short", top_n=args.top, bottom_n=args.top,
                           max_pos=2 * args.top), R.make_gate(mode="both")),
        ("switch",    dict(mode="long_short", top_n=args.top, bottom_n=args.top,
                           max_pos=2 * args.top), R.make_gate(mode="switch")),
        ("short_only", dict(mode="long_short", top_n=args.top, bottom_n=args.top,
                            max_pos=2 * args.top), R.make_gate(mode="shortonly")),
    ]
    out = {}
    print(f"\n{'name':11s} {'tot':>8s} {'sharpe':>7s} {'maxDD':>8s} {'n':>5s} {'long_n':>6s} {'long_avg':>9s} {'short_n':>7s} {'short_avg':>10s}")
    for name, kw, gate in cfgs:
        e = LongShortEngine(hold_days=args.hold, **kw)
        s = e.run(ctx, days, sc, start_idx=idx, gate=gate)
        out[name] = s
        print(f"{name:11s} {s['total_return']*100:+7.2f}% {s['sharpe']:7.2f} {s['max_dd']*100:7.2f}% "
              f"{s['n_trades']:5d} {s['long_n']:6d} {s['long_avg']*100:8.2f}% {s['short_n']:7d} {s['short_avg']*100:9.2f}%")
    io.save_atomic(out, C.OUT + "/switch_result.json")
    print(f"\n[switch] -> {C.OUT}/switch_result.json")


if __name__ == "__main__":
    main()
