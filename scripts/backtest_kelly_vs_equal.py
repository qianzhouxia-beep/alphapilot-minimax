#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""等权 vs Kelly 仓位回测对比 — 基于现有 tradable 回测数据集。

用 v3_tradable_gated_sleeve_backtest.json 的 A0_baseline 交易，
替换原等权为 Kelly 权重，对比：
  - 每笔按 Kelly 调整 size
  - 等权基线直接取原始 ret

输出：
  output/reviews/kelly_vs_equal_backtest_YYYY-MM-DD.json

用法：
  python3 -u scripts/backtest_kelly_vs_equal.py
  KELLY_ENABLE=1 python3 -u scripts/backtest_kelly_vs_equal.py  # 生产环境变量
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path("/home/ubuntu/alphapilot")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parents[1]
    os.chdir(ROOT)

sys.path.insert(0, str(ROOT))

BACKTEST_PATH = (
    ROOT / "output/v3_tradable_gated_sleeve_backtest.json"
    or ROOT / "output/v3_tradable_gated_backtest.json"
)
KLINE_PATH = ROOT / "data/kline_cache/kline_all.parquet"
OUT_DIR = ROOT / "output/reviews"


def main() -> int:
    import pandas as pd

    # 1. 加载回测交易数据
    payload = json.loads(BACKTEST_PATH.read_text(encoding="utf-8"))
    trades_map = payload.get("trades", {})
    arm = "A0_baseline" if "A0_baseline" in trades_map else None
    if not arm:
        print("No A0_baseline found")
        return 1
    trades = [t for t in trades_map[arm] if not t.get("skipped")]
    print(f"Loaded {len(trades)} trades from {arm}")

    # 2. 加载日K波动率
    kdf = None
    if KLINE_PATH.exists():
        kdf = pd.read_parquet(KLINE_PATH, columns=["symbol", "date", "close"])
        from kelly_sizing import _norm_sym, _annual_vol

        kdf["_sym"] = kdf["symbol"].astype(str).map(_norm_sym)
        vol_map = {}
        for sym, grp in kdf.groupby("_sym"):
            vol_map[sym] = _annual_vol(grp["close"])
        vols = [v for v in vol_map.values() if v > 0]
        median_vol = float(np.median(vols)) if vols else 0.50
    else:
        vol_map = {}
        median_vol = 0.50

    # 3. 构建 score → 统计映射
    from kelly_sizing import calibrate_from_backtest, apply_kelly, KELLY_ENABLE, _lookup_bin

    hist = calibrate_from_backtest(str(BACKTEST_PATH), arm)
    print(f"Calibrated hist: n={hist.get('n_trades')}, win_rate={hist.get('overall_win_rate')}, payoff={hist.get('overall_payoff')}")

    # 4. 等权 vs Kelly 对比
    kelly_trades = []
    equal_trades = []

    # 按交易日分组（同一日多只需要一起算 Kelly 权重）
    from collections import defaultdict
    by_date: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        d = str(t.get("date") or t.get("buy_date") or "")
        by_date[d].append(t)

    for date, group in sorted(by_date.items()):
        # 等权
        eq_w = 1.0 / len(group)
        for t in group:
            ret = float(t.get("ret") or t.get("gross_ret") or 0)
            equal_trades.append({
                "date": date,
                "symbol": t.get("symbol"),
                "score": t.get("score"),
                "weight": eq_w,
                "ret": ret,
                "weighted_ret": ret * eq_w,
                "buy": t.get("buy"),
                "sell": t.get("sell"),
            })

        # Kelly
        candidates = []
        for t in group:
            sym = str(t.get("symbol", ""))
            raw_sym = "".join(c for c in sym if c.isdigit())[-6:].zfill(6)
            vol = vol_map.get(raw_sym, median_vol)
            sc = float(t.get("score") or 0)
            pct = 0.5  # 暂用组内排名代替
            candidates.append({
                "symbol": sym,
                "name": t.get("name", ""),
                "score": sc,
                "industry_l1": t.get("industry_l1", ""),
                "_vol": vol,
            })

        # 本组内 score 排名确定百分位
        scores = sorted([c["score"] for c in candidates], reverse=True)
        for c in candidates:
            pct = sum(1 for s in scores if s <= c["score"]) / max(len(scores), 1)
            p, b = _lookup_bin(pct, hist)
            q = 1.0 - p
            k_full = max(0.0, (p * b - q) / b) if b > 0 else 0.0
            kelly_frac = min(k_full * 0.5, 0.25)
            # vol adjust
            vf = min(median_vol / c["_vol"], 1.5) if c["_vol"] > 0 else 1.0
            c["_k"] = kelly_frac * vf

        total_k = sum(c["_k"] for c in candidates)
        if total_k > 0:
            for c, t in zip(candidates, group):
                w = c["_k"] / total_k
                ret = float(t.get("ret") or t.get("gross_ret") or 0)
                kelly_trades.append({
                    "date": date,
                    "symbol": t.get("symbol"),
                    "score": t.get("score"),
                    "weight": round(w, 4),
                    "ret": ret,
                    "weighted_ret": ret * w,
                    "kelly_frac": round(c["_k"], 4),
                    "vol_factor": round(min(median_vol / c["_vol"], 1.5), 3) if c["_vol"] > 0 else 1.0,
                })

    # 5. 统计
    def stats(arr: list[dict], label: str) -> dict:
        n = len(arr)
        wrets = [t["weighted_ret"] for t in arr]
        rets = [t["ret"] for t in arr]
        cum = np.cumsum(wrets)
        dd = 0.0
        peak = cum[0]
        for v in cum[1:]:
            if v > peak:
                peak = v
            dd = min(dd, v - peak)
        return {
            "arm": label,
            "n_trades": n,
            "total_return_pct": round(float(np.sum(wrets)) * 100, 2),
            "avg_return_pct": round(float(np.mean(rets)) * 100, 3),
            "median_return_pct": round(float(np.median(rets)) * 100, 3),
            "win_rate": round(float(np.mean([r > 0 for r in rets])) * 100, 1),
            "max_drawdown_pct": round(float(dd) * 100, 2),
            "avg_weight": round(float(np.mean([t["weight"] for t in arr])), 4),
            "std_weight": round(float(np.std([t["weight"] for t in arr])), 4),
        }

    eq_metrics = stats(equal_trades, "equal_weight")
    kl_metrics = stats(kelly_trades, "kelly_half")

    out = {
        "asof": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": str(BACKTEST_PATH.relative_to(ROOT)),
        "arm": arm,
        "config": {
            "KELLY_ENABLE": KELLY_ENABLE,
            "KELLY_FRAC": float(os.environ.get("KELLY_FRAC", "0.5")),
            "KELLY_MAX_POS": float(os.environ.get("KELLY_MAX_POS", "0.25")),
            "hist_n_trades": hist.get("n_trades"),
            "hist_overall_win_rate": hist.get("overall_win_rate"),
            "hist_overall_payoff": hist.get("overall_payoff"),
        },
        "equal_weight": eq_metrics,
        "kelly_half": kl_metrics,
        "delta": {
            "total_return_delta_pct": round(kl_metrics["total_return_pct"] - eq_metrics["total_return_pct"], 2),
            "win_rate_delta_pct": round(kl_metrics["win_rate"] - eq_metrics["win_rate"], 1),
            "max_drawdown_delta_pct": round(kl_metrics["max_drawdown_pct"] - eq_metrics["max_drawdown_pct"], 2),
            "avg_return_delta_pct": round(kl_metrics["avg_return_pct"] - eq_metrics["avg_return_pct"], 3),
        },
        "verdict": [],
    }
    out["verdict"].append(
        f"等权 vs Half-Kelly: 总收益 {eq_metrics['total_return_pct']}% → {kl_metrics['total_return_pct']}% "
        f"(Δ{out['delta']['total_return_delta_pct']:+.2f}%)"
    )
    out["verdict"].append(
        f"胜率 {eq_metrics['win_rate']}% → {kl_metrics['win_rate']}% "
        f"(Δ{out['delta']['win_rate_delta_pct']:+.1f}pp) "
        f"最大回撤 {eq_metrics['max_drawdown_pct']}% → {kl_metrics['max_drawdown_pct']}% "
        f"(Δ{out['delta']['max_drawdown_delta_pct']:+.2f}pp)"
    )
    out["verdict"].append(
        f"平均权重: 等权={eq_metrics['avg_weight']} std={eq_metrics['std_weight']} | "
        f"Kelly={kl_metrics['avg_weight']} std={kl_metrics['std_weight']}"
    )

    # 生产默认：等权（KELLY_ENABLE=0），Kelly 可用但供评估
    if KELLY_ENABLE:
        out["production_default"] = "KELLY_ENABLE=1"
        out["verdict"].append("当前生产已启用 Kelly 仓位分配")
    else:
        out["production_default"] = "KELLY_ENABLE=0（默认等权）"
        out["verdict"].append(
            "生产默认等权；KELLY_ENABLE=1 启用 Kelly + 风险预算（仅供评估，需观察）"
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    day = datetime.now().strftime("%Y-%m-%d")
    path = OUT_DIR / f"kelly_vs_equal_backtest_{day}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {path}")
    print(json.dumps({"equal_weight": eq_metrics, "kelly_half": kl_metrics, "delta": out["delta"], "verdict": out["verdict"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())