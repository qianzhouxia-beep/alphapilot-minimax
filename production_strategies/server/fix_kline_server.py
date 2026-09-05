#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""服务器 K 线补全 (2026-08-03, WorkBuddy)
东财风控导致 kline_all 覆盖率崩(每天仅10只) → 用 mootdx(通达信直连) 补全最近 20 个交易日
合并进 data/kline_cache/kline_all.parquet (按 symbol+date 去重, 新行覆盖旧行)
保留 outstanding_share/turnover 旧值(通达信日线无此字段)
"""
import os, time, json, shutil
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed

KLINE_PATH = "data/kline_cache/kline_all.parquet"
BAK_PATH = "data/kline_cache/kline_all.parquet.bak_20260803"
DAYS = 20
WORKERS = 1  # 通达信直连对并发限流: 16线程失败率>80%, 串行实测100%成功

from prod_op_lock import acquire_prod_lock, release_prod_lock


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)

def get_client():
    from mootdx.quotes import Quotes
    return Quotes.factory(market="std")

_client = None
def _c():
    global _client
    if _client is None:
        _client = get_client()
    return _client

def fetch_one(sym):
    """拉单只最近 DAYS 天日线, 失败返回 None"""
    for attempt in range(2):
        try:
            df = _c().bars(symbol=sym, frequency=9, offset=DAYS)
            if df is None or len(df) == 0:
                return None
            df = df.reset_index(drop=True)
            # 日期: mootdx 返回 datetime 列 (字符串 'YYYY-MM-DD HH:MM')
            if "datetime" in df.columns:
                df["date"] = df["datetime"].astype(str).str[:10]
            elif "date" in df.columns:
                df["date"] = df["date"].astype(str).str[:10]
            else:
                return None
            # volume: 通达信单位是手。用 amount/(volume*close) 判别后再决定是否 ×100。
            if "volume" not in df.columns and "vol" in df.columns:
                df["volume"] = df["vol"]
            if "volume" in df.columns:
                vol = pd.to_numeric(df["volume"], errors="coerce")
                if "amount" in df.columns and "close" in df.columns:
                    amt = pd.to_numeric(df["amount"], errors="coerce")
                    close = pd.to_numeric(df["close"], errors="coerce").replace(0, np.nan)
                    ratio = amt / (vol.clip(lower=1) * close)
                    med = float(ratio.median()) if ratio.notna().any() else 1.0
                    if 20 <= med <= 500:
                        df["volume"] = vol * 100
                    else:
                        df["volume"] = vol
                else:
                    df["volume"] = vol * 100
            keep = [c for c in ["date", "open", "high", "low", "close", "volume", "amount"] if c in df.columns]
            df = df[keep]
            for c in keep[1:]:
                df[c] = pd.to_numeric(df[c], errors="coerce")
            df["symbol"] = sym
            return df
        except Exception:
            time.sleep(0.3)
    return None

def main():
    if not acquire_prod_lock("fix_kline", reason="16:15 K线补全（cron）"):
        print("锁被占用，跳过本次 K 线补全"); return 1
    t0 = time.time()
    log("=== K线补全 (mootdx 通达信直连) ===")
    # 1. 备份 + 加载现有 (主文件可能已被上次改名, 则读备份)
    src = KLINE_PATH if os.path.exists(KLINE_PATH) else (BAK_PATH if os.path.exists(BAK_PATH) else None)
    if src is None:
        log(f"[ERR] {KLINE_PATH} 和 {BAK_PATH} 都不存在"); return 1
    if os.path.exists(KLINE_PATH) and not os.path.exists(BAK_PATH):
        os.rename(KLINE_PATH, BAK_PATH)
        log(f"备份 → {BAK_PATH}")
    kdf = pd.read_parquet(src)
    kdf["date"] = kdf["date"].astype(str).str[:10]
    kdf["symbol"] = kdf["symbol"].astype(str)
    symbols = sorted(kdf["symbol"].unique())
    log(f"现有 {len(kdf)} 行 / {len(symbols)} 只 | 最新日期 {kdf['date'].max()}")

    # 2. 并发拉取
    ok, fail = [], []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(fetch_one, s): s for s in symbols}
        done = 0
        for fut in as_completed(futs):
            s = futs[fut]
            try:
                df = fut.result()
                if df is not None and len(df) > 0:
                    ok.append(df)
                else:
                    fail.append(s)
            except Exception:
                fail.append(s)
            done += 1
            if done % 1000 == 0:
                log(f"  进度 {done}/{len(symbols)} 成功{len(ok)} 失败{len(fail)} ({time.time()-t0:.0f}s)")

    log(f"拉取完成: 成功 {len(ok)} 只 / 失败 {len(fail)} 只 ({time.time()-t0:.0f}s)")
    if fail:
        log(f"  失败代码样例: {fail[:10]}")

    # 覆盖率门槛（2026-08-24 根治）：最新交易日覆盖率 <90% 时拒绝写入，
    # 防止「并发限流大量失败后仍把残缺 K 线当最新数据落盘」导致下游 chip/因子
    # 静默使用旧数据（08-24 事故：成功960/失败4031，文件照样写入）。
    if not ok:
        log("[ERR] 全部拉取失败, 未写入")
        release_prod_lock()
        return 1
    new_df = pd.concat(ok, ignore_index=True)
    _cov_dates = sorted(new_df["date"].unique())
    _cov_latest = _cov_dates[-1] if _cov_dates else ""
    _cov_n = int((new_df["date"] == _cov_latest).sum()) if _cov_latest else 0
    _cov_total = len(symbols)
    _cov_pct = _cov_n / _cov_total if _cov_total else 0.0
    log(f"  最新日 {_cov_latest} 覆盖 {_cov_n}/{_cov_total} ({_cov_pct:.1%})")
    if _cov_pct < 0.90:
        log(f"[ERR] 最新日覆盖率 {_cov_pct:.1%} < 90%，拒绝写入残缺 K 线")
        release_prod_lock()
        return 1

    # 3. 合并
    # 保留旧 outstanding_share/turnover (按 symbol 最近值填充)
    old_cols = [c for c in ["outstanding_share", "turnover"] if c in kdf.columns]
    if old_cols:
        latest_old = kdf.sort_values("date").groupby("symbol")[old_cols].last().reset_index()
        new_df = new_df.merge(latest_old, on="symbol", how="left")
    merged = pd.concat([kdf, new_df], ignore_index=True)
    merged = merged.drop_duplicates(subset=["symbol", "date"], keep="last")
    merged = merged.sort_values(["symbol", "date"]).reset_index(drop=True)
    merged.to_parquet(KLINE_PATH, index=False)
    log(f"合并后: {len(merged)} 行")
    # 覆盖率
    dates = merged["date"].unique()
    latest_dates = sorted(dates)[-5:]
    for d in latest_dates:
        n = (merged["date"] == d).sum()
        log(f"  {d}: {n} 只")
    last = str(merged["date"].max())
    sample = merged[merged["date"] == last].head(200).copy()
    vol = sample["volume"].clip(lower=1)
    close = sample["close"].replace(0, np.nan)
    ratio = float((sample["amount"] / (vol * close)).median())
    log(f"  volume_ratio_med={ratio:.3f} asof={last}")
    if ratio >= 20:
        log("[ERR] volume 仍像手数，拒绝把坏文件留着")
        return 1
    root = "kline_all.parquet"
    if os.path.exists(root) and os.path.realpath(root) != os.path.realpath(KLINE_PATH):
        shutil.copy2(KLINE_PATH, root)
        log(f"synced {root}")
    log(f"总用时 {int(time.time()-t0)}s")
    release_prod_lock()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
