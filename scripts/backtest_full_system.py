#!/usr/bin/env python3
"""
全系统回测 — 新旧选股逻辑对比

旧系统: 05:00 管线硬过滤(GC filter) + 09:35 ICIR动量双轨(无管线溢价+无竞价热点)
新系统: 05:00 软门控(A/B臂) + 09:25 竞价热点 + 09:35 ICIR动量+管线溢价+竞价热点

回测 60 天，对比:
  - 日均收益
  - 胜率
  - 累计收益
  - 夏普比率
"""
import json, os, sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/ubuntu/alphapilot")
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

KLINE_PATH = ROOT / "kline_all.parquet"
IMAP_PATH = ROOT / "data" / "stock_industry_map.json"
FUND_FLOW_PATH = ROOT / "data" / "fund_flow_history.json"
OUTPUT = ROOT / "output" / "backtest_full_system_compare.json"

LOOKBACK = 30
TOP_N = 5  # Top-N 选股


def log(msg): print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def load_data():
    df = pd.read_parquet(KLINE_PATH)
    df["date"] = pd.to_datetime(df["date"])
    imap = json.loads(IMAP_PATH.read_text(encoding="utf-8")) if IMAP_PATH.exists() else {}
    ff = json.loads(FUND_FLOW_PATH.read_text(encoding="utf-8")) if FUND_FLOW_PATH.exists() else {}
    return df, imap, ff


def get_sector(code, imap):
    return imap.get(code, {}).get("industry_l1", "其他")


def compute_old_system_scores(df_day, df_prev, imap):
    """旧系统: 纯ICIR模拟 + 硬GC过滤"""
    scores = defaultdict(float)
    gc_set = set()

    for _, row in df_day.iterrows():
        code = row["symbol"]
        o, c, v = row["open"], row["close"], row["volume"]
        prev = df_prev[df_prev["symbol"] == code]
        if len(prev) == 0:
            continue
        pc = prev["close"].iloc[0]

        # 简化ICIR模拟: 用近期趋势
        gap = (o / pc - 1) * 100
        scores[code] = gap * 0.3 + (c / o - 1) * 100 * 0.3 + np.log1p(v) * 0.1
        scores[code] = np.clip(scores[code], -5, 10)

        # GC池模拟: 放量+站上MA25附近
        if float(v) > 0 and float(o) > float(pc):
            gc_set.add(code)

    # 硬过滤: 只保留GC池里的
    filtered = {c: s for c, s in scores.items() if c in gc_set}
    if len(filtered) < TOP_N:
        filtered = dict(sorted(scores.items(), key=lambda x: -x[1])[:TOP_N * 2])

    return filtered


def compute_new_system_scores(df_day, df_prev, imap, fund_flow, date_str):
    """新系统: 软门控 + 竞价热点 + 管线溢价"""
    scores = defaultdict(float)
    sector_gaps = defaultdict(list)
    stock_signals = {}

    for _, row in df_day.iterrows():
        code = row["symbol"]
        o, c, v = row["open"], row["close"], row["volume"]
        prev = df_prev[df_prev["symbol"] == code]
        if len(prev) == 0:
            continue
        pc = prev["close"].iloc[0]

        gap = (o / pc - 1) * 100
        sector = get_sector(code, imap)
        sector_gaps[sector].append(gap)
        stock_signals[code] = {"gap": gap, "vol": v, "sector": sector}

    # 竞价热点计算
    sector_heat = {}
    for sec, gaps in sector_gaps.items():
        gap_mean = np.mean(gaps)
        pos_ratio = sum(1 for g in gaps if g > 0) / max(len(gaps), 1)
        sector_heat[sec] = gap_mean * 0.25 + pos_ratio * 0.20

    # 管线候选池: ML分最高的前50只
    pipeline_candidates = set()
    ml_scores = {}
    for code, sig in stock_signals.items():
        s = sig["gap"] * 0.4 + np.log1p(sig["vol"]) * 0.1
        ml_scores[code] = s
    pipeline_candidates = set(sorted(ml_scores, key=lambda x: -ml_scores[x])[:50])

    for code, sig in stock_signals.items():
        # ICIR分(50%)
        icir = sig["gap"] * 0.4 + np.log1p(sig["vol"]) * 0.1
        # 动量分(50%)
        momentum = sig["gap"] * 0.3 + 0.2

        # 基础分
        base = icir * 0.5 + momentum * 0.5

        # 竞价热点
        sector = sig["sector"]
        heat = sector_heat.get(sector, 0)
        if heat > 0.3:
            base *= 1.08
        elif heat < -0.2:
            base *= 0.85

        # 管线溢价
        if code in pipeline_candidates:
            base *= 1.08

        scores[code] = base

    return scores


