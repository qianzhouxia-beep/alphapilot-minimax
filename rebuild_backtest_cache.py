# -*- coding: utf-8 -*-
"""重建 backtest_cache: 从 kline_all.parquet (100% 08-03) 生成全部 pkl"""
import pandas as pd
import os, time
from prod_op_lock import acquire_prod_lock, release_prod_lock

KLINE = '/home/ubuntu/alphapilot/data/kline_cache/kline_all.parquet'
CACHE = '/home/ubuntu/alphapilot/backtest_cache'

if not acquire_prod_lock("rebuild_cache", reason="16:22 backtest_cache 重建（cron）"):
    print("锁被占用，跳过本次缓存重建"); sys.exit(1)
t0 = time.time()
kdf = pd.read_parquet(KLINE,
                      columns=['symbol', 'date', 'open', 'high', 'low', 'close', 'volume', 'amount'])
kdf['symbol'] = kdf['symbol'].astype(str)
print(f"kline_all: {len(kdf):,} 行 / {kdf['symbol'].nunique()} 只", flush=True)

# 继承旧 pkl 的 outstanding_share
os_map = {}
for f in os.listdir(CACHE):
    if f.endswith('.pkl'):
        sym = f[:-4]
        if len(sym) == 6 and sym.isdigit():
            try:
                k = pd.read_pickle(os.path.join(CACHE, f))
                if 'outstanding_share' in k.columns and len(k) > 0:
                    v = k['outstanding_share'].iloc[-1]
                    if v is not None and float(v) > 0:
                        os_map[sym] = float(v)
            except Exception:
                pass
print(f"outstanding_share 继承: {len(os_map)} 只", flush=True)

n = 0
latest_dates = set()
for sym, g in kdf.groupby('symbol'):
    g = g.sort_values('date').reset_index(drop=True)
    if len(g) < 60:
        continue
    g = g.copy()
    os_ = os_map.get(sym, 0.0)
    g['outstanding_share'] = os_
    g['turnover'] = (g['volume'] / os_) if os_ > 0 else 0.0
    cols = ['date', 'open', 'high', 'low', 'close', 'volume', 'amount',
            'outstanding_share', 'turnover', 'symbol']
    g = g[cols]
    g.to_pickle(os.path.join(CACHE, f"{sym}.pkl"))
    latest_dates.add(str(g['date'].iloc[-1]))
    n += 1
    if n % 1000 == 0:
        print(f"  {n} 只 ...", flush=True)

print(f"重建完成: {n} 个 pkl, 用时 {int(time.time()-t0)}s", flush=True)
print("最新日期样例:", sorted(latest_dates)[-5:], flush=True)
release_prod_lock()
