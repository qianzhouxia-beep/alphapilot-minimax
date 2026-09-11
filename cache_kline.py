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

CACHE_DIR = Path("data/kline_cache")  # 统一单一数据源: data/kline_cache/kline_all.parquet -> 软链到根目录 kline_all.parquet
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

def update_cache():
    """仅补最新交易日"""
    t0 = time.time()
    today = datetime.now().strftime("%Y%m%d")
    
    existing = load_cache()
    if len(existing) == 0:
        print("缓存为空，执行全量构建")
        build_full_cache()
        return
    
    symbols = existing["symbol"].unique()
    print(f"增量更新: {len(symbols)} 只, 最新日期: {existing['date'].max() if 'date' in existing.columns else '?'}")
    
    new_rows = []
    with ThreadPoolExecutor(max_workers=20) as ex:
        futures = {ex.submit(fetch_stock_kline, s, today): s for s in symbols}
        done = 0
        for f in as_completed(futures):
            sym, df = f.result()
            if df is not None and len(df) > 0:
                # 只取最新日期的行
                df_new = df[df["date"] == today] if "date" in df.columns else df
                if len(df_new) > 0:
                    new_rows.append(df_new)
            done += 1
            if done % 500 == 0:
                print(f"  [{int(time.time()-t0)}s] {done}/{len(symbols)}", flush=True)
    
    if new_rows:
        new_df = pd.concat(new_rows, ignore_index=True)
        # 去重：删除已有日期+symbol的行
        combined = pd.concat([existing, new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset=["symbol", "date"], keep="last")
        save_cache(combined)
    else:
        print("  无新数据")
    
    print(f"增量更新完成: {int(time.time()-t0)}s")

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    print(f"K线缓存 {'全量' if mode=='full' else '增量'} 构建")
    print("="*50)
    
    if mode == "full":
        build_full_cache()
    elif mode == "update":
        update_cache()
    else:
        print(f"未知模式: {mode}, 可用: full|update")
    
    if INDEX_FILE.exists():
        info = json.load(open(INDEX_FILE))
        print(f"\n缓存状态: {info['stock_count']} 只 × {info['total_rows']} 行")
        print(f"  日期范围: {info['date_range'][0]} ~ {info['date_range'][1]}")
