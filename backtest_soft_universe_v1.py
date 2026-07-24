#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""软宇宙简化模型 V1 回测（对照现行硬宇宙）。

设计（Cursor × WorkBuddy 合流）:
  主人要做减法：宽→严，分数说话，少硬踢。
  WorkBuddy 证据：生产 Top500 有 ~93% 死在启动|旁路硬门。

三臂（可交易协议一致）:
  HardUniverse   现行近似：量价金叉硬进 + 资金弱硬门 + VM TopN
  SoftUniverse   新模型：趋势宽入口 + 非金叉软降权 + 同资金硬底 + VM TopN
  PureScore      极端对照：宽入口不降权，纯 VM TopN（看金叉软权是否有用）

宽入口（Soft / Pure）廉价条件（不做启动硬删）:
  - 非近涨停
  - 资金弱硬门通过（与 Hard 相同）
  - 非下跌通道（MA 空头堆叠且价在 MA20 下）
  - 价 > MA20 或 金叉（保证最低趋势）
  - 每日最多 score_cap 只：全体金叉强制纳入 + 其余按 5 日动量补齐

协议: T 信号 → T+1 开买（开盘近涨停跳过）→ T+2 收卖 → 成本 15bp
"""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
if (ROOT / "alphapilot_pipeline_v3.py").exists():
    os.chdir(ROOT)
else:
    ROOT = Path("/home/ubuntu/alphapilot")
    os.chdir(ROOT)

from vm25_scorer import VM25Scorer, _bare
from backtest_v3_pipeline import volume_gc_asof, fund_gate_ok
from backtest_v3_tradable_gated import (
    day_chg,
    limit_pct,
    max_drawdown,
    near_limit,
    settle_tradable,
)


def ma(series: pd.Series, n: int) -> float:
    if len(series) < n:
        return float("nan")
    return float(series.tail(n).mean())


def is_downtrend_channel(g: pd.DataFrame, ai: int) -> bool:
    """与 trend_prefer 简化对齐：空头堆叠 + 价在 MA20 下。"""
    if ai < 60:
        return False
    sub = g.iloc[: ai + 1]
    c = sub["close"].astype(float)
    c0 = float(c.iloc[-1])
    ma5, ma20, ma60 = ma(c, 5), ma(c, 20), ma(c, 60)
    if any(np.isnan(x) for x in (ma5, ma20, ma60)):
        return False
    bear = (ma5 < ma20) and (ma20 < ma60) and (c0 < ma60)
    return bool(bear and c0 < ma20)


def above_ma20(g: pd.DataFrame, ai: int) -> bool:
    if ai < 20:
        return False
    c = g.iloc[: ai + 1]["close"].astype(float)
    return float(c.iloc[-1]) > ma(c, 20)


def ret_nd(g: pd.DataFrame, ai: int, n: int = 5) -> float:
    if ai < n:
        return -999.0
    c0 = float(g.loc[ai, "close"])
    c1 = float(g.loc[ai - n, "close"])
    if c1 <= 0:
        return -999.0
    return c0 / c1 - 1.0


def summarize(trades: list, name: str, thr: float, calendar_days: list[str]) -> dict:
    filled = [t for t in trades if not t.get("skipped")]
    skipped = [t for t in trades if t.get("skipped")]
    by = defaultdict(list)
    for t in filled:
        by[t["date"]].append(float(t["ret"]))
    day_rets = []
    for d in calendar_days:
        if d in by:
            day_rets.append(float(np.mean(by[d])))
        else:
            day_rets.append(0.0)
    day_arr = np.array(day_rets, dtype=float)
    rets = np.array([t["ret"] for t in filled], dtype=float) if filled else np.array([])
    return {
        "arm": name,
        "n_trades": len(filled),
        "n_skipped": len(skipped),
        "n_signal_days": len([d for d in calendar_days if d in by]),
        "win_rate": float((rets > 0).mean()) if len(rets) else None,
        "hit_3pct": float((rets >= thr).mean()) if len(rets) else None,
        "hit_5pct": float((rets >= 0.05).mean()) if len(rets) else None,
        "avg_ret": float(rets.mean()) if len(rets) else None,
        "median_ret": float(np.median(rets)) if len(rets) else None,
        "day_avg_ret": float(day_arr.mean()) if len(day_arr) else None,
        "day_win_rate": float((day_arr > 0).mean()) if len(day_arr) else None,
        "max_dd": max_drawdown(day_arr) if len(day_arr) else None,
        "avg_pool_scored": None,
        "avg_hard_pool": None,
    }


def main():
    ap = argparse.ArgumentParser(description="SoftUniverse V1 backtest")
    ap.add_argument("--start", default="2026-06-26")
    ap.add_argument("--end", default="2026-07-22")
    ap.add_argument("--top-n", type=int, default=2)
    ap.add_argument("--pool-n", type=int, default=50, help="展示池大小（诊断召回）")
    ap.add_argument("--score-cap", type=int, default=120, help="每日最多 VM 评分只数")
    ap.add_argument("--soft-mult", type=float, default=0.72, help="非金叉软降权")
    ap.add_argument("--workers", type=int, default=1, help="评分线程（VM 默认串行更稳）")
    ap.add_argument("--limit-frac", type=float, default=0.97)
    ap.add_argument("--cost-rt", type=float, default=0.0015)
    ap.add_argument("--threshold", type=float, default=0.03)
    ap.add_argument("--prefer", default="opt")
    ap.add_argument("--surge-thr", type=float, default=0.05, help="次日大涨阈值（收盘）诊断")
    args = ap.parse_args()

    print("=== SoftUniverse V1 回测 ===", flush=True)
    print(
        f"window {args.start}~{args.end} top_n={args.top_n} pool_n={args.pool_n} "
        f"score_cap={args.score_cap} soft_mult={args.soft_mult}",
        flush=True,
    )

    scorer = VM25Scorer(prefer=args.prefer)
    if not scorer.load():
        raise SystemExit("VM25 load failed")

    kpath = ROOT / "data/kline_cache/kline_all.parquet"
    if not kpath.exists():
        kpath = ROOT / "kline_all.parquet"
    kdf = pd.read_parquet(kpath)
    kdf["date"] = kdf["date"].astype(str).str[:10]
    kdf["symbol"] = kdf["symbol"].astype(str).map(_bare)
    kdf = kdf[~kdf["symbol"].str.startswith(("8", "4", "bj"))]
    groups = {s: g.sort_values("date").reset_index(drop=True) for s, g in kdf.groupby("symbol")}

    cal_sym = "600519" if "600519" in groups else next(iter(groups))
    dates = sorted(d for d in groups[cal_sym]["date"].unique() if args.start <= d <= args.end)
    # 需要 T+2 结算：丢掉末两日无 K 的信号日已在 settle 里 skip
    print(f"stocks={len(groups)} days={len(dates)} calendar={cal_sym}", flush=True)

    arms = {"HardUniverse": [], "SoftUniverse": [], "PureScore": []}
    day_meta = []
    t0 = time.time()

    for di, date in enumerate(dates):
        cheap = []  # 宽池候选
        for sym, g in groups.items():
            idxs = g.index[g["date"] <= date]
            if len(idxs) == 0:
                continue
            ai = int(idxs[-1])
            if str(g.loc[ai, "date"]) != date:
                continue
            if ai + 2 >= len(g):
                continue
            lim = limit_pct(sym)
            chg = day_chg(g, ai)
            if near_limit(chg, lim, args.limit_frac):
                continue
            fh = scorer.fund_flow.get(sym, {})
            if not fund_gate_ok(fh, date, 5):
                continue
            if is_downtrend_channel(g, ai):
                continue
            gc = volume_gc_asof(g, ai)
            trend_ok = above_ma20(g, ai) or gc
            if not trend_ok:
                continue
            cheap.append(
                {
                    "symbol": sym,
                    "ai": ai,
                    "gc": gc,
                    "mom5": ret_nd(g, ai, 5),
                    "signal_chg": chg,
                }
            )

        gc_list = [x for x in cheap if x["gc"]]
        non_gc = [x for x in cheap if not x["gc"]]
        non_gc.sort(key=lambda x: -x["mom5"])
        # 给非金叉预留名额，避免金叉占满 score_cap 后 Soft 臂名存实亡
        reserve = max(20, int(args.score_cap * 0.35))
        gc_budget = max(10, args.score_cap - reserve)
        gc_take = gc_list[:gc_budget] if len(gc_list) > gc_budget else gc_list
        remain = max(0, args.score_cap - len(gc_take))
        wide = gc_take + non_gc[:remain]

        def _score_one(x):
            sym, ai = x["symbol"], x["ai"]
            g = groups[sym]
            sub = g.iloc[: ai + 1].copy()
            try:
                r = scorer.score(sub, sym)
            except Exception:
                return None
            if "error" in r:
                return None
            raw = float(r["score"])
            return {
                **x,
                "score_raw": raw,
                "score_soft": raw * (1.0 if x["gc"] else args.soft_mult),
            }

        scored = []
        # VM25Scorer 默认串行；workers>1 仅作实验（非线程安全风险）
        if args.workers <= 1:
            for si, x in enumerate(wide, 1):
                row = _score_one(x)
                if row is not None:
                    scored.append(row)
                if si % 40 == 0:
                    print(f"    score {si}/{len(wide)}", flush=True)
        else:
            with ThreadPoolExecutor(max_workers=args.workers) as ex:
                futs = [ex.submit(_score_one, x) for x in wide]
                for fut in as_completed(futs):
                    row = fut.result()
                    if row is not None:
                        scored.append(row)

        hard_pool = [x for x in scored if x["gc"]]
        soft_ranked = sorted(scored, key=lambda x: -x["score_soft"])
        pure_ranked = sorted(scored, key=lambda x: -x["score_raw"])
        hard_ranked = sorted(hard_pool, key=lambda x: -x["score_raw"])

        def push(ranked, arm: str, score_key: str):
            picks = ranked[: args.top_n]
            for p in picks:
                g = groups[p["symbol"]]
                st = settle_tradable(g, p["ai"], args.cost_rt)
                base = {
                    "date": date,
                    "symbol": p["symbol"],
                    "score": p.get(score_key),
                    "score_raw": p.get("score_raw"),
                    "gc": p.get("gc"),
                    "signal_chg": p.get("signal_chg"),
                }
                if st is None:
                    arms[arm].append({**base, "skipped": True, "skip_reason": "no_bar"})
                    continue
                if st.get("skip"):
                    arms[arm].append(
                        {
                            **base,
                            "skipped": True,
                            "skip_reason": st["skip"],
                            "buy_date": st.get("buy_date"),
                        }
                    )
                    continue
                ret = float(st["ret"])
                arms[arm].append(
                    {
                        **base,
                        "skipped": False,
                        "ret": ret,
                        "gross_ret": st["gross_ret"],
                        "buy": st["buy"],
                        "sell": st["sell"],
                        "buy_date": st["buy_date"],
                        "sell_date": st["sell_date"],
                        "win": ret > 0,
                        "hit_3pct": ret >= args.threshold,
                        "hit_5pct": ret >= 0.05,
                        "open_gap": st["open_gap"],
                    }
                )

        push(hard_ranked, "HardUniverse", "score_raw")
        push(soft_ranked, "SoftUniverse", "score_soft")
        push(pure_ranked, "PureScore", "score_raw")

        # 次日收盘大涨召回（池 Top pool_n）诊断
        surge = set()
        for sym, g in groups.items():
            idxs = g.index[g["date"] == date]
            if len(idxs) == 0:
                continue
            ai = int(idxs[-1])
            if ai + 1 >= len(g):
                continue
            c0 = float(g.loc[ai, "close"])
            c1 = float(g.loc[ai + 1, "close"])
            if c0 > 0 and (c1 / c0 - 1.0) >= args.surge_thr:
                surge.add(sym)

        def recall(ranked):
            pool = {x["symbol"] for x in ranked[: args.pool_n]}
            if not surge:
                return None
            hit = len(pool & surge)
            return {"surge_n": len(surge), "pool_hit": hit, "recall": hit / len(surge)}

        day_meta.append(
            {
                "date": date,
                "cheap_n": len(cheap),
                "gc_n": len(gc_list),
                "scored_n": len(scored),
                "hard_pool_n": len(hard_pool),
                "recall_hard": recall(hard_ranked),
                "recall_soft": recall(soft_ranked),
                "recall_pure": recall(pure_ranked),
            }
        )
        print(
            f"  {date}: cheap={len(cheap)} gc={len(gc_list)} scored={len(scored)} "
            f"hard_pool={len(hard_pool)} ({di+1}/{len(dates)})",
            flush=True,
        )

    summaries = {
        k: summarize(v, k, args.threshold, dates) for k, v in arms.items()
    }
    # 填充日均池规模
    if day_meta:
        summaries["HardUniverse"]["avg_hard_pool"] = float(
            np.mean([d["hard_pool_n"] for d in day_meta])
        )
        summaries["SoftUniverse"]["avg_pool_scored"] = float(
            np.mean([d["scored_n"] for d in day_meta])
        )
        summaries["PureScore"]["avg_pool_scored"] = summaries["SoftUniverse"]["avg_pool_scored"]

        def avg_recall(key):
            vals = [
                d[key]["recall"]
                for d in day_meta
                if d.get(key) and d[key].get("recall") is not None
            ]
            return float(np.mean(vals)) if vals else None

        for arm, rk in (
            ("HardUniverse", "recall_hard"),
            ("SoftUniverse", "recall_soft"),
            ("PureScore", "recall_pure"),
        ):
            summaries[arm]["pool_recall_next_day_ge5pct"] = avg_recall(rk)

    out = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "model": "SoftUniverse_V1",
        "window": {"start": args.start, "end": args.end},
        "protocol": {
            "buy": "T+1 open skip if open near limit",
            "sell": "T+2 close",
            "cost_rt": args.cost_rt,
            "top_n": args.top_n,
            "pool_n": args.pool_n,
            "soft_mult": args.soft_mult,
            "score_cap": args.score_cap,
        },
        "design": {
            "HardUniverse": "volume_gc hard + fund weak-hard + VM TopN",
            "SoftUniverse": "wide trend entry + non-gc * soft_mult + fund weak-hard + VM TopN",
            "PureScore": "wide trend entry + raw VM TopN (no gc demote)",
            "hard_rejects": ["near_limit", "fund_weak_hard", "downtrend_channel"],
        },
        "summaries": summaries,
        "day_meta": day_meta,
        "elapsed_sec": int(time.time() - t0),
        "trades_sample": {
            k: [t for t in v if not t.get("skipped")][:20] for k, v in arms.items()
        },
    }

    out_path = ROOT / "output" / "soft_universe_v1_backtest.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # 完整 trades 另存，主文件保持可读
    full_trades_path = ROOT / "output" / "soft_universe_v1_trades.json"
    full_trades_path.write_text(
        json.dumps({k: v for k, v in arms.items()}, ensure_ascii=False),
        encoding="utf-8",
    )
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== RESULTS ===", flush=True)
    for name, s in summaries.items():
        print(
            f"{name}: trades={s['n_trades']} win={s['win_rate']} "
            f"hit3={s['hit_3pct']} hit5={s['hit_5pct']} avg={s['avg_ret']} "
            f"day_avg={s['day_avg_ret']} maxDD={s['max_dd']} "
            f"pool_recall@5%={s.get('pool_recall_next_day_ge5pct')}",
            flush=True,
        )
    print(f"saved {out_path} ({out['elapsed_sec']}s)", flush=True)


if __name__ == "__main__":
    main()
