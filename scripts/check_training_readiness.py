#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查训练数据完备性 — 本地是否能运行训练"""
import os, sys, json
from pathlib import Path

ROOT = Path("C:\\Users\\elvisq\\Projects\\alphapilot")
os.chdir(str(ROOT))
sys.path.insert(0, str(ROOT))

print("=" * 60)
print("AlphaPilot 训练数据就绪检查")
print("=" * 60)

# 1. K线缓存
kf = ROOT / "data" / "kline_cache" / "kline_all.parquet"
if kf.exists():
    import pandas as pd
    kdf = pd.read_parquet(kf)
    print(f"\n[K线缓存] {len(kdf)} 行, {kdf['symbol'].nunique()} 只")
    if "date" in kdf.columns:
        print(f"  日期范围: {kdf['date'].min()} ~ {kdf['date'].max()}")
else:
    print(f"\n[K线缓存] 不存在: {kf}")

# 2. 侧车数据
side_files = {
    "资金流向": "data/fund_flow_history.json",
    "融资融券": "data/margin_data.json",
    "业绩预告": "data/event_forecast.json",
    "基本面": "data/fundamental_data.json",
    "筹码": "data/chip_data_all.json",
    "龙虎榜": "data/lhb_history.json",
}
print("\n[侧车数据]")
for label, path in side_files.items():
    p = ROOT / path
    alt = ROOT / path.replace("data/", "")
    if p.exists():
        sz = p.stat().st_size / 1024
        status = "OK" if sz > 5 else "可能为空"
        print(f"  {label:8s} {sz:>7.0f} KB  ({status})")
    elif alt.exists():
        sz = alt.stat().st_size / 1024
        print(f"  {label:8s} {sz:>7.0f} KB  (根路径)")
    else:
        print(f"  {label:8s}   MISSING")

# 3. 模型目录
mdir = ROOT / "models"
if mdir.exists():
    ubj = list(mdir.glob("*.ubj"))
    print(f"\n[模型] {len(ubj)} 个模型文件")
    for u in ubj:
        print(f"  {u.name} {u.stat().st_size/1024:.0f} KB")
else:
    print("\n[模型] 目录不存在")

# 4. 集合竞价因子模块
try:
    from call_auction_factors import ALL_FACTORS, compute_auction_factors
    print(f"\n[集合竞价因子] 模块加载 OK, {len(ALL_FACTORS)} 个因子")
except Exception as e:
    print(f"\n[集合竞价因子] 模块加载失败: {e}")

# 5. features_v2 集成测试
print("\n[特征管线集成测试]")
import numpy as np
import pandas as pd

dates = pd.date_range("2025-01-01", "2026-07-03", freq="B")
np.random.seed(42)
test_df = pd.DataFrame({
    "date": dates,
    "open": 10 + np.random.randn(len(dates)).cumsum() * 0.1,
    "high": 0, "low": 0, "close": 0,
    "volume": np.random.randint(1e7, 5e7, len(dates)),
    "amount": np.random.randint(1e9, 5e9, len(dates)),
})
test_df["close"] = test_df["open"] + np.random.randn(len(dates)) * 0.2
test_df["high"] = test_df[["open", "close"]].max(axis=1) + 0.1
test_df["low"] = test_df[["open", "close"]].min(axis=1) - 0.1
test_df["close"] = test_df["close"].clip(lower=5)

from features_v2 import build_full_features_v2, V11_FEATURE_COLUMNS
feats = build_full_features_v2(test_df)
print(f"  V11_FEATURE_COLUMNS: {len(V11_FEATURE_COLUMNS)} 列定义")
print(f"  实际产出: {feats.shape[1]} 列")

auction_cols = [c for c in feats.columns if c.startswith("rd_auction")]
print(f"  集合竞价因子列: {len(auction_cols)} 个")
missing = [c for c in V11_FEATURE_COLUMNS if c not in feats.columns]
if missing:
    print(f"  缺失列: {missing}")
else:
    print("  OK: 所有特征列均存在")

latest = feats.iloc[-1]
for col in auction_cols[:5]:
    val = latest[col]
    print(f"  {col}: {val:.4f}")

# 6. vm25_scorer 加载测试
print("\n[VM25Scorer 加载测试]")
try:
    from vm25_scorer import VM25Scorer
    scorer = VM25Scorer(prefer="opt")
    ok = scorer.load()
    if ok:
        print(f"  OK: 模型加载成功, {len(scorer.feature_names)} 特征")
        feat_auction = [c for c in scorer.feature_names if c.startswith("rd_auction")]
        print(f"  特征中包含 rd_auction: {len(feat_auction)} 个")
    else:
        print("  模型未加载（需先训练）")
except Exception as e:
    print(f"  VM25Scorer: {e}")

print(f"\n{'='*60}")
print("检查完成")
print(f"{'='*60}")