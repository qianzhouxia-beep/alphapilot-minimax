#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sina 5m 增量补口（2026-09-11 Cursor）

背景：build_kline5m.py 走 mootdx/TDX，单源；TDX 宕时当日 5m 直接空
      （2026-09-11 实测 `完成 0 只`，5m 卡在 09-09）。baostock 已被 IP 拉黑。
本脚本用 **新浪 5m**（服务器可达、原生带 amount、volume=股、bar 按结束时刻）
把缺失的近期 bar 并回 data/kline5m/{code}.parquet。

设计（吸取 baostock 事故教训）：
  - **单进程 + 全局最小间隔限速**（默认 0.12s ≈ 8 req/s），退避重试，绝不高并发；
  - **幂等**：只并 datetime 不在现有集合中的 bar，绝不改写已有行；
  - **原子写**：tmp + os.replace；
  - 新浪 5m 覆盖约 21 个交易日（datalen=1023），足够补当日/近缺口；
    6 个月长历史需另源（见 knowledge/inbox/2026-09-11-kline5m-backfill-baostock.md）。

用法：
  python3 fix_kline5m_sina.py --limit 20 --validate      # 小样验证
  python3 fix_kline5m_sina.py                            # 全市场增量
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import threading
import time
import urllib.request

import pandas as pd

ROOT = "/home/ubuntu/alphapilot"
K5 = os.path.join(ROOT, "data/kline5m")
LOG = os.path.join(ROOT, "output/logs/fix_kline5m_sina.log")

COLS = ["open", "close", "high", "low", "vol", "amount", "year", "month",
        "day", "hour", "minute", "datetime", "volume", "symbol"]

_lock = threading.Lock()
_last = [0.0]
_min_interval = 0.12


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _rate_limit() -> None:
    with _lock:
        wait = _min_interval - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()


def _pre(code: str) -> str:
    return "sh" if code[0] in "65" else "sz"


def fetch_sina_5m(code: str, retry: int = 3) -> pd.DataFrame | None:
    url = ("https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_="
           f"/CN_MarketDataService.getKLineData?symbol={_pre(code)}{code}"
           "&scale=5&ma=no&datalen=1023")
    for i in range(retry):
        _rate_limit()
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Referer": "https://finance.sina.com.cn"})
            raw = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore")
            m = re.search(r"\((\[.*\])\)", raw, re.S)
            if not m:
                return None
            arr = json.loads(m.group(1))
            if not arr:
                return None
            df = pd.DataFrame(arr)
            df["datetime"] = pd.to_datetime(df["day"])
            df = df.drop(columns=["day"])          # 原字符串列必须删，否则与下面 dt.day 重名
            for c in ("open", "high", "low", "close", "volume", "amount"):
                df[c] = pd.to_numeric(df[c], errors="coerce")
            df["vol"] = df["volume"].astype("float64")
            df["year"] = df["datetime"].dt.year
            df["month"] = df["datetime"].dt.month
            df["day"] = df["datetime"].dt.day
            df["hour"] = df["datetime"].dt.hour
            df["minute"] = df["datetime"].dt.minute
            df["symbol"] = code
            return df[COLS].dropna(subset=["open", "close"])
        except Exception as e:  # noqa: BLE001
            if i == retry - 1:
                log(f"  FETCH_FAIL {code}: {e!r}")
                return None
            time.sleep(1.0 * (i + 1))
    return None


def merge_one(code: str, dry: bool = False) -> dict:
    p = os.path.join(K5, f"{code}.parquet")
    if not os.path.exists(p) or os.path.getsize(p) == 0:
        return {"code": code, "status": "absent"}
    new = fetch_sina_5m(code)
    if new is None or not len(new):
        return {"code": code, "status": "empty"}
    try:
        old = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        return {"code": code, "status": "read_fail", "err": repr(e)[:80]}
    have = set(pd.to_datetime(old["datetime"]))
    add = new[~new["datetime"].isin(have)]
    if not len(add):
        return {"code": code, "status": "skip"}
    if dry:
        return {"code": code, "status": "dry", "n_add": int(len(add)),
                "add_max": str(add["datetime"].max())}
    out = pd.concat([old, add], ignore_index=True)
    out = out.drop_duplicates(subset=["datetime"], keep="last")
    out = out.sort_values("datetime").reset_index(drop=True)
    tmp = p + ".tmp"
    out.to_parquet(tmp, index=False)
    os.replace(tmp, p)
    return {"code": code, "status": "ok", "n_add": int(len(add)),
            "add_max": str(add["datetime"].max())}


def validate(code: str) -> None:
    """用重叠日比对 Sina vs 现有，确认对齐（close 差异 / volume 比）。"""
    p = os.path.join(K5, f"{code}.parquet")
    if not os.path.exists(p):
        log(f"VALIDATE {code}: absent")
        return
    new = fetch_sina_5m(code)
    if new is None:
        log(f"VALIDATE {code}: fetch empty")
        return
    old = pd.read_parquet(p)
    j = new.merge(old, on="datetime", suffixes=("_s", "_o"))
    if not len(j):
        log(f"VALIDATE {code}: no overlap")
        return
    cd = (j["close_s"] - j["close_o"]).abs().max()
    vr = (j["volume_s"] / j["volume_o"].replace(0, pd.NA)).median()
    amd = ((j["amount_s"] - j["amount_o"]).abs() /
           j["amount_o"].replace(0, pd.NA)).median()
    log(f"VALIDATE {code}: overlap={len(j)} close_maxdiff={cd:.4f} "
        f"vol_ratio_med={vr:.4f} amt_reldiff_med={amd:.5f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--codes", default="")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--min-interval", type=float, default=0.12)
    ap.add_argument("--symbols", default="", help="逗号分隔，覆盖全市场")
    args = ap.parse_args()

    global _min_interval
    _min_interval = args.min_interval

    if args.validate:
        for c in (args.symbols.split(",") if args.symbols else ["600519", "000001", "300750"]):
            validate(c.strip())
        return

    if args.symbols:
        syms = [s.strip() for s in args.symbols.split(",") if s.strip()]
    else:
        syms = sorted(os.path.basename(p)[:6] for p in glob.glob(os.path.join(K5, "*.parquet")))
    if args.limit:
        syms = syms[: args.limit]

    log(f"=== Sina 5m 补口开始 目标 {len(syms)} 只 min_interval={_min_interval} dry={args.dry_run} ===")
    t0 = time.time()
    stat = {"ok": 0, "skip": 0, "empty": 0, "absent": 0, "read_fail": 0, "dry": 0}
    n_add = 0
    for i, c in enumerate(syms, 1):
        r = merge_one(c, dry=args.dry_run)
        stat[r["status"]] = stat.get(r["status"], 0) + 1
        n_add += r.get("n_add", 0)
        if i % 200 == 0 or i == len(syms):
            log(f"  {i}/{len(syms)} ok={stat.get('ok',0)} skip={stat.get('skip',0)} "
                f"empty={stat.get('empty',0)} fail={stat.get('read_fail',0)} "
                f"新增={n_add} ({int(time.time()-t0)}s)")
    log(f"=== 完成 {stat} 新增 {n_add} 行 ({int(time.time()-t0)}s) ===")


if __name__ == "__main__":
    main()
