#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同步根目录 kline_all.parquet <- data/kline_cache/kline_all.parquet

背景: 根目录 kline_all.parquet 原由 update_kline_cache.py (东财源) 维护,
      2026-08-04 起东财接口被风控, 每轮仅成功 10-20 只 → 根目录文件覆盖崩坏.
      而 data/kline_cache/kline_all.parquet 由 fix_kline_server.py (mootdx 通达信直连)
      每天 16:15 全市场补全, 覆盖率 4991/4991, 是最新最全的数据源.
      本脚本在 fix_kline_server 之后将完整数据同步到根目录, 保证所有引用根目录
      文件的模块 (vol_gate/build_kline5m/backtest) 都拿到完整数据.
"""
import shutil, sys, time
from pathlib import Path

ROOT = Path("/home/ubuntu/alphapilot")
SRC = ROOT / "data/kline_cache/kline_all.parquet"
DST = ROOT / "kline_all.parquet"

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def main():
    if not SRC.exists():
        log(f"ERROR: 源文件不存在 {SRC}")
        sys.exit(1)
    # 原子替换: 先写临时文件再 rename
    tmp = DST.with_suffix(".parquet.tmp")
    shutil.copy2(SRC, tmp)
    tmp.replace(DST)
    log(f"OK: 已同步 {SRC} -> {DST} ({DST.stat().st_size/1024/1024:.1f} MB)")

if __name__ == "__main__":
    main()

