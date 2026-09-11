#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""服务器 K 线补全 (2026-08-03 WorkBuddy / 2026-09-11 多源兜底 Cursor)
东财风控导致 kline_all 覆盖率崩(每天仅10只) → 用 mootdx(通达信直连) 补全最近 20 个交易日
合并进 data/kline_cache/kline_all.parquet (按 symbol+date 去重, 新行覆盖旧行)
保留 outstanding_share/turnover 旧值(通达信日线无此字段)

2026-09-11 加固（09-10 全量事故后）：
  1) TDX 早期熔断：连续失败 >= EARLY_ABORT_FAILS 且零成功时立即停 TDX、转兜底，
     不再像 09-10 那样空跑 5h18m。
  2) 兜底链 = 新浪(不复权, 主) → 腾讯(不复权, 备)：TDX 最新日覆盖 <90% 时，仅对缺失股票补拉。
     - 新浪 `adjust=""`：原生带 amount/outstanding_share/turnover，volume=股；生产 data_fetcher 即走新浪源。
     - 腾讯：`day` 数组不复权 + qt 当日金额；volume 688=股/其余=手×100。
       ⚠️ 腾讯 WAF 对高频请求会返回 501 封 IP（09-11 实测：无节流约 5000 请求后整机被封）
       → 故仅作次级源，且**必须**经全局限速；被封后本轮直接失败、由新浪兜住。
     - 逐行过单位比率校验(0.8~1.2) 才写，**校验不过=不写**；停牌股自动跳过。
  3) --dry-run 只算不写；--no-fallback 关闭兜底（等同旧行为）；--skip-tdx 直接用兜底。
