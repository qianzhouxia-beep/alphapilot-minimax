#!/usr/bin/env python3
"""
K线数据缓存构建脚本
- 首次运行：全量拉取并保存到 Parquet
- 增量运行：只补最新交易日
- 被 data_fetcher.get_kline_sina 的缓存层读取
"""
import os, sys, json, time, pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

CACHE_DIR = Path("data/kline_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_FILE = CACHE_DIR / "kline_all.parquet"
INDEX_FILE = CACHE_DIR / "_index.json"

from data_fetcher import get_stock_list, _get_kline_sina

def load_cache():
    """加载已有缓存"""
    if CACHE_FILE.exists():
        try:
            df = pd.read_parquet(CACHE_FILE)
            print(f"  缓存加载: {len(df)} 行, {df['symbol'].nunique() if 'symbol' in df else '?'} 只")
            return df
        except Exception as e:
            print(f"  缓存读取失败: {e}")
    return pd.DataFrame()

def save_cache(df):
    """保存缓存到 Parquet"""
    df.to_parquet(CACHE_FILE, index=False)
    # 记录索引信息
    index_info = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_rows": len(df),
        "stock_count": df["symbol"].nunique() if "symbol" in df.columns else 0,
        "date_range": [df["date"].min(), df["date"].max()] if "date" in df.columns else [],
    }
    with open(INDEX_FILE, "w") as f:
        json.dump(index_info, f, indent=2, ensure_ascii=False)
    print(f"  ✅ 缓存保存: {len(df)} 行, {index_info['stock_count']} 只")

def fetch_stock_kline(symbol, start_date="20250101"):
    """拉取单只K线"""
    try:
        df = _get_kline_sina(symbol, start_date)
        if df is not None and len(df) > 0:
            df["symbol"] = symbol
            return symbol, df
    except Exception as e:
        pass
    return symbol, None

def build_full_cache():
    """全量构建"""
    t0 = time.time()
    stocks = get_stock_list()
    symbols = stocks["symbol"].tolist()
    total = len(symbols)
    print(f"全量构建: {total} 只股票")
    
    existing = load_cache()
    existing_symbols = set(existing["symbol"].unique()) if "symbol" in existing.columns else set()
    need = [s for s in symbols if s not in existing_symbols]
    print(f"  已有: {len(existing_symbols)}, 需要: {len(need)}")
    
    if len(need) == 0:
        print("  全部已缓存，跳过")
        return
    
    new_rows = []
    batch_size = 100
    with ThreadPoolExecutor(max_workers=20) as ex:
        for i in range(0, len(need), batch_size):
            batch = need[i:i+batch_size]
            futures = {ex.submit(fetch_stock_kline, s): s for s in batch}
            for f in as_completed(futures):
                sym, df = f.result()
                if df is not None and len(df) > 0:
                    new_rows.append(df)
            pct = min(100, int((i+batch_size)/total*100))
            elapsed = int(time.time()-t0)
            print(f"  [{elapsed}s] {min(i+batch_size,total)}/{total} ({pct}%)", flush=True)
    
    if new_rows:
        new_df = pd.concat(new_rows, ignore_index=True)
        combined = pd.concat([existing, new_df], ignore_index=True) if len(existing) > 0 else new_df
        save_cache(combined)
    
    print(f"全量构建完成: {int(time.time()-t0)}s")

def probe_source_max_date(start_date: str | None = None) -> str | None:
    """用几只流动性好的票探测源站最新交易日。"""
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=10)).strftime("%Y%m%d")
    dates = []
    for sym in ("000001", "600519", "300750"):
        try:
            df = _get_kline_sina(sym, start_date)
            if df is not None and len(df) > 0:
                dates.append(str(df["date"].astype(str).str[:10].max()))
        except Exception:
            continue
    return max(dates) if dates else None


