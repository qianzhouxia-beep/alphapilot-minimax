#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extend HK data for a longer-sample swing study (run ON SG).
1) refetch full-pool daily kline N=600 -> overwrite data/kline.json (+ 2800.HK 盈富基金)
2) pull ~250 southbound cross-sections (weekdays going back) -> merge into data/southbound_hist.json
Idempotent/resumable; logs to output/extend.log.
"""
import datetime as dt
import json
import os
import time

import config as C
import dataio as io
import sources as SR

N = 600
NSOUTH = 250


def log(m):
    print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] {m}", flush=True)


def logfile(m):
    log(m)
    os.makedirs(C.OUT, exist_ok=True)
    with open(os.path.join(C.OUT, "extend.log"), "a", encoding="utf-8") as f:
        f.write(f"[{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {m}\n")


def main():
    kline = io.load(C.F_KLINE, {}) or {}
    south = io.load(C.F_SOUTH, {}) or {}
    seed = io.load(os.path.join(C.DATA, "pool_seed_20260908.json"), {}) or {}
    codes = seed.get("codes") or list(south[max(south.keys())].keys())
    codes = list(dict.fromkeys(codes + ["02800"]))   # + 盈富基金（HSI ETF，做对冲用）
    logfile(f"start: codes={len(codes)} south_days={len(south)}")

    # ---- 1) kline N=600 ----
    t0 = time.time()
    upd = 0
    for i, c in enumerate(codes, 1):
        old = kline.get(c) or []
        if len(old) >= N - 5:
            continue
        try:
            bars = SR.fetch_hk_kline(c, n=N)
            if bars:
                kline[c] = bars
                upd += 1
        except Exception as e:  # noqa: BLE001
            pass
        if i % 100 == 0:
            io.save_atomic(kline, C.F_KLINE)
            logfile(f"kline {i}/{len(codes)} upd={upd} el={int(time.time()-t0)}s")
        time.sleep(0.12)
    io.save_atomic(kline, C.F_KLINE)
    logfile(f"kline DONE upd={upd} el={int(time.time()-t0)}s")

    # ---- 2) southbound ~250 weekdays ----
    ref = kline.get("00700") or []
    cal = [b["d"] for b in ref]
    today = dt.date.today().strftime("%Y-%m-%d")
    days = [d for d in cal if d < today][-NSOUTH:]
    t0 = time.time()
    added = 0
    for j, d in enumerate(days, 1):
        if d in south and south[d]:
            continue
        try:
            xs = SR.fetch_south_cross_section(d)
            if xs:
                south[d] = xs
                added += 1
        except Exception as e:  # noqa: BLE001
            logfile(f"  south {d} fail {str(e)[:60]}")
        if j % 20 == 0:
            io.save_atomic(south, C.F_SOUTH)
            logfile(f"south {j}/{len(days)} added={added} el={int(time.time()-t0)}s")
        time.sleep(0.25)
    io.save_atomic(south, C.F_SOUTH)
    logfile(f"south DONE days={len(south)} added={added} el={int(time.time()-t0)}s")

    # rebuild pool + readiness
    if kline and south:
        pool = SR.build_pool(kline, south)
        logfile(f"pool n={pool['n']} date={pool['date']}")


if __name__ == "__main__":
    main()