"""
import os, time, json, shutil, argparse, threading
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed

KLINE_PATH = "data/kline_cache/kline_all.parquet"
BAK_PATH = "data/kline_cache/kline_all.parquet.bak_20260803"
DAYS = 20
WORKERS = 1  # 通达信直连对并发限流: 16线程失败率>80%, 串行实测100%成功
EARLY_ABORT_FAILS = 150   # TDX 连续失败且零成功达到该数 → 熔断转兜底
FB_WORKERS = 6            # 兜底并发
FB_MIN_INTERVAL = 0.05    # 全局最小请求间隔(s) → 上限 ~20 req/s（避免腾讯 WAF）
FB_ROUNDS = 3             # 失败重试轮数
FB_ROUND_COOLDOWN = 15    # 每轮之间冷却(s)
FB_MIN_RATIO, FB_MAX_RATIO = 0.8, 1.2   # 单位比率校验带
TENCENT_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"

from prod_op_lock import acquire_prod_lock, release_prod_lock

_rl_lock = threading.Lock()
_rl_last = [0.0]
def _rate_limit():
    """全局限速：避免腾讯/新浪高频请求被限流封禁。"""
    with _rl_lock:
        wait = FB_MIN_INTERVAL - (time.time() - _rl_last[0])
        if wait > 0:
            time.sleep(wait)
        _rl_last[0] = time.time()


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)


# ---------------------------------------------------------------- 代码/市场前缀
def _mk_code(sym):
    """6位代码 → 带市场前缀。北交所(8xx/4xx) 不在 A 股缓存范围 → (None, bare)。"""
    s = str(sym or "").strip().lower()
    for p in ("sh", "sz", "bj"):
        if s.startswith(p):
            s = s[2:]
    s = s[-6:]
    if s.startswith("6"):
        return "sh" + s, s
    if s.startswith(("0", "3")):
        return "sz" + s, s
    return None, s


# ---------------------------------------------------------------- TDX（主源）
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


# ---------------------------------------------------------------- 新浪（兜底主源，不复权）
def fetch_one_sina(sym, days=DAYS):
    """新浪【不复权】日线（adjust=""）。

    返回 date/open/high/low/close/volume(股)/amount/outstanding_share/turnover。
    生产 `data_fetcher` 即走新浪源，单只稳定性已验证（不被东财风控影响）。
    """
    code, bare = _mk_code(sym)
    if code is None:
        return None
    _rate_limit()
    try:
        import akshare as ak
        sd = (datetime.now() - timedelta(days=max(days, 20) * 2)).strftime("%Y%m%d")
        ed = datetime.now().strftime("%Y%m%d")
        df = ak.stock_zh_a_daily(symbol=code, start_date=sd, end_date=ed, adjust="")
        if df is None or len(df) == 0:
            return None
        df = df.rename(columns={c: str(c).lower() for c in df.columns})
        if "date" not in df.columns:
            return None
        df["date"] = df["date"].astype(str).str[:10]
        keep = [c for c in ["date", "open", "high", "low", "close", "volume",
                            "amount", "outstanding_share", "turnover"] if c in df.columns]
        df = df[keep].copy()
        for c in keep[1:]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["symbol"] = str(sym)
        return df
    except Exception:
        return None


# ---------------------------------------------------------------- 腾讯（兜底备源，不复权）
def fetch_one_tencent(sym, days=DAYS):
    """腾讯【不复权】日线兜底。

    - 价格: `data[code]['day']` = [date, open, close, high, low, volume]（不复权，与服务器缓存一致）
    - volume: 科创板 688 返回【股】；其余板块返回【手】→ ×100（与 westock 同规则）。
    - amount: 腾讯 day 数组不含成交额，仅能取 `qt` 快照里的当日 "price/volume/amount" 串
      → 只有最新交易日那一行有 amount，其它行为 NaN（校验不过即不写）。
    - ⚠️ 高频请求会被腾讯 WAF 501 封 IP；本函数经全局限速，且仅作次级源。
    """
    import requests
    code, bare = _mk_code(sym)
    if code is None:
        return None
    _rate_limit()
    try:
        r = requests.get(
            TENCENT_URL,
            params={"param": f"{code},day,,,{days},"},
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        node = (r.json().get("data") or {}).get(code) or {}
        rows = node.get("day") or []
        if not rows:
            return None
        # 当日成交额（元）: qt 中形如 "64.60/11489921/751189672" 的串
        qt_amt = None
        for x in (node.get("qt", {}).get(code) or []):
            if isinstance(x, str) and x.count("/") == 2:
                parts = x.split("/")
                try:
                    a = float(parts[2])
                    if a > 0:
                        qt_amt = a
                except Exception:
                    pass
                break
        last_d = str(rows[-1][0])[:10]
        recs = []
        for row in rows:
            if len(row) < 6:
                continue
            try:
                d = str(row[0])[:10]
                o, c, h, l, v = (float(row[1]), float(row[2]), float(row[3]),
                                 float(row[4]), float(row[5]))
            except Exception:
                continue
            if v <= 0 or c <= 0:
                continue
            vol = v if bare.startswith("688") else v * 100.0
            amt = qt_amt if (qt_amt and d == last_d) else None
            recs.append({"date": d, "open": o, "high": h, "low": l,
                         "close": c, "volume": vol, "amount": amt})
        if not recs:
            return None
        df = pd.DataFrame(recs)
        df["symbol"] = str(sym)
        return df
    except Exception:
        return None

def _probe_latest_date():
    """TDX 全失败时，用兜底源探针确定目标最新交易日（新浪优先）。"""
    for fn in (fetch_one_sina, fetch_one_tencent):
        for s in ("600519", "000001", "300750"):
            df = fn(s, days=5)
            if df is not None and len(df):
                return str(df["date"].max())[:10]
    return None


# ---------------------------------------------------------------- 兜底驱动
def _extract_target_row(df, target_date):
    """从单只结果中取 target_date 行，并过单位比率校验；不满足返回 None。"""
    if df is None or not len(df):
        return None
    row = df[df["date"].astype(str) == target_date]
    if not len(row):
        return None
    row = row.head(1).copy()
    try:
        amt = float(row["amount"].iloc[0]) if pd.notna(row["amount"].iloc[0]) else 0.0
        vol = float(row["volume"].iloc[0])
        close = float(row["close"].iloc[0])
    except Exception:
        return None
    if amt <= 0 or vol <= 0 or close <= 0:
        return None
    if not (FB_MIN_RATIO <= amt / (vol * close) <= FB_MAX_RATIO):
        return None  # 单位/口径存疑 → 宁可不写
    return row

def _try_sources(sym, target_date):
    for fn in (fetch_one_sina, fetch_one_tencent):
        row = _extract_target_row(fn(sym), target_date)
        if row is not None:
            row["symbol"] = str(sym)
            return row
    return None

def _fetch_fb_batch(missing, target_date, workers=FB_WORKERS):
    """单轮：并发拉取，返回 (成功行列表, 失败symbol列表)。"""
    got, failed = [], []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_try_sources, s, target_date): s for s in missing}
        for i, fut in enumerate(as_completed(futs), 1):
            s = futs[fut]
            try:
                row = fut.result()
                if row is not None:
                    got.append(row)
                else:
                    failed.append(s)
            except Exception:
                failed.append(s)
            if i % 500 == 0:
                log(f"    进度 {i}/{len(missing)} 成功{len(got)}")
    return got, failed

def fill_missing_fallback(missing, target_date, workers=FB_WORKERS, rounds=FB_ROUNDS):
    """对 target_date 缺失的股票补拉：新浪优先，腾讯兜底；多轮重试穿透限流。"""
    got, todo = [], list(missing)
    if not todo:
        return got
    for rd in range(1, max(1, rounds) + 1):
        if not todo:
            break
        log(f"  兜底 第 {rd}/{rounds} 轮: 待拉 {len(todo)} 只（新浪→腾讯）")
        g, failed = _fetch_fb_batch(todo, target_date, workers=workers)
        got.extend(g)
        todo = failed
        log(f"    第 {rd} 轮完成: 成功 +{len(g)} / 本轮失败 {len(failed)}")
        if todo and rd < rounds:
            time.sleep(FB_ROUND_COOLDOWN * rd)
    if todo:
        log(f"  兜底结束: 仍失败 {len(todo)} 只（样例 {todo[:10]}）")
    return got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只拉取+校验，不写文件")
    ap.add_argument("--no-fallback", action="store_true", help="关闭兜底（等同旧行为）")
    ap.add_argument("--skip-tdx", action="store_true", help="跳过 TDX，直接用兜底（TDX 已知宕机时用）")
    args = ap.parse_args()

    if not acquire_prod_lock("fix_kline", reason="16:15 K线补全（cron）"):
        print("锁被占用，跳过本次 K 线补全"); return 1
    t0 = time.time()
    log("=== K线补全 (TDX 主源 + 新浪/腾讯 兜底) ===")
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

    # 2. TDX 拉取（含早期熔断，避免 09-10 那种空跑 5h）
    ok, fail = [], []
    aborted = False
    if args.skip_tdx:
        log("[INFO] --skip-tdx：跳过 TDX，直接走兜底")
    else:
        ex = ThreadPoolExecutor(max_workers=WORKERS)
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
            if not ok and len(fail) >= EARLY_ABORT_FAILS:
                aborted = True
                log(f"[WARN] TDX 连续失败 {len(fail)} 且零成功 → 早期熔断，转兜底")
                break
        ex.shutdown(wait=False, cancel_futures=True)
    log(f"TDX 拉取{'(熔断)' if aborted else ''}: 成功 {len(ok)} 只 / 失败 {len(fail)} 只 ({time.time()-t0:.0f}s)")
    if fail:
        log(f"  失败代码样例: {fail[:10]}")

    # 3. 汇总 TDX 结果 + 覆盖率
    new_df = pd.concat(ok, ignore_index=True) if ok else pd.DataFrame(
        columns=["date", "open", "high", "low", "close", "volume", "amount", "symbol"]
    )
    if len(new_df):
        _cov_dates = sorted(new_df["date"].astype(str).unique())
        _cov_latest = _cov_dates[-1] if _cov_dates else ""
    else:
        _cov_latest = _probe_latest_date() or ""
        log(f"  TDX 无数据，兜底探针目标最新日 = {_cov_latest or '未知'}")
    if not _cov_latest:
        log("[ERR] 无法确定目标最新交易日, 未写入"); release_prod_lock(); return 1

    def _coverage(df):
        if not len(df):
            return set(), 0.0
        cov = set(df[df["date"].astype(str) == _cov_latest]["symbol"].astype(str))
        return cov, len(cov) / len(symbols)

    covered, _cov_pct = _coverage(new_df)
    log(f"  TDX 最新日 {_cov_latest} 覆盖 {len(covered)}/{len(symbols)} ({_cov_pct:.1%})")

    # 4. 兜底：TDX 覆盖不足 → 新浪/腾讯补缺失股票（仅目标日）
    if _cov_pct < 0.90 and not args.no_fallback:
        missing = [s for s in symbols if s not in covered]
        log(f"[WARN] TDX 最新日覆盖 {_cov_pct:.1%} < 90% → 兜底 {len(missing)} 只")
        fb = fill_missing_fallback(missing, _cov_latest)
        log(f"  兜底完成: 成功 {len(fb)} 只 ({time.time()-t0:.0f}s)")
        if fb:
            parts = ([new_df] if len(new_df) else []) + fb
            new_df = pd.concat(parts, ignore_index=True)
            covered, _cov_pct = _coverage(new_df)
            log(f"  合并后最新日 {_cov_latest} 覆盖 {len(covered)}/{len(symbols)} ({_cov_pct:.1%})")

    # 5. 覆盖率门槛（2026-08-24 根治）：仍不足则拒绝写入
    if not len(new_df):
        log("[ERR] 全部拉取失败, 未写入"); release_prod_lock(); return 1
    if _cov_pct < 0.90:
        log(f"[ERR] 最新日覆盖率 {_cov_pct:.1%} < 90%，拒绝写入残缺 K 线"); release_prod_lock(); return 1

    # 6. 合并（保留旧 outstanding_share/turnover，按 symbol 最近值填充）
    old_cols = [c for c in ["outstanding_share", "turnover"] if c in kdf.columns]
    if old_cols:
        latest_old = kdf.sort_values("date").groupby("symbol")[old_cols].last().reset_index()
        new_df = new_df.merge(latest_old, on="symbol", how="left",
                              suffixes=("", "_old"))
        # 兜底源自带 outstanding_share/turnover 时优先用新值
        for c in old_cols:
            if c + "_old" in new_df.columns:
                new_df[c] = new_df[c].where(new_df[c].notna(), new_df[c + "_old"])
                new_df = new_df.drop(columns=[c + "_old"])
    merged = pd.concat([kdf, new_df], ignore_index=True)
    merged = merged.drop_duplicates(subset=["symbol", "date"], keep="last")
    merged = merged.sort_values(["symbol", "date"]).reset_index(drop=True)

    # 写前校验（dry-run 也执行）
    dates = merged["date"].unique()
    for d in sorted(dates)[-5:]:
        n = (merged["date"] == d).sum()
        log(f"  {d}: {n} 只")
    last = str(merged["date"].max())
    sample = merged[merged["date"] == last].head(200).copy()
    vol = sample["volume"].clip(lower=1)
    close = sample["close"].replace(0, np.nan)
    ratio = float((sample["amount"] / (vol * close)).median())
    log(f"  volume_ratio_med={ratio:.3f} asof={last}")

    if args.dry_run:
        log(f"[DRY-RUN] 不写文件；合并后 {len(merged)} 行 (原 {len(kdf)})")
        release_prod_lock(); return 0
    if ratio >= 20:
        log("[ERR] volume 仍像手数，拒绝把坏文件留着"); release_prod_lock(); return 1

    merged.to_parquet(KLINE_PATH, index=False)
    log(f"合并后: {len(merged)} 行")
    root = "kline_all.parquet"
    if os.path.exists(root) and os.path.realpath(root) != os.path.realpath(KLINE_PATH):
        shutil.copy2(KLINE_PATH, root)
        log(f"synced {root}")
    log(f"总用时 {int(time.time()-t0)}s")
    release_prod_lock()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
