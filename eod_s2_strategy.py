#!/usr/bin/env python3
"""
尾盘选股策略引擎 — S2最优版
基于 Manus 回测分析报告的策略二（8步法）+ 策略一（放量突破）量比加强

核心逻辑（S2最优版）：
  1. 涨幅 +1% ~ +7%      ← 性价比区间
  2. 量比 > 1.5          ← S1 加强条件
  3. 均线多头排列          ← close > MA5 > MA10 > MA20
  4. 收盘强度 < 0.05      ← (high-close)/high < 0.05（收盘近最高）
  5. 站上均价线            ← close > VWAP
  6. 20日波动率排序选Top1  ← 回测最优

输出: output/eod_s2_picks.json
"""

import os, sys, json, time, numpy as np, pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from data_fetcher import get_kline_sina, get_stock_list
from enriched_data import get_quote

OUTPUT_FILE = "output/eod_s2_picks.json"
KLINE_CACHE = "data/kline_cache/kline_all.parquet"

# 筹码数据
_CHIP_DATA = None
def _load_chip_data():
    global _CHIP_DATA
    if _CHIP_DATA is not None:
        return _CHIP_DATA
    try:
        import json
        with open("chip_data_all.json") as f:
            _CHIP_DATA = {k.split(".")[0] if "." in k else k: v for k, v in json.load(f).items()}
    except:
        _CHIP_DATA = {}
    return _CHIP_DATA

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def calc_ma(df: pd.DataFrame, period: int) -> float:
    """计算最近 N 日均线"""
    if df is None or len(df) < period:
        return None
    return df["close"].tail(period).mean()

def calc_volatility(df: pd.DataFrame, period: int = 20) -> float:
    """计算 N 日波动率（日收益率标准差）"""
    if df is None or len(df) < period:
        return 0
    returns = df["close"].pct_change().dropna().tail(period)
    return float(returns.std()) if len(returns) >= period else 0

def check_bullish_ma(df: pd.DataFrame) -> bool:
    """均线多头排列: close > MA5 > MA10 > MA20"""
    if df is None or len(df) < 20:
        return False
    close = df["close"].iloc[-1]
    ma5 = df["close"].tail(5).mean()
    ma10 = df["close"].tail(10).mean()
    ma20 = df["close"].tail(20).mean()
    return close > ma5 > ma10 > ma20

def check_close_strength(row) -> bool:
    """收盘强度: (high - close) / high < 0.05"""
    if row is None or row["high"] == 0:
        return False
    return (row["high"] - row["close"]) / row["high"] < 0.05

