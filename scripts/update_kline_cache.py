#!/usr/bin/env python3
"""
K 线缓存更新 — 用 eastmoney 源（东财免费，比 akshare 稳定）
替换旧的 cache_kline.py update（akshare 经常返回空）
"""
import json, time, sys
import pandas as pd
import urllib.request
from pathlib import Path

ROOT = Path("/home/ubuntu/alphapilot")
KLINE_PATH = ROOT / "kline_all.parquet"
LMT = 3  # 拉最近3天，覆盖周末/假期gap

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

log("K线更新 (eastmoney源)")

# 加载现有数据
df = pd.read_parquet(KLINE_PATH)
existing_dates = set(str(d)[:10] for d in pd.to_datetime(df['date']))
symbols = sorted(df['symbol'].unique().tolist())
log(f"现有: {len(symbols)} 只, 最新日期: {max(existing_dates)}")

# 拉新数据
all_new = []
n, skipped = 0, 0
for sym in symbols:
    prefix = '1' if sym.startswith('6') else '0'
    try:
        url = (f'https://push2his.eastmoney.com/api/qt/stock/kline/get'
               f'?secid={prefix}.{sym}&klt=101&fqt=0&end=20500101&lmt={LMT}'
               f'&fields1=f1&fields2=f51,f52,f53,f54,f55,f56,f57')
        r = urllib.request.urlopen(url, timeout=5)
        data = json.loads(r.read())
        klines = data.get('data', {}).get('klines', [])
        for kl in klines:
            parts = kl.split(',')
            dt = parts[0]
            if dt not in existing_dates:
                all_new.append({
                    'date': dt, 'symbol': sym,
                    'open': float(parts[1]), 'close': float(parts[2]),
                    'high': float(parts[3]), 'low': float(parts[4]),
                    'volume': float(parts[5]), 'amount': float(parts[6]),
                })
        n += 1
        if n % 1000 == 0:
            log(f"  {n}/{len(symbols)} ({len(all_new)} new rows)")
    except Exception as e:
        skipped += 1
        if skipped < 5:
            log(f"  WARN {sym}: {e}")
    time.sleep(0.05)  # 限频

log(f"完成: {n}/{len(symbols)}, 跳过 {skipped}, 新行 {len(all_new)}")

if all_new:
    ndf = pd.DataFrame(all_new)
    # 去重后合并
    combined = pd.concat([df, ndf], ignore_index=True)
    combined = combined.drop_duplicates(subset=['date', 'symbol'], keep='last')
    combined = combined.sort_values(['symbol', 'date']).reset_index(drop=True)
    combined.to_parquet(KLINE_PATH, index=False)
    new_dates = sorted(set(str(d)[:10] for d in pd.to_datetime(combined['date'])))
    log(f"保存: {len(combined)} 行, 日期范围: {new_dates[0]} ~ {new_dates[-1]}")
else:
    log("无新数据")
