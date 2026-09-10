#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补齐南向历史截面里出现、但当前 K 线缺失的代码（消除「退出港股通」存活偏差）。"""
import json
import time

import config as C
import dataio as io
import sources as SR

N = 600


def main():
    kline = io.load(C.F_KLINE, {}) or {}
    south = io.load(C.F_SOUTH, {}) or {}
    u = set()
    for d in south:
        u |= set(south[d].keys())
    miss = sorted(u - set(kline.keys()))
    print(f"union={len(u)} have={len(kline)} missing={len(miss)}")
    ok = 0
    for i, c in enumerate(miss, 1):
        try:
            bars = SR.fetch_hk_kline(c, n=N)
            if bars:
                kline[c] = bars
                ok += 1
        except Exception as e:  # noqa: BLE001
            print(" fail", c, str(e)[:50])
        if i % 25 == 0:
            io.save_atomic(kline, C.F_KLINE)
            print(f"  {i}/{len(miss)} ok={ok}", flush=True)
        time.sleep(0.12)
    io.save_atomic(kline, C.F_KLINE)
    print(f"done: +{ok} codes, total={len(kline)}")


if __name__ == "__main__":
    main()
