#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""daily_update: 每日数据管线（盘后跑，L1-L6 纪律：原子写 + readiness 闸）。

步骤:
  1) 取池（首次从南向持股 bootstrap，之后沿用 + 新截面补充）
  2) 增量刷新日K（HK）
  3) 补齐南向持股截面（最近 N 个交易日）
  4) 重建池（流动性 + K线完整度）
  5) 写 readiness.json（供告警/巡检）
  6) 可选：算当日打分写出 picks

用法:
  python3 daily_update.py               # 全量日更
  python3 daily_update.py --no-kline    # 跳过K线刷新（离线/回填）
  python3 daily_update.py --picks       # 额外产出当日选股
"""
import argparse
import datetime as dt
import json

import config as C
import dataio as io
import factors as F
import signals as S
import sources as SR


def _recent_south_dates(n: int = 75) -> list[str]:
    """最近 n 个自然日候选（南向按交易日；缺的会被增量逻辑跳过/补齐）。"""
    today = dt.date.today()
    out = []
    for k in range(n, 0, -1):
        d = today - dt.timedelta(days=k)
        if d.weekday() < 5:
            out.append(d.strftime("%Y-%m-%d"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-kline", action="store_true")
    ap.add_argument("--picks", action="store_true")
    ap.add_argument("--market", default=C.MARKET)
    args = ap.parse_args()

    report = {"ts": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "market": args.market}

    south = io.load(C.F_SOUTH, {}) or {}
    kline = io.load(C.F_KLINE, {}) or {}
    pool = io.load(C.F_POOL, {}) or {}

    # 1) 池代码（首次：从南向最新截面 bootstrap）
    codes = pool.get("codes") or []
    if not codes and south:
        codes = list(south[max(south.keys())].keys())
    report["n_pool_in"] = len(codes)

    # 2) K线
    if not args.no_kline and codes:
        r = SR.refresh_kline_tail(codes, market=args.market)
        report["kline"] = r
        kline = io.load(C.F_KLINE, {}) or {}

    # 3) 南向截面补齐
    r = SR.update_southbound(_recent_south_dates())
    report["southbound"] = r
    south = io.load(C.F_SOUTH, {}) or {}

    # 4) 重建池
    if kline and south:
        pool = SR.build_pool(kline, south)
        report["n_pool_out"] = pool["n"]

    # 5) readiness
    latest_k = max((b[-1]["d"] for b in kline.values() if b), default=None)
    latest_s = max(south.keys()) if south else None
    ready = bool(latest_k and latest_s and pool.get("n", 0) > 50)
    readiness = {"ready": ready, "latest_kline": latest_k, "latest_southbound": latest_s,
                 "n_pool": pool.get("n", 0), "ts": report["ts"],
                 "checks": {
                     "kline_ok": bool(latest_k),
                     "south_ok": bool(latest_s),
                     "pool_ok": pool.get("n", 0) > 50,
                 }}
    io.save_atomic(readiness, C.F_READY)
    report["readiness"] = readiness

    # 6) picks
    if args.picks and kline and south and pool.get("codes"):
        ctx = F.Context(kline, south, pool["codes"])
        days = io.trading_days(kline)
        date = days[-1]
        res = S.pick(ctx, date)
        io.save_atomic(res, C.F_PICKS.format(date=date))
        report["picks_date"] = date
        report["picks_top"] = [p["code"] for p in res["picks"][:10]]

    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
