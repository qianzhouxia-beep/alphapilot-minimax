#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fix cache_kline.update_cache to backfill from last cached date (not only 'today')."""
from __future__ import annotations

from pathlib import Path

ROOT = Path("/home/ubuntu/alphapilot")
path = ROOT / "cache_kline.py"
src = path.read_text(encoding="utf-8")
bak = ROOT / "cache_kline.py.bak_before_backfill"
if not bak.exists():
    bak.write_text(src, encoding="utf-8")

old = '''def update_cache():
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
'''

new = '''def update_cache():
    """从缓存最大日期之后补到最近有数据的交易日（周末也可补齐周五缺口）。"""
    t0 = time.time()

    existing = load_cache()
    if len(existing) == 0:
        print("缓存为空，执行全量构建")
        build_full_cache()
        return

    existing = existing.copy()
    existing["date"] = existing["date"].astype(str).str[:10]
    max_date = existing["date"].max()
    start_dt = (datetime.strptime(max_date, "%Y-%m-%d") - timedelta(days=2)).strftime("%Y%m%d")
    symbols = existing["symbol"].unique()
    print(
        f"增量更新: {len(symbols)} 只, 缓存最新: {max_date}, 拉取起点: {start_dt}",
        flush=True,
    )

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
                df_new = df[df["date"] > max_date]
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
            combined.to_parquet(ROOT / "kline_all.parquet" if False else Path("kline_all.parquet"), index=False)
            print("  ✅ synced ./kline_all.parquet", flush=True)
        except Exception as e:
            print(f"  ⚠️ sync root parquet fail: {e}", flush=True)
    else:
        print("  无新数据（可能源站尚未更新，或已是最新）", flush=True)

    print(f"增量更新完成: {int(time.time()-t0)}s", flush=True)
'''

# Fix the botched ROOT reference in new string - use Path("kline_all.parquet") only
new = new.replace(
    'combined.to_parquet(ROOT / "kline_all.parquet" if False else Path("kline_all.parquet"), index=False)',
    'combined.to_parquet(Path("kline_all.parquet"), index=False)',
)

if old not in src:
    # try flexible match
    if "def update_cache():" in src and "today = datetime.now().strftime" in src:
        import re
        src2, n = re.subn(
            r"def update_cache\(\):.*?print\(f\"增量更新完成: \{int\(time\.time\(\)-t0\)\}s\"\)\n",
            new,
            src,
            count=1,
            flags=re.S,
        )
        if n != 1:
            raise SystemExit("pattern not found for update_cache")
        src = src2
    else:
        raise SystemExit("update_cache block not found")
else:
    src = src.replace(old, new, 1)

path.write_text(src, encoding="utf-8")
print("PATCHED cache_kline.update_cache")
