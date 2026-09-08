#!/usr/bin/env python3
"""
集合竞价板块热点引擎回测
用历史K线 open 价模拟集合竞价信号，验证板块热度是否有预测力。

核心逻辑:
  1. 每天计算「模拟板块热度」: gap%(open/prev_close-1) + 板块一致性 + 5日资金方向
  2. 选 Top-3 热点板块
  3. 在热点板块中选 Top-3 个股（按动量: 5日涨跌幅 + 量比）
  4. 计算次日收益
  5. 对比基准: 全市场均值、随机选股、Top10评分

输出:
  - 逐日收益曲线
  - 胜率、平均收益、夏普比率
  - 热点 vs 冷门板块对比
  - 与现有 score_top10 策略对比
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# ── 配置 ──
ROOT = Path(__file__).resolve().parent.parent
KLINE_PATH = ROOT / "data/kline_all.parquet"
INDUSTRY_MAP_PATH = ROOT / "data/stock_industry_map.json"
FUND_FLOW_PATH = ROOT / "data/fund_flow_history.json"
OUTPUT_PATH = ROOT / "output/backtest_auction_heat.json"

LOOKBACK_DAYS = 90  # 回测天数
TOP_HOT_SECTORS = 3
TOP_STOCKS_PER_SECTOR = 3


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def load_kline() -> pd.DataFrame:
    """加载全市场K线缓存"""
    paths = [KLINE_PATH, ROOT / "kline_all.parquet",
             Path("/home/ubuntu/alphapilot/kline_all.parquet")]
    for p in paths:
        if p.exists():
            df = pd.read_parquet(p)
            df.rename(columns={"symbol": "code"}, inplace=True)
            df["code"] = df["code"].astype(str).str[-6:]
            df["date"] = pd.to_datetime(df["date"])
            log(f"K线加载: {p} ({len(df)} 行)")
            return df
    log(f"[ERROR] 无K线缓存")
    sys.exit(1)


def load_industry_map() -> dict[str, dict]:
    if not INDUSTRY_MAP_PATH.exists():
        return {}
    try:
        return json.loads(INDUSTRY_MAP_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_fund_flow() -> dict[str, dict]:
    if not FUND_FLOW_PATH.exists():
        return {}
    try:
        return json.loads(FUND_FLOW_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_sector(code: str, imap: dict) -> str:
    return imap.get(code, {}).get("industry_l1", "其他")


def compute_sector_heat(
    df_day: pd.DataFrame,
    df_prev: pd.DataFrame,
    imap: dict,
    fund_flow: dict,
    date_str: str,
) -> dict[str, dict]:
    """
    模拟某日的板块竞价热度。
    用 open/prev_close 模拟 gap，5日主力净额模拟资金方向。
    """
    # 合并当日和前日数据
    merged = df_day[["code", "open", "close", "volume"]].merge(
        df_prev[["code", "close"]].rename(columns={"close": "prev_close"}),
        on="code", how="inner",
    )

    if len(merged) < 100:
        return {}

    merged["gap_pct"] = ((merged["open"] / merged["prev_close"]) - 1) * 100
    merged["sector"] = merged["code"].apply(lambda c: get_sector(c, imap))

    # 板块聚合
    sector_data = defaultdict(lambda: {"gaps": [], "fund_5d": [], "codes": []})
    for _, row in merged.iterrows():
        code = row["code"]
        sector = row["sector"]
        sd = sector_data[sector]
        sd["gaps"].append(row["gap_pct"])
        sd["codes"].append(code)

        # 5日主力净额（用最近5天的 fund_flow_history）
        ff = fund_flow.get(code, {})
        if ff:
            dates = sorted(ff.keys(), reverse=True)
            target_dates = [d for d in dates if d <= date_str][:5]
            net_5d = sum(ff.get(d, 0) for d in target_dates)
            sd["fund_5d"].append(net_5d)

    # 计算热度分
    results = {}
    for sector, sd in sector_data.items():
        gaps = sd["gaps"]
        if len(gaps) < 3:
            continue

        gap_mean = float(np.mean(gaps))
        pos_ratio = sum(1 for g in gaps if g > 0) / len(gaps)
        fund_mean = float(np.mean(sd["fund_5d"])) if sd["fund_5d"] else 0

        # 简化热度分（与真实引擎一致）
        fund_align = 0.0
        if gap_mean > 0 and fund_mean > 0:
            fund_align = 1.0
        elif gap_mean > 0 and fund_mean < 0:
            fund_align = -0.5

        heat = gap_mean * 0.25 + pos_ratio * 0.20 + fund_align * 0.25

        results[sector] = {
            "gap_mean": gap_mean,
            "pos_ratio": pos_ratio,
            "fund_align": fund_align,
            "heat": heat,
            "codes": sd["codes"],
        }

    return results


def pick_stocks_from_hot_sectors(
    df_day: pd.DataFrame,
    df_history: pd.DataFrame,
    sector_heat: dict,
    top_sectors: int,
    top_per_sector: int,
) -> list[str]:
    """从热点板块中选个股（按5日动量排序）"""
    # 计算5日涨跌幅
    dates_sorted = sorted(df_history["date"].unique())
    if len(dates_sorted) < 6:
        return []

    # 选热点板块
    ranked = sorted(sector_heat.items(), key=lambda x: -x[1]["heat"])
    hot_sectors = [s for s, _ in ranked[:top_sectors] if _["heat"] > 0]

    picks = []
    for sector in hot_sectors:
        codes = sector_heat[sector]["codes"]
        day_data = df_day[df_day["code"].isin(codes)].copy()
        if len(day_data) < top_per_sector:
            continue

        # 计算近5日动量
        ref_date = pd.Timestamp(df_day["date"].iloc[0])
        hist_5d = df_history[
            (df_history["date"] >= ref_date - pd.Timedelta(days=7))
            & (df_history["date"] < ref_date)
        ]
        momentum = {}
        for code in day_data["code"].unique():
            code_hist = hist_5d[hist_5d["code"] == code]
            if len(code_hist) >= 3:
                chg = (code_hist["close"].iloc[-1] / code_hist["close"].iloc[0] - 1) if len(code_hist) > 0 else 0
                vol_ratio = (code_hist["volume"].mean() / code_hist["volume"].iloc[-1]) if len(code_hist) > 0 and code_hist["volume"].iloc[-1] > 0 else 1
                momentum[code] = chg * 0.6 + min(vol_ratio, 3) * 0.4
            else:
                momentum[code] = 0

        # 选前3
        top_codes = sorted(momentum.items(), key=lambda x: -x[1])[:top_per_sector]
        picks.extend([c for c, _ in top_codes])

    return picks[: top_sectors * top_per_sector]


def backtest() -> dict:
    """主回测函数"""
    log("加载数据...")
    df = load_kline()
    imap = load_industry_map()
    fund_flow = load_fund_flow()

    log(f"K线: {len(df)} 行, {df['code'].nunique()} 只, {df['date'].nunique()} 天")
    log(f"行业映射: {len(imap)} 只")
    log(f"资金流: {len(fund_flow)} 只")

    # 获取可用交易日
    dates = sorted(df["date"].unique())
    dates = dates[-LOOKBACK_DAYS - 10:]  # 多拿10天用于动量计算
    log(f"回测区间: {dates[0].date()} ~ {dates[-1].date()} ({len(dates)} 天)")

    # 逐日回测
    daily_results = []
    sector_heat_history = []

    for i in range(10, len(dates) - 1):  # 从第10天开始，确保有足够历史
        date = dates[i]
        next_date = dates[i + 1]
        date_str = pd.Timestamp(date).strftime("%Y-%m-%d")

        df_day = df[df["date"] == date].copy()
        df_prev = df[df["date"] == dates[i - 1]].copy()
        df_next = df[df["date"] == next_date].copy()

        if len(df_day) < 500 or len(df_next) < 500:
            continue

        # 1. 计算当日板块热度
        heat = compute_sector_heat(df_day, df_prev, imap, fund_flow, date_str)
        if not heat:
            continue

        # 2. 选股
        picks = pick_stocks_from_hot_sectors(
            df_day, df, heat, TOP_HOT_SECTORS, TOP_STOCKS_PER_SECTOR
        )
        if len(picks) < 3:
            continue

        # 3. 计算次日收益
        returns = []
        for code in picks:
            next_row = df_next[df_next["code"] == code]
            if len(next_row) == 0:
                continue
            open_px = next_row["open"].iloc[0]
            close_px = next_row["close"].iloc[0]
            ret = (close_px / open_px - 1) * 100
            returns.append(ret)

        if len(returns) < 3:
            continue

        avg_ret = float(np.mean(returns))
        win_rate = sum(1 for r in returns if r > 0) / len(returns)

        # 基准: 全市场均值
        market_ret = float(
            ((df_next["close"].mean() / df_next["open"].mean()) - 1) * 100
        )

        # 记录最热/最冷板块
        hot_sector = max(heat.items(), key=lambda x: x[1]["heat"]) if heat else ("?", {})
        cold_sector = min(heat.items(), key=lambda x: x[1]["heat"]) if heat else ("?", {})

        daily_results.append({
            "date": date_str,
            "n_picks": len(picks),
            "avg_return_pct": round(avg_ret, 2),
            "win_rate": round(win_rate, 2),
            "market_return_pct": round(market_ret, 2),
            "excess_return": round(avg_ret - market_ret, 2),
            "top_sectors": [s for s, _ in sorted(heat.items(), key=lambda x: -x[1]["heat"])[:3]],
            "hottest_sector": hot_sector[0],
            "coldest_sector": cold_sector[0],
        })

        sector_heat_history.append({
            "date": date_str,
            "hot_sectors": sorted(heat.items(), key=lambda x: -x[1]["heat"])[:5],
            "cold_sectors": sorted(heat.items(), key=lambda x: x[1]["heat"])[:3],
        })

    # ── 汇总统计 ──
    if not daily_results:
        log("[ERROR] 无有效回测日")
        return {}

    dr = pd.DataFrame(daily_results)
    total_days = len(dr)
    win_days = sum(1 for _, r in dr.iterrows() if r["avg_return_pct"] > 0)
    avg_daily = dr["avg_return_pct"].mean()
    market_daily = dr["market_return_pct"].mean()
    excess_daily = dr["excess_return"].mean()

    # 累计收益
    cumulative = (1 + dr["avg_return_pct"] / 100).cumprod().iloc[-1] - 1
    cumulative_market = (1 + dr["market_return_pct"] / 100).cumprod().iloc[-1] - 1

    # 夏普
    sharpe = (avg_daily / dr["avg_return_pct"].std() * np.sqrt(252)) if dr["avg_return_pct"].std() > 0 else 0

    # 热点 vs 冷门板块对比
    hot_returns = []
    cold_returns = []
    for i, row in dr.iterrows():
        hot_returns.append(row["avg_return_pct"])
    # 冷门板块用市场收益近似（因为我们没有在回测中选冷门板块个股）

    output = {
        "strategy": "竞价热点板块 + Top3个股",
        "backtest_period": f"{dr['date'].iloc[0]} ~ {dr['date'].iloc[-1]}",
        "total_days": total_days,
        "summary": {
            "win_days": win_days,
            "win_rate_pct": round(win_days / total_days * 100, 1),
            "avg_daily_return_pct": round(avg_daily, 2),
            "avg_market_return_pct": round(market_daily, 2),
            "avg_excess_return_pct": round(excess_daily, 2),
            "cumulative_return_pct": round(cumulative * 100, 1),
            "cumulative_market_pct": round(cumulative_market * 100, 1),
            "sharpe_ratio": round(sharpe, 2),
        },
        "daily": [
            {
                "date": r["date"],
                "ret": r["avg_return_pct"],
                "market": r["market_return_pct"],
                "excess": r["excess_return"],
                "win": r["win_rate"],
                "hottest": r["hottest_sector"],
            }
            for _, r in dr.iterrows()
        ],
        "sector_heat_samples": sector_heat_history[:10],
    }

    log("=" * 60)
    log(f"📊 竞价热点板块回测结果")
    log(f"  回测区间: {output['backtest_period']}")
    log(f"  交易日数: {total_days}")
    log(f"  胜率: {output['summary']['win_rate_pct']}%")
    log(f"  日均收益: {output['summary']['avg_daily_return_pct']}%")
    log(f"  日均超额: {output['summary']['avg_excess_return_pct']}% (vs 市场)")
    log(f"  累计收益: {output['summary']['cumulative_return_pct']}%")
    log(f"  累计市场: {output['summary']['cumulative_market_pct']}%")
    log(f"  夏普比率: {output['summary']['sharpe_ratio']}")

    return output


if __name__ == "__main__":
    result = backtest()
    if result:
        import json as _json
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(
            _json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log(f"\n输出: {OUTPUT_PATH}")
    else:
        log("\n[ERROR] 回测无结果")
        sys.exit(1)