def main():
    log("=" * 60)
    log("尾盘 S2最优版 策略引擎")
    log("=" * 60)
    
    # 1. 获取全市场股票列表
    stocks = get_stock_list()
    all_symbols = stocks["symbol"].tolist()
    log(f"全市场: {len(all_symbols)} 只")
    
    # 2. 加载 K 线数据（优先本地缓存）
    kline_cache = {}
    if os.path.isfile(KLINE_CACHE):
        try:
            kdf = pd.read_parquet(KLINE_CACHE)
            for sym in kdf["symbol"].unique():
                sdf = kdf[kdf["symbol"] == sym].sort_values("date")
                if len(sdf) >= 20:
                    kline_cache[sym] = sdf
            log(f"K线缓存: {len(kline_cache)} 只")
        except Exception as e:
            log(f"  ⚠️ 缓存加载失败: {e}")
    
    # 3. 获取实时行情 & 计算指标
    candidates = []
    today = datetime.now().strftime("%Y-%m-%d")
    
    for i, symbol in enumerate(all_symbols):
        if i % 500 == 0 and i > 0:
            log(f"  进度: {i}/{len(all_symbols)}")
        
        try:
            # 获取实时行情
            quote = get_quote(symbol)
            if not quote:
                continue
            
            price = float(quote.get("price", 0) or 0)
            prev_close = float(quote.get("prev_close", 0) or 0)
            change_pct = float(quote.get("change_pct", 0) or 0)
            volume_ratio = float(quote.get("volume_ratio", 0) or 0)
            high = float(quote.get("high", 0) or 0)
            low = float(quote.get("low", 0) or 0)
            volume = float(quote.get("volume", 0) or 0)
            amount = float(quote.get("amount", 0) or 0)
            turnover = float(quote.get("turnover", 0) or 0)
            name = quote.get("name", "")
            
            # 筛选1: 涨幅 +1% ~ +7%
            if change_pct < 1.0 or change_pct > 7.0:
                continue
            
            # 筛选2: 量比 > 1.5
            if volume_ratio < 1.5:
                continue
            
            # 获取日K线（计算均线、波动率）
            df = kline_cache.get(symbol)
            if df is None or len(df) < 20:
                continue
            
            # 筛选3: 均线多头排列
            if not check_bullish_ma(df):
                continue
            
            # 筛选4: 收盘强度
            latest_k = df.iloc[-1]
            if not check_close_strength(latest_k):
                continue
            
            # 筛选5: 站上均价线 (approximate VWAP)
            # 用 typical price * volume 近似
            typical_price = (high + low + price) / 3
            vwap = amount / volume if volume > 0 else typical_price
            if price < vwap:
                continue
            
            # 20日波动率
            vol20 = calc_volatility(df)
            
            # ── 筹码峰条件 ──
            chip_bonus = 0
            chip = _load_chip_data().get(symbol)
            if chip:
                # 筹码穿透率 > 0.5 → 上方阻力小
                penetration = float(chip.get("chipPenetration", 0))                     if "chipPenetration" in chip else float(chip.get("chip_penetration", 0))
                if penetration > 0.05:
                    chip_bonus += 1.5
                
                # 成本重心偏移 → 主力加仓
                cost_shift = float(chip.get("avgCostShift5d", 0))                     if "avgCostShift5d" in chip else 0
                if cost_shift > 0.01:
                    chip_bonus += 1.0
                
                # 获利盘高 → 趋势好
                profit_rate = float(chip.get("chipProfitRate", 0))
                if profit_rate > 40:
                    chip_bonus += 0.5

            
            # 流通市值估算 (price * turnover / turnover_rate)
            mkt_cap = price * (volume / (turnover / 100 if turnover > 0 else 1))
            
            candidates.append({
                "symbol": symbol,
                "name": name,
                "price": price,
                "change_pct": change_pct,
                "volume_ratio": volume_ratio,
                "volatility_20d": vol20,
                "turnover": turnover,
                "close_vs_high": (high - price) / high if high > 0 else 100,
                "market_cap": mkt_cap,
                "chip_bonus": chip_bonus,
            })
        except Exception:
            continue
    
    log(f"筛选完成: {len(candidates)} 只通过")
    
    # 6. 按20日波动率排序选Top1
    if candidates:
        candidates.sort(key=lambda x: x["volatility_20d"] + x.get("chip_bonus",0), reverse=True)
        top = candidates[:5]  # Top5 展示
    else:
        top = []
    
    # 保存结果
    output = {
        "generated_at": datetime.now().isoformat(),
        "generated_time": datetime.now().strftime("%H:%M"),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "total_screened": len(all_symbols),
        "total_passed": len(candidates),
        "strategy": "S2最优版",
        "picks": top,
        "note": "按20日波动率排序，Top1为最强信号" if top else "今日无符合条件的信号",
    }
    
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)
    
    if top:
        log(f"\n🏆 S2最优版 Top5:")
        for i, c in enumerate(top[:3]):
            log(f"  {i+1}. {c['name']} ({c['symbol']}) 涨跌={c['change_pct']:+.2f}% "
                f"量比={c['volume_ratio']:.1f} 波动率={c['volatility_20d']:.4f}")
        
        log(f"\n✅ Top1: {top[0]['name']} ({top[0]['symbol']})")
    else:
        log("❌ 今日无符合 S2最优版 条件的标的")
    
    log(f"✅ 结果保存: {OUTPUT_FILE}")



    # ── 写入 Paper Trading 信号 ──
    PT_PATH = "data/paper_trading.json"
    if os.path.exists(PT_PATH) and top:
        with open(PT_PATH) as f:
            pt = json.load(f)
        c = top[0]
        price = c["price"]
        signal = {
            "symbol": c["symbol"],
            "name": c["name"],
            "score": c["volatility_20d"] + c.get("chip_bonus", 0),
            "action": "buy",
            "price": price,
            "target_price": round(price * 1.05, 2),
            "stop_price": round(price * 0.97, 2),
            "quantity": int(50000 / price / 100) * 100,
            "strategy_id": "s2_eod",
            "reason": "S2尾盘狙击（规则引擎）",
        }
        existing = set()
        for s in pt.get("strategies", []):
            for p in s.get("positions", []):
                existing.add(p.get("symbol", ""))
        if c["symbol"] not in existing:
            found_s2 = False
            for s in pt["strategies"]:
                if s["id"] == "s2_eod":
                    s["signals"] = [signal]
                    found_s2 = True
                    break
            if not found_s2:
                pt["strategies"].append({"id": "s2_eod", "name": "S2尾盘狙击", "status": "active", "allocated": 500000, "used": 0, "signals": [signal], "positions": []})
            with open(PT_PATH, "w") as f:
                json.dump(pt, f, ensure_ascii=False, indent=2)
            log("  ✅ S2 Top1 已写入 Paper Trading")

if __name__ == "__main__":
    main()
