#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""可交易口径 Top3 回测（真实可执行）。

协议（A 股可成交）:
  信号日 T 收盘后：严格量价金叉 + VM2.5 打分（仅 as-of）
  买入日 T+1 开盘：若开盘涨停 / 一字板 → 不成交
  卖出日 T+2 收盘：T+1 买入后最早可卖日（A 股 T+1）
  成功：净收益 >= 3%（扣成本后）
  过滤：信号日已近涨停不可买；|单笔净收益| 异常过大剔除结算但不参与选股

对比臂（均走同一成交规则）:
  A hard_strictGC_fund     — 生产对齐：严格金叉 + 资金硬门控 + score Top3
  B soft_strictGC_fundboost — 严格金叉 + 资金软加权 + score_soft Top3
  C soft_relaxedGC_fundboost — 仅作对照，不作为上线推荐

用法:
  python3 backtest_v3_tradable_top3.py --start 2026-04-01 --end 2026-07-10
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

from vm25_scorer import VM25Scorer, _bare
from backtest_v3_pipeline import volume_gc_asof, fund_gate_ok


def limit_pct(symbol: str) -> float:
    s = _bare(symbol)
    if s.startswith(("300", "301", "688")):
        return 0.20
    if s.startswith(("8", "4")):  # 北交所常见
        return 0.30
    return 0.10


def relaxed_gc(kl: pd.DataFrame, ai: int) -> bool:
    if ai < 60:
        return False
    sub = kl.iloc[: ai + 1]
    c = sub["close"].astype(float).values
    vcol = "volume" if "volume" in sub.columns else "amount"
    v = sub[vcol].astype(float).values
    ma25 = pd.Series(c).rolling(25).mean().values[-1]
    vm5 = pd.Series(v).rolling(5).mean().values[-1]
    vm60 = pd.Series(v).rolling(60).mean().values[-1]
    return bool(c[-1] > ma25 and vm5 > vm60)


def fund_soft_bonus(fund_hist: dict, date: str, lookback: int = 5) -> float:
    if not fund_hist:
        return 0.0
    dates = [d for d in sorted(fund_hist.keys()) if d <= date]
    if not dates:
        return 0.0
    use = dates[-lookback:]
    s = float(sum(float(fund_hist[d]) for d in use))
    return float(0.05 * np.tanh(s / 5e8))


def day_chg(g: pd.DataFrame, ai: int) -> float | None:
    if ai < 1:
        return None
    prev = float(g.loc[ai - 1, "close"])
    cur = float(g.loc[ai, "close"])
    if prev <= 0:
        return None
    return cur / prev - 1


def near_limit(chg: float | None, lim: float, frac: float = 0.97) -> bool:
    if chg is None:
        return False
    return chg >= lim * frac


def settle_tradable(g: pd.DataFrame, signal_ai: int, cost_rt: float):
    """信号日 signal_ai → 买 signal_ai+1 开盘 → 卖 signal_ai+2 收盘。"""
    bi = signal_ai + 1
    si = signal_ai + 2
    if si >= len(g):
        return None
    sym = str(g.loc[signal_ai, "symbol"]) if "symbol" in g.columns else ""
    lim = limit_pct(sym)

    buy_open = float(g.loc[bi, "open"])
    prev_close = float(g.loc[signal_ai, "close"])
    if prev_close <= 0 or buy_open <= 0:
        return None
    open_gap = buy_open / prev_close - 1
    # 开盘涨停/一字：无法买入
    if open_gap >= lim * 0.97:
        return {"skip": "open_limit", "buy_date": str(g.loc[bi, "date"])}

    sell_close = float(g.loc[si, "close"])
    gross = sell_close / buy_open - 1
    net = gross - cost_rt
    return {
        "skip": None,
        "buy_date": str(g.loc[bi, "date"]),
        "sell_date": str(g.loc[si, "date"]),
        "buy": buy_open,
        "sell": sell_close,
        "gross_ret": gross,
        "ret": net,
        "open_gap": open_gap,
    }


def max_drawdown(day_rets: np.ndarray) -> float:
    if len(day_rets) == 0:
        return 0.0
    eq = np.cumprod(1.0 + day_rets)
    peak = np.maximum.accumulate(eq)
    dd = eq / peak - 1.0
    return float(dd.min())


