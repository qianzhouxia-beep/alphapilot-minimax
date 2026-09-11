"""5分钟K线增量累积 (服务器端)
- mootdx 只能回溯7天 → 每天收盘后增量拉取追加, 建立长期历史库
- 数据: data/kline5m/{symbol}.parquet (每只一个文件) 或合并文件
- 存储: 上海服务器 /home/ubuntu/alphapilot/data/kline5m/
- 时间: 每日 15:30 后 cron 运行 (数据量: 全市场~5000只 × 48根/天)
"""
import json, os, time, sys
import pandas as pd
import numpy as np
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from mootdx.quotes import Quotes

ROOT = Path("/home/ubuntu/alphapilot")
DATA5M = ROOT / "data" / "kline5m"
DATA5M.mkdir(parents=True, exist_ok=True)
INDEX_FILE = DATA5M / "_index.json"

TOP_N = 5000     # 全市场覆盖 (~5000只, 6秒/500只 → 约60秒全市场)
BATCH = 30       # 并发线程数


def load_active_symbols(top_n=TOP_N):
    """从日线 parquet 取全市场股票"""
    try:
        kline = pd.read_parquet(ROOT / "kline_all.parquet")
        # 全市场: 取所有 symbol, 按最近成交量排序(活跃优先)
        recent = kline[kline['date'] >= (pd.Timestamp.now() - pd.Timedelta(days=30)).strftime('%Y-%m-%d')]
        top = recent.groupby('symbol')['volume'].mean().sort_values(ascending=False).head(top_n)
        return top.index.tolist()
    except Exception as e:
        print(f"加载活跃股失败: {e}")
        # fallback: 沪深300权重股样本
        return ["600519", "300750", "000001", "601318", "600036"]


def fetch_5min(symbol, days=7):
    """拉取单只股票7天5分钟"""
    try:
        client = Quotes.factory(market='std')
        bars = client.bars(symbol=symbol, frequency=0, offset=48 * days)
        if bars is not None and len(bars) > 0:
            bars = bars.reset_index(drop=True)
            bars['symbol'] = symbol
            bars['datetime'] = pd.to_datetime(bars['datetime'])
            return bars
    except Exception as e:
        pass
    return None


def save_symbol(symbol, new_df):
    """增量合并保存单只股票"""
    path = DATA5M / f"{symbol}.parquet"
    if path.exists():
        try:
            old = pd.read_parquet(path)
            combined = pd.concat([old, new_df], ignore_index=True)
            combined = combined.drop_duplicates(subset=['datetime'], keep='last')
            combined = combined.sort_values('datetime').reset_index(drop=True)
            combined.to_parquet(path, index=False)
            return len(combined), combined['datetime'].max()
        except Exception:
            pass
    new_df = new_df.sort_values('datetime').reset_index(drop=True)
    new_df.to_parquet(path, index=False)
    return len(new_df), new_df['datetime'].max()


def main():
    t0 = time.time()
    symbols = load_active_symbols()
    print(f"处理 {len(symbols)} 只活跃股...")

    results = {}
    with ThreadPoolExecutor(max_workers=BATCH) as ex:
        futures = {ex.submit(fetch_5min, s): s for s in symbols}
        done = 0
        for f in as_completed(futures):
            sym = futures[f]
            bars = f.result()
            if bars is not None and len(bars) > 0:
                total, latest = save_symbol(sym, bars)
                results[sym] = {"rows": total, "latest": str(latest)}
            done += 1
            if done % 100 == 0:
                print(f"  {done}/{len(symbols)} ({time.time()-t0:.0f}s)")

    # 索引
    info = {
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "n_symbols": len(results),
        "per_symbol_rows": {s: v["rows"] for s, v in results.items()},
    }
    with open(INDEX_FILE, "w") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - t0
    total_rows = sum(v["rows"] for v in results.values())
    size = sum(os.path.getsize(DATA5M / f"{s}.parquet") for s in results if (DATA5M / f"{s}.parquet").exists())
    print(f"\n✅ 完成: {len(results)} 只, 总行数 {total_rows:,}, 存储 {size/1024/1024:.1f}MB, 用时 {elapsed:.0f}s")
    print(f"数据目录: {DATA5M}")


if __name__ == "__main__":
    main()