def backtest_compare():
    log("加载数据...")
    df, imap, ff = load_data()
    dates = sorted(df["date"].unique())[-LOOKBACK - 5:]
    log(f"回测 {len(dates)} 天")

    old_daily, new_daily = [], []
    old_cum, new_cum = 1.0, 1.0

    for i in range(5, len(dates) - 1):
        date = dates[i]
        next_date = dates[i + 1]
        date_str = pd.Timestamp(date).strftime("%Y-%m-%d")

        df_day = df[df["date"] == date]
        df_prev = df[df["date"] == dates[i - 1]]
        df_next = df[df["date"] == next_date]

        if len(df_day) < 500 or len(df_next) < 500:
            continue

        # 旧系统
        old_scores = compute_old_system_scores(df_day, df_prev, imap)
        old_picks = sorted(old_scores, key=lambda x: -old_scores[x])[:TOP_N]

        # 新系统
        new_scores = compute_new_system_scores(df_day, df_prev, imap, ff, date_str)
        new_picks = sorted(new_scores, key=lambda x: -new_scores[x])[:TOP_N]

        # 计算收益
        old_ret, new_ret = [], []
        market_ret = []

        for picks, rets in [(old_picks, old_ret), (new_picks, new_ret)]:
            for code in picks:
                nr = df_next[df_next["symbol"] == code]
                if len(nr) == 0:
                    continue
                r = (nr["close"].iloc[0] / nr["open"].iloc[0] - 1) * 100
                rets.append(r)

        # 市场基准
        mr = (df_next["close"].mean() / df_next["open"].mean() - 1) * 100
        market_ret.append(mr)

        if old_ret and new_ret:
            old_avg = np.mean(old_ret)
            new_avg = np.mean(new_ret)
            old_daily.append(old_avg)
            new_daily.append(new_avg)
            old_cum *= (1 + old_avg / 100)
            new_cum *= (1 + new_avg / 100)

    # 汇总
    old_win = sum(1 for r in old_daily if r > 0) / max(len(old_daily), 1)
    new_win = sum(1 for r in new_daily if r > 0) / max(len(new_daily), 1)
    old_sharpe = (np.mean(old_daily) / np.std(old_daily) * np.sqrt(252)) if np.std(old_daily) > 0 else 0
    new_sharpe = (np.mean(new_daily) / np.std(new_daily) * np.sqrt(252)) if np.std(new_daily) > 0 else 0

    result = {
        "period": f"{dates[5].date()} ~ {dates[-2].date()}",
        "n_days": len(old_daily),
        "old_system": {
            "avg_return_pct": round(np.mean(old_daily), 2),
            "win_rate_pct": round(old_win * 100, 1),
            "cumulative_pct": round((old_cum - 1) * 100, 1),
            "sharpe": round(old_sharpe, 2),
        },
        "new_system": {
            "avg_return_pct": round(np.mean(new_daily), 2),
            "win_rate_pct": round(new_win * 100, 1),
            "cumulative_pct": round((new_cum - 1) * 100, 1),
            "sharpe": round(new_sharpe, 2),
        },
        "improvement": {
            "avg_return_delta": round(np.mean(new_daily) - np.mean(old_daily), 2),
            "win_rate_delta": round((new_win - old_win) * 100, 1),
            "cumulative_delta": round((new_cum - old_cum) * 100, 1),
            "sharpe_delta": round(new_sharpe - old_sharpe, 2),
        },
        "daily": [
            {"date": str(dates[i + 5]).split()[0],
             "old": round(old_daily[j], 2), "new": round(new_daily[j], 2)}
            for j in range(len(old_daily))
        ],
    }

    log("=" * 60)
    log(f"📊 新旧系统对比回测 ({result['n_days']}天)")
    log(f"  旧系统: 日均={result['old_system']['avg_return_pct']}% "
        f"胜率={result['old_system']['win_rate_pct']}% "
        f"累计={result['old_system']['cumulative_pct']}% "
        f"夏普={result['old_system']['sharpe']}")
    log(f"  新系统: 日均={result['new_system']['avg_return_pct']}% "
        f"胜率={result['new_system']['win_rate_pct']}% "
        f"累计={result['new_system']['cumulative_pct']}% "
        f"夏普={result['new_system']['sharpe']}")
    log(f"  提升:  日均+{result['improvement']['avg_return_delta']}% "
        f"胜率+{result['improvement']['win_rate_delta']}pp "
        f"累计+{result['improvement']['cumulative_delta']}pp "
        f"夏普+{result['improvement']['sharpe_delta']}")

    return result


if __name__ == "__main__":
    result = backtest_compare()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"\n输出: {OUTPUT}")
