#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""K线覆盖率检查增强 (2026-08-03, WorkBuddy 修复)
原 data_freshness_check 只查 date.max() → 10/4991 也误判"最新"
新增: 检查最近交易日覆盖率, < 90% 即告警
用法: python3 freshness_coverage_check.py
"""
import json, os, sys
from datetime import datetime, timedelta

KLINE_PATH = "data/kline_cache/kline_all.parquet"
THRESHOLD = 0.90   # 覆盖率阈值: 最近交易日应有 >= 90% 股票有 K 线

def main():
    import pandas as pd
    alerts = []
    if not os.path.exists(KLINE_PATH):
        print(json.dumps({"ok": False, "alerts": [f"{KLINE_PATH} 不存在"]}, ensure_ascii=False))
        return 1
    kdf = pd.read_parquet(KLINE_PATH, columns=["date", "symbol"])
    kdf["date"] = kdf["date"].astype(str).str[:10]
    total_symbols = kdf["symbol"].nunique()
    dates = sorted(kdf["date"].unique())
    latest = dates[-1]
    # 最近 5 个有数据的交易日覆盖
    print(f"K线: 总股票 {total_symbols} | 最新日期 {latest} | 总交易日 {len(dates)}")
    for d in dates[-5:]:
        n = (kdf["date"] == d).sum()
        cov = n / total_symbols
        flag = "✅" if cov >= THRESHOLD else "❌"
        print(f"  {flag} {d}: {n}/{total_symbols} ({cov:.1%})")
        if cov < THRESHOLD:
            alerts.append(f"K线覆盖率不足 {d}: {n}/{total_symbols} ({cov:.1%}) < {THRESHOLD:.0%}")
    # 是否最新到最近交易日
    result = {"ok": len(alerts) == 0, "latest_date": latest, "coverage": {}, "alerts": alerts}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not alerts else 2

if __name__ == "__main__":
    sys.exit(main())
