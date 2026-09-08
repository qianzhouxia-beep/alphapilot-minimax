#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Backfill kline_all.parquet gap (2026-07-24 ~ latest) using akshare/sina source.

Root cause: eastmoney source (scripts/update_kline_cache.py) is blocked from this server IP,
so since 07-24 only a handful of rows/day made it in. akshare (sina) still works, so we
backfill the missing daily rows per symbol.

Usage: python3 scripts/backfill_kline_gap.py [--start 2026-07-24] [--limit N]
"""
import argparse
import os
import time
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.chdir(Path(__file__).resolve().parents[1])

import pandas as pd
from data_fetcher import _get_kline_sina

ROOT = Path("/home/ubuntu/alphapilot")
KLINE_PATH = ROOT / "kline_all.parquet"


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-07-24", help="gap start date")
    ap.add_argument("--limit", type=int, default=0, help="symbols to process (0=all)")
    args = ap.parse_args()

    start_dt = args.start
    start_ymd = start_dt.replace("-", "")

    df = pd.read_parquet(KLINE_PATH)
    df["date"] = df["date"].astype(str).str[:10]
    log(f"loaded {len(df)} rows, latest={df['date'].max()}")

    # target trading dates: all dates >= start present in dataset (existing incomplete ones)
    all_dates = sorted(df["date"].unique())
    target_dates = [d for d in all_dates if d >= start_dt]
    log(f"target dates ({len(target_dates)}): {target_dates[-6:]}")

    # symbols needing backfill: any symbol whose own max date < dataset max
    # (covers both partial-gap and entirely-missing-after-start symbols)
    sym_max = df.groupby("symbol")["date"].max()
    global_max = df["date"].max()
    missing_syms = sym_max[sym_max < global_max].index.tolist()
    log(f"symbols needing backfill: {len(missing_syms)} / {df['symbol'].nunique()}")

    if args.limit:
        missing_syms = missing_syms[: args.limit]

    # fetch per-symbol daily from ~15 days before start (so qfq aligns), keep only missing rows
    new_rows = []
    done, fail = 0, 0
    fetch_start = (datetime.strptime(start_dt, "%Y-%m-%d") - timedelta(days=15)).strftime("%Y%m%d")
    for sym in missing_syms:
        try:
            sdf = _get_kline_sina(sym, fetch_start)
            if sdf is not None and len(sdf):
                sdf["date"] = sdf["date"].astype(str).str[:10]
                sdf["symbol"] = sym
                my_max = sym_max.get(sym, "")
                sdf = sdf[sdf["date"] > my_max]
                if len(sdf):
                    new_rows.append(sdf)
            done += 1
        except Exception as e:
            fail += 1
            if fail <= 5:
                log(f"  FAIL {sym}: {str(e)[:80]}")
        if done % 500 == 0 and done:
            log(f"  {done}/{len(missing_syms)} new_rows={sum(len(x) for x in new_rows)}")
        time.sleep(0.02)

    log(f"done={done} fail={fail} new_row_batches={len(new_rows)}")
    if not new_rows:
        log("nothing to backfill")
        return

    ndf = pd.concat(new_rows, ignore_index=True)
    cols = ["date", "symbol"] + [c for c in ["open", "high", "low", "close", "volume", "amount"] if c in ndf.columns]
    ndf = ndf[cols]
    combined = pd.concat([df, ndf], ignore_index=True)
    combined = combined.drop_duplicates(subset=["date", "symbol"], keep="last")
    combined = combined.sort_values(["symbol", "date"]).reset_index(drop=True)
    combined.to_parquet(KLINE_PATH, index=False)
    log(f"saved {len(combined)} rows (was {len(df)}), +{len(combined) - len(df)}")
    cnt = combined[combined["date"] >= start_dt].groupby("date")["symbol"].nunique()
    log("per-date coverage after backfill:")
    print(cnt.to_string())


if __name__ == "__main__":
    main()
