#!/usr/bin/env python3
"""
AlphaPilot 自动因子引擎
1. 从历史数据生成候选因子（基础因子 → 衍生因子）
2. IC 检验 + 相关性去重 + 重要性排序
3. 输出精选因子列表
"""
import sys, os, time, json, warnings, pickle
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, "/home/ubuntu/alphapilot")
warnings.filterwarnings("ignore")

BASE = Path("/home/ubuntu/alphapilot")
OUTPUT = BASE / "output"
OUTPUT.mkdir(exist_ok=True)

from data_fetcher import get_stock_list, get_kline_sina
import features as ft
from enriched_data import get_quote

MAX_WORKERS = 10
STOCK_SAMPLE = 4992
MAX_DAYS = 250

# ── 因子衍生函数 ──
def derive_factors(base_df):
    """从22维基础因子生成60+候选因子"""
    factors = pd.DataFrame(index=base_df.index)
    
    # 基础因子
    for col in ft.FEATURE_COLUMNS:
        if col in base_df.columns:
            factors[col] = base_df[col].values
    
    # 1. 滚动统计
    for col in ['vol_ma_ratio', 'turnover', 'amt_ma_ratio', 'atr_pct', 'active_buy_ratio']:
        if col not in base_df.columns: continue
        series = base_df[col].values
        factors[f'{col}_ma3'] = pd.Series(series).rolling(3).mean().values if len(series)>=3 else series
        factors[f'{col}_std5'] = pd.Series(series).rolling(5).std().values if len(series)>=5 else np.zeros(len(series))
        ma5 = pd.Series(series).rolling(5).mean().values if len(series)>=5 else np.full(len(series), np.nan)
        factors[f'{col}_zscore'] = np.where(
            factors[f'{col}_std5'].values > 1e-8,
            (series - ma5) / (factors[f'{col}_std5'].values + 1e-8),
            0
        )
    
    # 2. 量价交叉
    if all(c in base_df.columns for c in ['vol_ma_ratio', 'close_vs_ma']):
        factors['volume_price'] = base_df['vol_ma_ratio'].values * base_df['close_vs_ma'].values
    if all(c in base_df.columns for c in ['vol_ma_ratio', 'turnover']):
        factors['vol_turnover'] = base_df['vol_ma_ratio'].values * base_df['turnover'].values
    if all(c in base_df.columns for c in ['active_buy_ratio', 'vol_ma_ratio']):
        factors['money_flow_vol'] = base_df['active_buy_ratio'].values * base_df['vol_ma_ratio'].values
    
    # 3. 动量加速
    if 'ret_5d' in base_df.columns and 'ret_1d' in base_df.columns:
        factors['momentum_accel'] = base_df['ret_5d'].values - base_df['ret_1d'].values
    if 'ma_direction' in base_df.columns and 'vol_trend_5d' in base_df.columns:
        factors['trend_strength'] = base_df['ma_direction'].values * base_df['vol_trend_5d'].values
    
    # 4. 乖离率
    if 'ma_convergence' in base_df.columns and 'atr_pct' in base_df.columns:
        factors['conv_div'] = base_df['ma_convergence'].values / (base_df['atr_pct'].values + 1e-6)
    if 'close_vs_ma' in base_df.columns and 'ma_dist_pct' in base_df.columns:
        factors['price_dev'] = base_df['close_vs_ma'].values - base_df['ma_dist_pct'].values
    
    # 5. 筹码衍生
    if 'chip_concentration' in base_df.columns:
        if 'vol_ma_ratio' in base_df.columns:
            factors['chip_vol'] = base_df['chip_concentration'].values * base_df['vol_ma_ratio'].values
        factors['chip_reverse'] = 1.0 / (base_df['chip_concentration'].values + 1e-6)
    
    # 6. 上涨趋势
    if all(c in base_df.columns for c in ['consecutive_up', 'vol_shrink_days']):
        factors['bull_confirmation'] = base_df['consecutive_up'].values * (base_df['vol_shrink_days'].values < 2).astype(float)
    
    # 7. 价格位置
    if 'price_percentile_60' in base_df.columns:
        # 中低位+资金流入 = 买入信号
        if 'active_buy_ratio' in base_df.columns:
            factors['low_price_buy'] = ((base_df['price_percentile_60'].values < 0.5).astype(float) 
                                        * base_df['active_buy_ratio'].values)
    
    return factors


