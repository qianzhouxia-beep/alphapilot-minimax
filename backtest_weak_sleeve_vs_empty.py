#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""弱势袖套 vs 空仓 对照回测（可交易协议）。

仅在 market_severe / position_exposure=0 的信号日上比较：
  E0  empty：当日收益 0（主臂空仓）
  S1  fund_sleeve：3/5/10 日资金轮动袖套，Top1，收益 × sleeve_expo（默认 0.25）

协议同主臂：T+1 开盘买（涨停跳过）→ T+2 收盘卖 → 成本 15bp → hit≥3%。

用法:
  python3 backtest_weak_sleeve_vs_empty.py --start 2026-05-01 --end 2026-07-17
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/ubuntu/alphapilot")
os.chdir(ROOT)

from market_env_gate import build_env_asof, fetch_all_index_klines, position_exposure
from vm25_scorer import _bare
from backtest_v3_tradable_gated import settle_tradable
from weak_fund_sleeve import SLEEVE_EXPO, scan_weak_fund_sleeve


def max_dd(day_rets: np.ndarray) -> float:
    if len(day_rets) == 0:
        return 0.0
    eq = np.cumprod(1.0 + day_rets)
    peak = np.maximum.accumulate(eq)
    dd = (peak - eq) / np.maximum(peak, 1e-12)
    return float(dd.max())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-05-01")
    ap.add_argument("--end", default="2026-07-17")
    ap.add_argument("--top-n", type=int, default=1)
    ap.add_argument("--sleeve-expo", type=float, default=SLEEVE_EXPO)
    ap.add_argument("--threshold", type=float, default=0.03)
    ap.add_argument("--cost-rt", type=float, default=0.0015)
    ap.add_argument(
        "--universe",
        choices=("severe", "market_weak", "both"),
        default="severe",
        help="severe=主臂空仓日; market_weak=双市走弱日(探索); both=并集",
    )
    args = ap.parse_args()

    print("=== 弱势袖套 vs 空仓 ===")
    print(
        f"{args.start}~{args.end} top_n={args.top_n} sleeve_expo={args.sleeve_expo} "
        f"universe={args.universe}"
    )

    kpath = ROOT / "data/kline_cache/kline_all.parquet"
    if not kpath.exists():
        kpath = ROOT / "kline_all.parquet"
    kdf = pd.read_parquet(kpath)
    kdf["date"] = kdf["date"].astype(str).str[:10]
    kdf["symbol"] = kdf["symbol"].astype(str).map(_bare)
    kdf = kdf[~kdf["symbol"].str.startswith(("8", "4"))]
    groups = {s: g.sort_values("date").reset_index(drop=True) for s, g in kdf.groupby("symbol")}
    cal_sym = "600519" if "600519" in groups else next(iter(groups))
    dates = sorted(d for d in groups[cal_sym]["date"].unique() if args.start <= d <= args.end)

    print("fetch index history...", flush=True)
    # Need enough bars for asof backtests (severe windows use 10d lookback)
    index_hist = fetch_all_index_klines(lmt=500)

    severe_days = []
    empty_day = {}
    sleeve_day = {}
    sleeve_trades = []
    day_meta = []
    t0 = time.time()

    for di, date in enumerate(dates):
        env = build_env_asof(index_hist, date)
        expo = float(env.get("position_exposure", position_exposure(env.get("flags"))))
        flags = env.get("flags") or {}
        is_severe = expo <= 0 or bool(flags.get("market_severe"))
        is_weak = bool(flags.get("market_weak"))
        if args.universe == "severe" and not is_severe:
            continue
        if args.universe == "market_weak" and not is_weak:
            continue
        if args.universe == "both" and not (is_severe or is_weak):
            continue
        severe_days.append(date)
        empty_day[date] = 0.0

        scan = scan_weak_fund_sleeve(date, kdf=kdf, top_n=args.top_n, expo=args.sleeve_expo)
        picked = scan.get("picked") or []
        day_rets = []
        n_fill = 0
        for p in picked:
            sym = _bare(p["symbol"])
            g = groups.get(sym)
            if g is None:
                continue
            idxs = g.index[g["date"] == date]
            if len(idxs) == 0:
                continue
            ai = int(idxs[0])
            st = settle_tradable(g, ai, args.cost_rt)
            if st is None:
                sleeve_trades.append(
                    {"date": date, "symbol": sym, "skipped": True, "skip_reason": "no_bar"}
                )
                continue
            if st.get("skip"):
                sleeve_trades.append(
                    {
                        "date": date,
                        "symbol": sym,
                        "skipped": True,
                        "skip_reason": st["skip"],
                        "industry_l1": p.get("industry_l1"),
                    }
                )
                continue
            raw = float(st["ret"])
            scaled = raw * args.sleeve_expo
            day_rets.append(scaled)
            n_fill += 1
            sleeve_trades.append(
                {
                    "date": date,
                    "symbol": sym,
                    "skipped": False,
                    "ret_raw": raw,
                    "ret": scaled,
                    "exposure": args.sleeve_expo,
                    "win": scaled > 0,
                    "hit_3pct": scaled >= args.threshold,
                    "industry_l1": p.get("industry_l1"),
                    "score": p.get("score"),
                    "fund_5d_sum": p.get("fund_5d_sum"),
                    "allow_top": [x["industry"] for x in (scan.get("allow_industries") or [])[:5]],
                    "buy_date": st.get("buy_date"),
                    "sell_date": st.get("sell_date"),
                }
            )
        sleeve_day[date] = float(np.mean(day_rets)) if day_rets else 0.0
        day_meta.append(
            {
                "date": date,
                "main_expo": expo,
                "flags": flags,
                "n_picked": len(picked),
                "n_filled": n_fill,
                "sleeve_day_ret": sleeve_day[date],
                "allow": [x["industry"] for x in (scan.get("allow_industries") or [])[:8]],
                "skip": scan.get("skip_reason"),
            }
        )
        print(
            f"  {date}: sleeve_fill={n_fill}/{len(picked)} day_ret={sleeve_day[date]*100:.2f}% "
            f"allow={day_meta[-1]['allow'][:4]}",
            flush=True,
        )
        if (di + 1) % 10 == 0:
            print(f"  ... {int(time.time()-t0)}s", flush=True)

    # KPI on severe days only
    e_arr = np.array([empty_day[d] for d in severe_days], float)
    s_arr = np.array([sleeve_day[d] for d in severe_days], float)
    filled = [t for t in sleeve_trades if not t.get("skipped")]

    def arm_kpi(name, day_arr, trades_filled):
        if len(day_arr) == 0:
            return {"arm": name, "n_severe_days": 0}
        rets = np.array([t["ret"] for t in trades_filled], float) if trades_filled else np.array([])
        return {
            "arm": name,
            "n_severe_days": len(day_arr),
            "n_filled_trades": int(len(trades_filled)),
            "fill_days": int(sum(1 for x in day_arr if abs(x) > 1e-12)),
            "day_avg_return": float(day_arr.mean()),
            "total_return": float(np.prod(1.0 + day_arr) - 1.0),
            "max_drawdown": max_dd(day_arr),
            "win_rate": float((rets > 0).mean()) if len(rets) else None,
            "hit_3pct_rate": float((rets >= args.threshold).mean()) if len(rets) else None,
            "avg_trade_return": float(rets.mean()) if len(rets) else None,
        }

    k_empty = arm_kpi("E0_empty", e_arr, [])
    k_sleeve = arm_kpi("S1_fund_sleeve", s_arr, filled)
    # delta
    delta = {
        "total_return_pp": (k_sleeve["total_return"] - k_empty["total_return"]) * 100,
        "maxDD_pp": (k_sleeve["max_drawdown"] - k_empty["max_drawdown"]) * 100,
        "day_avg_pp": (k_sleeve["day_avg_return"] - k_empty["day_avg_return"]) * 100,
    }

    out = {
        "protocol": {
            "entry": "T+1 open skip limit",
            "exit": "T+2 close",
            "cost_rt": args.cost_rt,
            "sleeve_expo": args.sleeve_expo,
            "universe": args.universe,
            "fund_windows": "3d tip / 5d spine / 10d anti-fake",
            "note": "severe=主臂空仓对照; market_weak=探索样本量(主臂仍可能半仓)",
        },
        "config": {
            "start": args.start,
            "end": args.end,
            "top_n": args.top_n,
            "threshold": args.threshold,
            "universe": args.universe,
        },
        "kpi": [k_empty, k_sleeve],
        "delta_sleeve_minus_empty": delta,
        "severe_days": severe_days,
        "day_meta": day_meta,
        "trades": sleeve_trades,
        "recommendation": {
            "use_sleeve_if": "total_return improves AND maxDD increase acceptable",
            "main_arm": "unchanged — still empty on severe",
            "sleeve": "optional satellite capital only",
        },
    }
    path = ROOT / "output/weak_sleeve_vs_empty_backtest.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n======== 结果（仅 severe/空仓日）========")
    for k in (k_empty, k_sleeve):
        print(
            f"{k['arm']}: days={k.get('n_severe_days')} fills={k.get('n_filled_trades')} "
            f"day_avg={ (k.get('day_avg_return') or 0)*100:.3f}% "
            f"total={ (k.get('total_return') or 0)*100:.2f}% "
            f"maxDD={ (k.get('max_drawdown') or 0)*100:.2f}% "
            f"hit3%={None if k.get('hit_3pct_rate') is None else round(k['hit_3pct_rate']*100,1)}"
        )
    print(
        f"DELTA sleeve-empty: total {delta['total_return_pp']:+.2f}pp "
        f"maxDD {delta['maxDD_pp']:+.2f}pp day_avg {delta['day_avg_pp']:+.3f}pp"
    )
    print("saved", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
