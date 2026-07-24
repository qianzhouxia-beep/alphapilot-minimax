#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AlphaPilot V3 管线选股回测（以 VM2.5 为评分引擎）。

目标：不是只看模型 IC，而是模拟漏斗选出的股票在持有期内的胜率/收益。

漏斗（回测版，与生产对齐的可量化部分）:
  STEP1 量价金叉（as-of）
  STEP2 VM2.5 评分，取 TopK
  STEP3 资金门控：近5日主力净额合计 > 0（有资金流时）
  STEP4 LLM 默认跳过（生产阈值会空输出；可用 --with-llm-proxy 用分位代替）

指标:
  - 胜率 win_rate（持有 HOLD 日后收益>0）
  - 准确率 precision@3pct（持有期收益>=3%，对齐训练标签）
  - 平均收益 / 中位收益 / 最大回撤近似
"""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/ubuntu/alphapilot")
os.chdir(ROOT)

from vm25_scorer import VM25Scorer, _bare, _load_json


def volume_gc_asof(kl: pd.DataFrame, asof_idx: int) -> bool:
    if asof_idx < 60:
        return False
    sub = kl.iloc[: asof_idx + 1]
    c = sub["close"].astype(float).values
    vcol = "volume" if "volume" in sub.columns else "amount"
    v = sub[vcol].astype(float).values
    ma25 = pd.Series(c).rolling(25).mean().values
    vm5 = pd.Series(v).rolling(5).mean().values
    vm60 = pd.Series(v).rolling(60).mean().values
    l = len(c) - 1
    return bool(c[l] > ma25[l] and vm5[l] > vm60[l] and vm5[l - 1] <= vm60[l - 1])


def fund_gate_ok(fund_hist: dict, date: str, lookback: int = 5) -> bool:
    """弱硬底线：3日锋面+5日骨架皆非参与（双负且近5日零流入日）或5日深流出则挡。"""
    if not fund_hist:
        return True  # 无数据时不挡
    dates = sorted(d for d in fund_hist.keys() if d <= date)
    if not dates:
        return True
    use5 = dates[-lookback:]
    use3 = dates[-3:]
    if len(use5) < 3:
        return True
    nets5 = [float(fund_hist[d]) for d in use5]
    nets3 = [float(fund_hist[d]) for d in use3]
    s5 = sum(nets5)
    s3 = sum(nets3)
    pos5 = sum(1 for x in nets5 if x > 0)
    if s5 < -1e8:
        return False
    if s3 <= 0 and s5 <= 0 and pos5 == 0:
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-06-01")
    ap.add_argument("--end", default="2026-07-15")
    ap.add_argument("--hold", type=int, default=5)
    ap.add_argument("--top-k", type=int, default=20)
    ap.add_argument("--stride", type=int, default=1, help="交易日步长")
    ap.add_argument("--max-stocks", type=int, default=0, help="调试限股票数，0=全市场")
    ap.add_argument("--prefer", default="opt", choices=["opt", "base"])
    ap.add_argument("--skip-fund-gate", action="store_true")
    ap.add_argument("--llm-proxy_pct", type=float, default=0.0,
                    help="若>0，按当日分数分位保留 top pct（如0.5=前50%）模拟LLM宽松过滤")
    args = ap.parse_args()

    print("=== V3 管线选股回测（VM2.5）===")
    print(f"窗口 {args.start}~{args.end} hold={args.hold} top_k={args.top_k}")

    scorer = VM25Scorer(prefer=args.prefer)
    if not scorer.load():
        raise SystemExit(2)

    kpath = ROOT / "data" / "kline_cache" / "kline_all.parquet"
    if not kpath.exists():
        kpath = ROOT / "kline_all.parquet"
    kdf = pd.read_parquet(kpath)
    kdf["date"] = kdf["date"].astype(str).str[:10]
    kdf["symbol"] = kdf["symbol"].astype(str).map(_bare)

    symbols = sorted(kdf["symbol"].unique())
    if args.max_stocks:
        symbols = symbols[: args.max_stocks]
    print(f"股票池: {len(symbols)}")

    # 按股分组
    groups = {sym: g.sort_values("date").reset_index(drop=True)
              for sym, g in kdf[kdf["symbol"].isin(symbols)].groupby("symbol")}

    # 交易日
    sample = next(iter(groups.values()))
    trade_dates = sorted(d for d in sample["date"].unique() if args.start <= d <= args.end)
    trade_dates = trade_dates[:: max(args.stride, 1)]
    print(f"交易日: {len(trade_dates)}")

    trades = []
    t0 = time.time()

    for di, date in enumerate(trade_dates):
        day_cands = []
        for sym, g in groups.items():
            # asof index
            idxs = g.index[g["date"] <= date]
            if len(idxs) == 0:
                continue
            ai = int(idxs[-1])
            if g.loc[ai, "date"] != date:
                # 必须是当日有交易
                continue
            if not volume_gc_asof(g, ai):
                continue
            if not args.skip_fund_gate:
                if not fund_gate_ok(scorer.fund_flow.get(sym, {}), date, 5):
                    continue
            # 评分用 asof 历史
            sub = g.iloc[: ai + 1].copy()
            try:
                r = scorer.score(sub, sym)
            except Exception:
                continue
            if "error" in r:
                continue
            day_cands.append({
                "date": date,
                "symbol": sym,
                "score": float(r["score"]),
                "buy": float(r["buy_price"]),
                "ai": ai,
            })

        if not day_cands:
            print(f"  {date}: 候选0")
            continue

        day_cands.sort(key=lambda x: -x["score"])
        if args.llm_proxy_pct > 0:
            keep = max(1, int(len(day_cands) * args.llm_proxy_pct))
            day_cands = day_cands[:keep]

        picks = day_cands[: args.top_k]

        # 持有期收益
        for p in picks:
            g = groups[p["symbol"]]
            ai = p["ai"]
            hi = ai + args.hold
            if hi >= len(g):
                continue
            sell = float(g.loc[hi, "close"])
            ret = sell / p["buy"] - 1
            # 涨跌停异常过滤
            if abs(ret) > 0.45:
                continue
            trades.append({
                "date": p["date"],
                "symbol": p["symbol"],
                "score": p["score"],
                "ret": ret,
                "win": ret > 0,
                "hit_3pct": ret >= 0.03,
                "sell_date": str(g.loc[hi, "date"]),
            })

        wins = [t for t in trades if t["date"] == date and t["win"]]
        print(
            f"  {date}: GC+评分候选 {len(day_cands)} -> 选 {len(picks)} | "
            f"当日可结算胜率 {len(wins)}/{sum(1 for t in trades if t['date']==date)}",
            flush=True,
        )
        if (di + 1) % 5 == 0:
            print(f"  ... elapsed {int(time.time()-t0)}s cumulative trades={len(trades)}", flush=True)

    if not trades:
        print("无成交，退出")
        raise SystemExit(1)

    rets = np.array([t["ret"] for t in trades], dtype=float)
    report = {
        "model": "vm25",
        "pipeline": "V3_funnel_backtest",
        "start": args.start,
        "end": args.end,
        "hold": args.hold,
        "top_k": args.top_k,
        "n_trades": len(trades),
        "n_days": len({t["date"] for t in trades}),
        "win_rate": float((rets > 0).mean()),
        "precision_3pct": float((rets >= 0.03).mean()),
        "avg_return": float(rets.mean()),
        "median_return": float(np.median(rets)),
        "p25_return": float(np.percentile(rets, 25)),
        "p75_return": float(np.percentile(rets, 75)),
        "avg_score": float(np.mean([t["score"] for t in trades])),
        "skip_fund_gate": args.skip_fund_gate,
        "llm_proxy_pct": args.llm_proxy_pct,
        "note": "LLM skipped in backtest unless llm_proxy_pct>0; production LLM threshold still needs fix",
    }

    # 按日聚合
    by_day = defaultdict(list)
    for t in trades:
        by_day[t["date"]].append(t["ret"])
    day_rets = np.array([np.mean(v) for v in by_day.values()], dtype=float)
    report["day_avg_return"] = float(day_rets.mean())
    report["day_win_rate"] = float((day_rets > 0).mean())

    out = ROOT / "output" / "v3_pipeline_backtest.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"kpi": report, "trades": trades[:500]}, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n======== V3 管线回测结果 ========")
    print(f"成交次数: {report['n_trades']} | 覆盖交易日: {report['n_days']}")
    print(f"胜率(收益>0): {report['win_rate']*100:.1f}%")
    print(f"准确率(收益>=3%): {report['precision_3pct']*100:.1f}%")
    print(f"平均收益: {report['avg_return']*100:.2f}% | 中位: {report['median_return']*100:.2f}%")
    print(f"按日组合: 日胜率 {report['day_win_rate']*100:.1f}% | 日均收益 {report['day_avg_return']*100:.2f}%")
    print(f"已保存: {out}")


if __name__ == "__main__":
    main()