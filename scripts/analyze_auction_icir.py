#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
集合竞价因子 IC/IR 分析
=========================
使用本地 K 线缓存 + 侧车数据，计算各集合竞价因子的：
  - Spearman Rank IC (next-day return)
  - ICIR (IC_mean / IC_std)
  - 与现有 top 因子的 IC 对比

用法: python scripts/analyze_auction_icir.py [--sample 500] [--start 2025-01-01]
"""
import os, sys, json, time, warnings
from pathlib import Path

ROOT = Path(os.environ.get("ALPHAPILOT_ROOT") or str(Path(__file__).resolve().parent.parent))
os.chdir(str(ROOT))
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

# ── 参数 ──
SAMPLE = 500
START_DATE = "2025-01-01"
FORWARD_DAYS = 1

# ── 加载 K 线缓存 ──
kf = ROOT / "data" / "kline_cache" / "kline_all.parquet"
if not kf.exists():
    # 回退到根目录
    kf = ROOT / "kline_all.parquet"
    if not kf.exists():
        print("ERROR: K-line cache not found")
        sys.exit(1)

print(f"Loading K-line from {kf} ...")
kdf = pd.read_parquet(kf)
print(f"  {len(kdf)} rows, {kdf['symbol'].nunique()} stocks")

# ── 尝试加载侧车数据 ──
from data_fetcher import get_stock_list
symbols = get_stock_list()["symbol"].tolist()
print(f"Total symbols: {len(symbols)}")

# 侧车数据
def load_json_safe(path):
    p = ROOT / path
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8", errors="ignore"))
        except:
            return {}
    # try alt path
    p2 = ROOT / path.replace("data/", "")
    if p2.exists():
        try:
            return json.loads(p2.read_text(encoding="utf-8", errors="ignore"))
        except:
            return {}
    return {}

def bare(sym):
    s = str(sym).strip()
    if "." in s:
        s = s.split(".")[0]
    return s.zfill(6)[-6:]

fund_flow_raw = load_json_safe("data/fund_flow_history.json")
fund_flow = {bare(k): v for k, v in fund_flow_raw.items() if isinstance(v, dict)}
margin_data = {bare(k): v for k, v in load_json_safe("data/margin_data.json").items() if isinstance(v, dict)}
event_data = {bare(k): v for k, v in load_json_safe("data/event_forecast.json").items() if isinstance(v, dict)}

print(f"\nSide data coverage:")
print(f"  Fund flow: {len(fund_flow)} stocks")
print(f"  Margin:    {len(margin_data)} stocks")
print(f"  Events:    {len(event_data)} stocks")

# ── 采样股票 ──
if SAMPLE and SAMPLE < len(symbols):
    np.random.seed(42)
    sampled = sorted(np.random.choice(symbols, SAMPLE, replace=False).tolist())
else:
    sampled = symbols
print(f"Sampled stocks: {len(sampled)}")

# ── 逐股票计算特征 + 标签 ──
from call_auction_factors import ALL_FACTORS
from features_v2 import build_full_features_v2

IC_COLS = ALL_FACTORS + [
    "gap_pct", "ma_cross_20_60", "ret_5d", "ret_20d", "vol_20d",
    "amount_ratio_5", "amount_ratio_20", "vol_spike", "cmf_20", "vpt_20",
    "rsi_14", "macd", "macd_hist", "bb_width",
    "ma_dist_pct", "atr_pct", "turnover_ratio", "vol_ma_ratio",
    "price_vol_corr_20", "ret_range", "ma_cross_5_20",
    "eps", "roe", "profit_margin",
    "main_net_today", "main_net_5d", "main_net_10d",
    "margin_balance", "margin_buy",
]

results = []
pbar_every = max(1, len(sampled) // 20)

t0 = time.time()
for idx, sym in enumerate(sampled):
    try:
        code = bare(sym)
        kl = kdf[kdf["symbol"] == sym].sort_values("date").copy()
        if len(kl) < 120:
            # try code match
            kl = kdf[kdf["symbol"] == code].sort_values("date").copy()
        if len(kl) < 120:
            continue

        kl = kl.tail(180).reset_index(drop=True)
        kl["date"] = kl["date"].astype(str)

        feats = build_full_features_v2(
            kl,
            fund_hist=fund_flow.get(code),
            margin_data=margin_data.get(code),
            event_data=event_data.get(code),
        )
        if feats is None or len(feats) < 30:
            continue

        # forward return label
        future_ret = feats["close"].shift(-FORWARD_DAYS) / feats["close"] - 1

        # collect each date row
        for ri in range(20, len(feats) - FORWARD_DAYS):
            row = {}
            for c in IC_COLS:
                if c in feats.columns:
                    v = feats.iloc[ri][c]
                    row[c] = float(v) if not (isinstance(v, float) and np.isnan(v)) else None
            row["_ret_fwd"] = float(future_ret.iloc[ri]) if not np.isnan(future_ret.iloc[ri]) else None
            row["_date"] = str(kl.iloc[ri]["date"])[:10]
            row["_symbol"] = code
            results.append(row)

    except Exception:
        continue

    if (idx + 1) % pbar_every == 0:
        elapsed = time.time() - t0
        print(f"  [{elapsed:.0f}s] {idx+1}/{len(sampled)}, collected={len(results)}", flush=True)

print(f"\nTotal observation rows: {len(results)}")

if not results:
    print("ERROR: No observations collected, cannot compute IC")
    sys.exit(1)

# ── 转换为 DataFrame ──
df = pd.DataFrame(results)
print(f"DataFrame: {df.shape}")

# ── 计算 Spearman Rank IC ──
print("\n=== Factor IC Analysis ===")
ic_results = []

for col in IC_COLS:
    if col not in df.columns:
        continue
    sub = df[[col, "_ret_fwd"]].dropna()
    if len(sub) < 100:
        continue
    ic = sub["_ret_fwd"].rank().corr(sub[col].rank(), method="spearman")
    ic_mean = ic  # single IC for now

    # Compute daily IC by date
    daily_ics = []
    for date, grp in df.groupby("_date"):
        sub_d = grp[[col, "_ret_fwd"]].dropna()
        if len(sub_d) < 20:
            continue
        daily_ic = sub_d["_ret_fwd"].rank().corr(sub_d[col].rank(), method="spearman")
        if not np.isnan(daily_ic):
            daily_ics.append(daily_ic)

    if daily_ics:
        icir = float(np.mean(daily_ics)) / (float(np.std(daily_ics)) + 1e-10)
        ic_mean_daily = float(np.mean(daily_ics))
        hit_rate = sum(1 for v in daily_ics if v > 0) / len(daily_ics)
    else:
        icir = 0.0
        ic_mean_daily = float(ic)
        hit_rate = 0.5

    ic_results.append({
        "factor": col,
        "ic_global": round(float(ic), 4),
        "icir": round(icir, 4),
        "ic_mean_daily": round(ic_mean_daily, 4),
        "hit_rate": round(hit_rate, 4),
        "n_dates": len(daily_ics),
        "n_obs": len(sub),
    })

ic_df = pd.DataFrame(ic_results)
ic_df = ic_df.sort_values("icir", ascending=False).reset_index(drop=True)

# ── 输出结果 ──
print(f"\n{'='*70}")
print(f"  IC/IR 排名 (因子 × {len(ic_df)}, 日频 IC 均值)")
print(f"{'='*70}")
print(f"{'Rank':>4} {'Factor':35s} {'IC_global':>9} {'IC_mean':>9} {'ICIR':>9} {'HitRate':>8} {'Days':>5}")
print(f"{'─'*4} {'─'*35} {'─'*9} {'─'*9} {'─'*9} {'─'*8} {'─'*5}")

for i, row in ic_df.iterrows():
    flag = " ★" if row["factor"].startswith("rd_auction") else ""
    if abs(row["icir"]) < 0.02:
        continue  # skip noise
    print(f"{i+1:>4d} {row['factor']:35s} "
          f"{row['ic_global']:>9.4f} {row['ic_mean_daily']:>9.4f} "
          f"{row['icir']:>9.4f} {row['hit_rate']:>8.2%} {row['n_dates']:>5d}{flag}")

# ── 集合竞价因子统计 ──
auction_ics = ic_df[ic_df["factor"].str.startswith("rd_auction")]
print(f"\n{'='*70}")
print(f"  集合竞价因子汇总 ({len(auction_ics)} 个)")
print(f"{'='*70}")
pos_icir = (auction_ics["icir"] > 0).sum()
neg_icir = (auction_ics["icir"] < 0).sum()
print(f"  正向 ICIR: {pos_icir}  |  负向 ICIR: {neg_icir}")
print(f"  平均 |ICIR|: {auction_ics['icir'].abs().mean():.4f}")
print(f"  平均 |IC|:   {auction_ics['ic_global'].abs().mean():.4f}")
print(f"  最大 IC:    {auction_ics['ic_global'].max():.4f}")
print(f"  最小 IC:    {auction_ics['ic_global'].min():.4f}")

print(f"\n{'─'*70}")
print(f"  集合竞价因子 IC/IR 排名:")
print(f"{'─'*70}")
for i, row in auction_ics.sort_values("icir", ascending=False).iterrows():
    print(f"  {row['factor']:40s} IC={row['ic_global']:>.4f} ICIR={row['icir']:>.4f} HR={row['hit_rate']:>.1%}")

# ── 保存 ──
out_dir = ROOT / "output" / "icir_prod"
out_dir.mkdir(parents=True, exist_ok=True)
ic_df.to_json(out_dir / "auction_icir_analysis.json", orient="records", indent=2, force_ascii=False)
print(f"\nSaved: {out_dir / 'auction_icir_analysis.json'}")

# ── 与现有 top 因子比较 ──
print(f"\n{'='*70}")
print(f"  现有 top 因子 vs 集合竞价因子 TOP5")
print(f"{'='*70}")
existing_top = ic_df[~ic_df["factor"].str.startswith("rd_auction")].head(10)
for i, row in existing_top.iterrows():
    print(f"  {row['factor']:40s} IC={row['ic_global']:>.4f} ICIR={row['icir']:>.4f}")
print(f"\n  集合竞价 TOP5:")
top5_auction = auction_ics.sort_values("icir", ascending=False).head(5)
for i, row in top5_auction.iterrows():
    print(f"  {row['factor']:40s} IC={row['ic_global']:>.4f} ICIR={row['icir']:>.4f}")

print(f"\nDone in {time.time()-t0:.0f}s")