#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补齐日K：按标的 latest < 源站最新日 强制回填，并重建筹码。"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path("/home/ubuntu/alphapilot")
sys.path.insert(0, str(ROOT))
os_chdir = ROOT
import os

os.chdir(ROOT)

from cache_kline import CACHE_FILE, INDEX_FILE, fetch_stock_kline, load_cache, probe_source_max_date, save_cache


def backfill_missing(workers: int = 20) -> dict:
    t0 = time.time()
    existing = load_cache()
    if existing is None or len(existing) == 0:
        raise RuntimeError("empty kline cache")
    existing = existing.copy()
    existing["date"] = existing["date"].astype(str).str[:10]
    existing["symbol"] = existing["symbol"].astype(str).str.zfill(6)

    src_max = probe_source_max_date()
    if not src_max:
        # fallback today
        src_max = datetime.now().strftime("%Y-%m-%d")
    print(f"source_max={src_max}", flush=True)

    last = existing.groupby("symbol")["date"].max()
    missing = last[last < src_max].index.tolist()
    print(f"symbols={len(last)} missing_asof={len(missing)} already_ok={int((last >= src_max).sum())}", flush=True)
    if not missing:
        return {"ok": True, "filled": 0, "src_max": src_max, "elapsed": 0}

    start_dt = (datetime.strptime(src_max, "%Y-%m-%d") - timedelta(days=5)).strftime("%Y%m%d")
    new_rows = []
    fail = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(fetch_stock_kline, s, start_dt): s for s in missing}
        done = 0
        for f in as_completed(futures):
            sym = futures[f]
            try:
                s2, df = f.result()
            except Exception:
                fail += 1
                df = None
                s2 = sym
            done += 1
            if df is not None and len(df) > 0:
                df = df.copy()
                df["symbol"] = str(s2).zfill(6)
                df["date"] = df["date"].astype(str).str[:10]
                # 该标的只补自己缺的日期
                sym_max = str(last.get(str(s2).zfill(6), "1970-01-01"))
                df_new = df[df["date"] > sym_max]
                if len(df_new) > 0:
                    new_rows.append(df_new)
            if done % 500 == 0 or done == len(missing):
                print(
                    f"  [{int(time.time()-t0)}s] {done}/{len(missing)} new_batches={len(new_rows)} fail={fail}",
                    flush=True,
                )

    filled = 0
    if new_rows:
        new_df = pd.concat(new_rows, ignore_index=True)
        filled = len(new_df)
        print(f"new_rows={filled} dates={sorted(new_df['date'].unique())}", flush=True)
        combined = pd.concat([existing, new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset=["symbol", "date"], keep="last")
        save_cache(combined)
        try:
            combined.to_parquet(Path("kline_all.parquet"), index=False)
            print("synced ./kline_all.parquet", flush=True)
        except Exception as e:
            print(f"sync root fail: {e}", flush=True)
    else:
        print("no new rows fetched", flush=True)

    # verify
    df2 = load_cache()
    df2["date"] = df2["date"].astype(str).str[:10]
    last2 = df2.groupby("symbol")["date"].max()
    n_ok = int((last2 >= src_max).sum())
    print(f"after: asof>={src_max}: {n_ok}/{len(last2)}", flush=True)
    return {
        "ok": n_ok > len(last2) * 0.9,
        "filled": filled,
        "src_max": src_max,
        "asof_ok": n_ok,
        "symbols": len(last2),
        "elapsed": int(time.time() - t0),
        "fail": fail,
    }


def patch_update_cache_logic() -> None:
    """把 update_cache 改为按标的 max_date 补齐，避免全局 max 卡住。"""
    path = ROOT / "cache_kline.py"
    text = path.read_text(encoding="utf-8")
    old = 'df_new = df[df["date"] > max_date]'
    if "per_symbol_max" in text and "sym_max = last_map.get" in text:
        print("cache_kline already patched", flush=True)
        return
    if old not in text:
        print("WARN: expected filter line not found; skip patch", flush=True)
        return
    # inject last_map after computing max_date
    anchor = 'print(\n        f"增量更新: {len(symbols)} 只, 缓存最新: {max_date}, 拉取起点: {start_dt}",\n        flush=True,\n    )'
    # simpler replace of the filter line + add last_map before executor
    if "last_map = existing.groupby" not in text:
        text = text.replace(
            "new_rows = []\n    with ThreadPoolExecutor(max_workers=20) as ex:\n        futures = {ex.submit(fetch_stock_kline, s, start_dt): s for s in symbols}",
            "last_map = existing.groupby(\"symbol\")[\"date\"].max().to_dict()\n"
            "    new_rows = []\n"
            "    with ThreadPoolExecutor(max_workers=20) as ex:\n"
            "        futures = {ex.submit(fetch_stock_kline, s, start_dt): s for s in symbols}",
        )
    text = text.replace(
        'df_new = df[df["date"] > max_date]',
        'sym_max = last_map.get(str(sym), max_date)\n'
        '                # per_symbol_max: 避免全局 max 导致部分股票永远补不上\n'
        '                df_new = df[df["date"] > sym_max]',
    )
    path.write_text(text, encoding="utf-8")
    print("patched cache_kline.update_cache per-symbol max", flush=True)


if __name__ == "__main__":
    patch_update_cache_logic()
    info = backfill_missing()
    print(json.dumps(info, ensure_ascii=False), flush=True)
    raise SystemExit(0 if info.get("ok") else 1)