def summarize(trades: list, name: str, thr: float) -> dict:
    filled = [t for t in trades if not t.get("skipped")]
    skipped = [t for t in trades if t.get("skipped")]
    if not filled:
        return {
            "arm": name,
            "n_signals": len(trades),
            "n_filled": 0,
            "n_skipped": len(skipped),
            "fill_rate": 0.0,
        }
    rets = np.array([t["ret"] for t in filled], float)
    by = defaultdict(list)
    for t in filled:
        by[t["date"]].append(t["ret"])
    days = sorted(by)
    day = np.array([np.mean(by[d]) for d in days], float)
    return {
        "arm": name,
        "n_signals": len(trades),
        "n_filled": len(filled),
        "n_skipped": len(skipped),
        "fill_rate": float(len(filled) / max(len(trades), 1)),
        "n_days": len(days),
        "win_rate": float((rets > 0).mean()),
        "hit_3pct_rate": float((rets >= thr).mean()),
        "avg_return": float(rets.mean()),
        "median_return": float(np.median(rets)),
        "day_win_rate": float((day > 0).mean()),
        "day_avg_return": float(day.mean()),
        "max_drawdown": max_drawdown(day),
        "total_return": float(np.prod(1.0 + day) - 1.0),
        "skip_reasons": {
            k: int(sum(1 for t in skipped if t.get("skip_reason") == k))
            for k in sorted({t.get("skip_reason") for t in skipped if t.get("skip_reason")})
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-04-01")
    ap.add_argument("--end", default="2026-07-10")
    ap.add_argument("--top-n", type=int, default=2)
    ap.add_argument("--threshold", type=float, default=0.03)
    ap.add_argument("--cost-rt", type=float, default=0.0015, help="双边总成本（默认 15bp）")
    ap.add_argument("--prefer", default="opt")
    ap.add_argument("--limit-frac", type=float, default=0.97, help="信号日涨幅>=limit*frac 视为不可买")
    ap.add_argument(
        "--with-relaxed-ctrl",
        action="store_true",
        help="附加宽松金叉对照臂 C（很慢，默认关闭；C 已证明涨停依赖强）",
    )
    args = ap.parse_args()

    print("=== 可交易 Top3 回测 ===")
    print(
        f"{args.start}~{args.end} top_n={args.top_n} thr={args.threshold} "
        f"cost_rt={args.cost_rt} | buy=T+1 open sell=T+2 close"
    )

    scorer = VM25Scorer(prefer=args.prefer)
    assert scorer.load()

    kpath = ROOT / "data/kline_cache/kline_all.parquet"
    if not kpath.exists():
        kpath = ROOT / "kline_all.parquet"
    kdf = pd.read_parquet(kpath)
    kdf["date"] = kdf["date"].astype(str).str[:10]
    kdf["symbol"] = kdf["symbol"].astype(str).map(_bare)
    # 排除北交所（生产也排除）
    kdf = kdf[~kdf["symbol"].str.startswith(("8", "4"))]
    groups = {s: g.sort_values("date").reset_index(drop=True) for s, g in kdf.groupby("symbol")}

    # 用沪市大票对齐交易日
    cal_sym = "600519" if "600519" in groups else next(iter(groups))
    dates = sorted(d for d in groups[cal_sym]["date"].unique() if args.start <= d <= args.end)
    print(f"stocks={len(groups)} signal_days={len(dates)} calendar={cal_sym}")

    arms = {
        "A_hard_strictGC_fund": [],
        "B_soft_strictGC_fundboost": [],
    }
    if args.with_relaxed_ctrl:
        arms["C_soft_relaxedGC_fundboost_CTRL"] = []
    t0 = time.time()

    for di, date in enumerate(dates):
        strict_pool, relax_pool = [], []
        for sym, g in groups.items():
            idxs = g.index[g["date"] <= date]
            if len(idxs) == 0:
                continue
            ai = int(idxs[-1])
            if str(g.loc[ai, "date"]) != date:
                continue
            # 需要至少 T+2 有数据才可能成交；但不把未来收益拿来筛候选
            if ai + 2 >= len(g):
                continue

            lim = limit_pct(sym)
            chg = day_chg(g, ai)
            if near_limit(chg, lim, args.limit_frac):
                continue  # 信号日已涨停附近：收盘买不到，也不进池

            is_strict = volume_gc_asof(g, ai)
            is_relax = relaxed_gc(g, ai) if args.with_relaxed_ctrl else False
            if not is_strict and not is_relax:
                continue

            sub = g.iloc[: ai + 1].copy()
            try:
                r = scorer.score(sub, sym)
            except Exception:
                continue
            if "error" in r:
                continue

            base = float(r["score"])
            fh = scorer.fund_flow.get(sym, {})
            bonus = fund_soft_bonus(fh, date)
            row = {
                "symbol": sym,
                "ai": ai,
                "score": base,
                "score_soft": base + bonus,
                "fund_ok": fund_gate_ok(fh, date, 5),
                "signal_chg": chg,
            }
            if is_strict:
                strict_pool.append(row)
            if is_relax:
                relax_pool.append(row)

        def push(cands, key, arm, hard_fund: bool):
            pool = [x for x in cands if (x["fund_ok"] if hard_fund else True)]
            picks = sorted(pool, key=lambda x: -x[key])[: args.top_n]
            for p in picks:
                g = groups[p["symbol"]]
                st = settle_tradable(g, p["ai"], args.cost_rt)
                if st is None:
                    arms[arm].append(
                        {
                            "date": date,
                            "symbol": p["symbol"],
                            "skipped": True,
                            "skip_reason": "no_bar",
                            "score": p["score"],
                            "score_used": p[key],
                        }
                    )
                    continue
                if st.get("skip"):
                    arms[arm].append(
                        {
                            "date": date,
                            "symbol": p["symbol"],
                            "skipped": True,
                            "skip_reason": st["skip"],
                            "buy_date": st.get("buy_date"),
                            "score": p["score"],
                            "score_used": p[key],
                        }
                    )
                    continue
                arms[arm].append(
                    {
                        "date": date,
                        "symbol": p["symbol"],
                        "skipped": False,
                        "ret": st["ret"],
                        "gross_ret": st["gross_ret"],
                        "buy": st["buy"],
                        "sell": st["sell"],
                        "buy_date": st["buy_date"],
                        "sell_date": st["sell_date"],
                        "score": p["score"],
                        "score_used": p[key],
                        "win": st["ret"] > 0,
                        "hit_3pct": st["ret"] >= args.threshold,
                        "signal_chg": p["signal_chg"],
                        "open_gap": st["open_gap"],
                    }
                )
            return len(pool), len(picks)

        p1, n1 = push(strict_pool, "score", "A_hard_strictGC_fund", hard_fund=True)
        p2, n2 = push(strict_pool, "score_soft", "B_soft_strictGC_fundboost", hard_fund=False)
        msg = f"  {date}: strict={len(strict_pool)} A={p1}->{n1} B={p2}->{n2}"
        if args.with_relaxed_ctrl:
            p3, n3 = push(relax_pool, "score_soft", "C_soft_relaxedGC_fundboost_CTRL", hard_fund=False)
            msg += f" relax={len(relax_pool)} C={p3}->{n3}"
        print(msg, flush=True)
        if (di + 1) % 5 == 0:
            print(f"  ... {int(time.time() - t0)}s", flush=True)

    kpis = [summarize(arms[k], k, args.threshold) for k in arms]
    out = {
        "protocol": {
            "signal": "T close as-of",
            "entry": "T+1 open if not limit-up",
            "exit": "T+2 close (A-share T+1)",
            "success": f"net_return >= {args.threshold}",
            "cost_rt": args.cost_rt,
            "exclude_signal_near_limit": True,
            "gc_production": "strict cross (A/B); relaxed only control (C)",
            "note": "VM2.5 trained_at 2026-07-18; window may overlap train data — treat as in-sample risk",
        },
        "config": {
            "start": args.start,
            "end": args.end,
            "top_n": args.top_n,
            "threshold": args.threshold,
            "prefer": args.prefer,
        },
        "kpi": kpis,
        "trades": {k: arms[k] for k in arms},
        "recommendation": {
            "production_arm": "A_hard_strictGC_fund",
            "optional_ab": "B_soft_strictGC_fundboost",
            "do_not_ship": "C_soft_relaxedGC_fundboost_CTRL",
            "reason": "C edge historically dominated by limit-up continuation; not tradable",
        },
    }
    path = ROOT / "output/v3_tradable_top3_backtest.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n======== 可交易 Top3 结果 ========")
    for k in kpis:
        if k.get("n_filled", 0) == 0:
            print(f"{k['arm']}: 无成交 fill={k.get('fill_rate', 0):.0%} skip={k.get('n_skipped', 0)}")
            continue
        print(
            f"{k['arm']}: filled={k['n_filled']}/{k['n_signals']} "
            f"fill={k['fill_rate']*100:.0f}% days={k['n_days']} "
            f"win={k['win_rate']*100:.1f}% hit3%={k['hit_3pct_rate']*100:.1f}% "
            f"avg={k['avg_return']*100:.2f}% day_win={k['day_win_rate']*100:.1f}% "
            f"maxDD={k['max_drawdown']*100:.1f}% total={k['total_return']*100:.1f}%"
        )
        if k.get("skip_reasons"):
            print(f"  skips: {k['skip_reasons']}")
    print("saved", path)
    print("RECOMMEND:", out["recommendation"]["production_arm"])


if __name__ == "__main__":
    main()