def process_stock(sym, name=""):
    """处理单只股票：获取数据 → 构建因子 → 计算未来收益"""
    try:
        kline = get_kline_sina(sym, "20230701")
        if kline.empty or len(kline) < 120:
            return None
        kline = kline.tail(MAX_DAYS).reset_index(drop=True)
        q = get_quote(sym)
        active_buy = q.get("active_buy_ratio", 0.5) if q else 0.5
        feats = ft.build_full_features(kline, symbol=sym, active_buy_ratio=active_buy)
        if feats.empty:
            return None
        
        # 基础因子
        base = feats[ft.FEATURE_COLUMNS].copy()
        base.columns = [c.strip() for c in base.columns]
        
        # 衍生因子
        derived = derive_factors(base)
        
        # 合并
        all_factors = pd.concat([base, derived], axis=1)
        
        # 计算未来收益（明日涨跌幅）
        future_ret = kline['close'].pct_change(1).shift(-1).values[-len(all_factors):]
        future_ret = np.where(future_ret > 0.03, 1, 0)  # 二分类：是否涨≥3%
        
        # 取最新的有效行
        valid = ~np.isnan(future_ret) & (all_factors.notna().all(axis=1).values)
        if valid.sum() < 10:
            return None
        
        result = all_factors[valid].copy()
        result['_target'] = future_ret[valid]
        result['_symbol'] = sym
        return result
    except Exception as e:
        return None


def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] === 自动因子引擎启动 ===")
    t0 = time.time()
    
    # 1. 采样股票
    stocks = get_stock_list()
    if len(stocks) > STOCK_SAMPLE:
        stocks = stocks.sample(n=STOCK_SAMPLE, random_state=42)
    print(f"采样 {len(stocks)} 只股票")
    
    # 2. 并行处理
    all_data = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        fut = {ex.submit(process_stock, r["symbol"], r.get("name","")): r["symbol"] for _, r in stocks.iterrows()}
        for i, f in enumerate(as_completed(fut), 1):
            r = f.result()
            if r is not None:
                all_data.append(r)
            if i % 50 == 0:
                print(f"  进度 {i}/{len(stocks)}, 有效 {len(all_data)}")
    
    if not all_data:
        print("错误：无有效数据")
        return
    
    df = pd.concat(all_data, ignore_index=True)
    target = np.asarray(df['_target'].values).ravel()
    factor_cols = [c for c in df.columns if not c.startswith('_')]
    
    print(f"\n有效样本: {len(df)}, 因子数: {len(factor_cols)}")
    
    # 3. IC 检验
    ic_results = []
    for col in factor_cols:
        vals_raw = df[col].values
        if vals_raw.ndim > 1:
            vals_raw = vals_raw[:, 0] if vals_raw.shape[1] == 2 else vals_raw.ravel()
        mask = ~np.isnan(vals_raw)
        if mask.sum() < 30:
            continue
        ic, pval = spearmanr(vals_raw[mask], target[mask])
        ic_results.append({'factor': col, 'ic': ic, 'pval': pval, 'samples': mask.sum()})
    
    ic_df = pd.DataFrame(ic_results)
    ic_df['ic_abs'] = ic_df['ic'].abs()
    ic_df = ic_df.sort_values('ic_abs', ascending=False)
    
    # 4. 筛选：IC显著 + 去重
    ic_sig = ic_df[ic_df['pval'] < 0.1].copy()
    print(f"\nIC显著因子: {len(ic_sig)}/{len(ic_df)}")
    
    # 相关性去重
    sig_cols = ic_sig['factor'].tolist()
    if len(sig_cols) > 1:
        corr_matrix = df[sig_cols].corr().abs()
        keep = set()
        for col in sig_cols:
            if col not in keep:
                # 找与col高度相关的其他因子
                high_corr = corr_matrix[col][corr_matrix[col] > 0.85].index.tolist()
                # 保留IC最高的
                ic_vals = {c: ic_df[ic_df['factor']==c]['ic_abs'].values[0] for c in high_corr}
                best = max(ic_vals, key=ic_vals.get)
                keep.add(best)
        print(f"去重后: {len(keep)} 个因子")
    else:
        keep = set(sig_cols)
    
    # 5. 保存结果
    final_factors = []
    for col in sorted(keep):
        row = ic_df[ic_df['factor']==col].iloc[0]
        final_factors.append({'factor': col, 'ic': round(row['ic'], 4), 'pval': round(row['pval'], 4)})
    
    result = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'total_candidates': len(factor_cols),
        'ic_significant': len(ic_sig),
        'after_dedup': len(final_factors),
        'factors': final_factors,
        'top10': [f for f in final_factors[:10]],
    }
    
    out_path = OUTPUT / 'factor_engine_result.json'
    with open(out_path, 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*50}")
    print(f"因子引擎完成！耗时 {time.time()-t0:.0f}s")
    print(f"候选因子: {len(factor_cols)} → IC显著: {len(ic_sig)} → 去重后: {len(final_factors)}")
    print(f"Top 10 因子:")
    for f in final_factors[:10]:
        print(f"  {f['factor']:30s} IC={f['ic']:+.4f}  p={f['pval']:.4f}")
    print(f"\n结果保存: {out_path}")


if __name__ == '__main__':
    main()