def update_cache() -> bool:
    """从缓存最大日期之后补到最近有数据的交易日。

    返回 True=缓存已对齐源站最新日；False=空更新/落后源站（调用方应重试或告警）。
    """
    t0 = time.time()

    existing = load_cache()
    if len(existing) == 0:
        print("缓存为空，执行全量构建")
        build_full_cache()
        return True

    existing = existing.copy()
    existing["date"] = existing["date"].astype(str).str[:10]
    max_date = existing["date"].max()
    start_dt = (datetime.strptime(max_date, "%Y-%m-%d") - timedelta(days=2)).strftime("%Y%m%d")
    symbols = existing["symbol"].unique()
    print(
        f"增量更新: {len(symbols)} 只, 缓存最新: {max_date}, 拉取起点: {start_dt}",
        flush=True,
    )

    last_map = existing.groupby("symbol")["date"].max().to_dict()
    new_rows = []
    with ThreadPoolExecutor(max_workers=20) as ex:
        futures = {ex.submit(fetch_stock_kline, s, start_dt): s for s in symbols}
        done = 0
        for f in as_completed(futures):
            sym, df = f.result()
            if df is not None and len(df) > 0:
                df = df.copy()
                df["symbol"] = sym
                df["date"] = df["date"].astype(str).str[:10]
                sym_max = last_map.get(str(sym), max_date)
                # per_symbol_max: 避免全局 max 导致部分股票永远补不上
                df_new = df[df["date"] > sym_max]
                if len(df_new) > 0:
                    new_rows.append(df_new)
            done += 1
            if done % 500 == 0:
                print(f"  [{int(time.time()-t0)}s] {done}/{len(symbols)} new_batches={len(new_rows)}", flush=True)

    if new_rows:
        new_df = pd.concat(new_rows, ignore_index=True)
        print(f"  新行: {len(new_df)} 日期={sorted(new_df['date'].unique())}", flush=True)
        combined = pd.concat([existing, new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset=["symbol", "date"], keep="last")
        save_cache(combined)
        # 同步根目录副本（部分脚本读这里）
        try:
            combined.to_parquet(Path("kline_all.parquet"), index=False)
            print("  ✅ synced ./kline_all.parquet", flush=True)
        except Exception as e:
            print(f"  ⚠️ sync root parquet fail: {e}", flush=True)
        max_date = str(combined["date"].astype(str).str[:10].max())
    else:
        print("  无新数据（可能源站尚未更新，或已是最新）", flush=True)

    # 关键：与源站探测日对齐；空更新但源站已有更新日 → 失败（勿再伪装成功）
    src_max = probe_source_max_date(start_dt)
    print(f"  源站探测最新日: {src_max} | 缓存最新: {max_date}", flush=True)
    ok = True
    if src_max and max_date < src_max:
        print(
            f"  ❌ 缓存落后源站: cache={max_date} < source={src_max}",
            flush=True,
        )
        ok = False
    elif not new_rows and src_max and max_date == src_max:
        print("  ✅ 已是最新（与源站一致）", flush=True)
    elif not new_rows and not src_max:
        print("  ⚠️ 无新行且源站探测失败，视为失败以便重试", flush=True)
        ok = False

    print(f"增量更新完成: {int(time.time()-t0)}s ok={ok}", flush=True)
    return ok

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    print(f"K线缓存 {'全量' if mode=='full' else '增量'} 构建")
    print("="*50)

    ok = True
    if mode == "full":
        build_full_cache()
    elif mode == "update":
        ok = update_cache()
    else:
        print(f"未知模式: {mode}, 可用: full|update")
        sys.exit(2)

    if INDEX_FILE.exists():
        info = json.load(open(INDEX_FILE))
        print(f"\n缓存状态: {info['stock_count']} 只 × {info['total_rows']} 行")
        print(f"  日期范围: {info['date_range'][0]} ~ {info['date_range'][1]}")

    sys.exit(0 if ok else 1)
