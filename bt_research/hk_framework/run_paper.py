#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_paper: 用现有数据跑一遍纸盘（回放/基线）。

用法:
  python3 run_paper.py                 # 港股，自动窗口
  python3 run_paper.py --start 2026-07-15
"""
import argparse
import json
import os

import config as C
import dataio as io
import factors as F
import signals as S
from paper import PaperEngine


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=None, help="起始交易日 YYYY-MM-DD")
    args = ap.parse_args()

    kline = io.load(C.F_KLINE, {}) or {}
    south = io.load(C.F_SOUTH, {}) or {}
    pool = io.load(C.F_POOL, {}) or {}
    if not kline or not south:
        raise SystemExit("缺数据：先跑 daily_update.py 或放入 data/kline.json + southbound_hist.json")
    codes = pool.get("codes") or list(south[max(south.keys())].keys())
    ctx = F.Context(kline, south, codes)
    days = io.trading_days(kline)
    sd = ctx.south_dates

    # 起始：南向 20 日预热 + 价格 120 日预热
    start_idx = 120
    if sd:
        min_date = sd[min(20, len(sd) - 1)]
        while start_idx < len(days) and days[start_idx] <= min_date:
            start_idx += 1
    if args.start and args.start in days:
        start_idx = days.index(args.start)
    print(f"[paper] universe={len(codes)} trade_days={len(days)} start={days[start_idx]} "
          f"end={days[-1]} hold={C.HOLD_DAYS}d", flush=True)

    eng = PaperEngine()
    summary = eng.run(ctx, days, S.pick, start_idx=start_idx)
    print("\n== summary ==")
    print(json.dumps(summary, ensure_ascii=False, indent=1))

    if eng.ledger:
        rets = [l["ret"] for l in eng.ledger]
        print(f"\n[ledger] {len(eng.ledger)} trades, avg={summary['avg_ret']*100:+.2f}%, "
              f"win={summary['win_rate']*100:.0f}%")
        # 年度/月度粗看：按 entry_month 汇总
        bym = {}
        for l in eng.ledger:
            bym.setdefault(l["entry_date"][:7], []).append(l["ret"])
        for m in sorted(bym):
            r = bym[m]
            print(f"  {m}: n={len(r):3d} avg={sum(r)/len(r)*100:+.2f}% win={sum(1 for x in r if x>0)/len(r)*100:.0f}%")

    eng.persist(summary)
    print(f"\n[paper] state -> {C.F_STATE}  ledger -> {C.F_LEDGER}  equity -> {C.F_EQUITY}")


if __name__ == "__main__":
    main()
