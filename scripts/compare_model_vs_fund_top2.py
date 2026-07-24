#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A4: 纯模型 Top2 vs 资金重排 Top2 归因

在同一日、同一 GC∩可评分池内：
  M = 按 VM2.5 score Top2
  F = 按 main_net_today（或 5d）Top2
比较 T+1 开 → T+2 收 收益，并按 market_env regime 切片。

用法:
  python3 -u scripts/compare_model_vs_fund_top2.py --start 2026-04-01 --end 2026-07-17 --top-n 2
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/ubuntu/alphapilot")
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from backtest_v3_pipeline import volume_gc_asof  # noqa: E402
from vm25_scorer import VM25Scorer  # noqa: E402


def bare(sym: str) -> str:
    s = str(sym).strip()
    if "." in s:
        s = s.split(".")[0]
    return s.zfill(6)[-6:]


def load_regime_map() -> dict[str, str]:
    """粗标签：用指数 5 日收益近似。优先读 snapshot 历史若无则按上证算。"""
    kf = ROOT / "data" / "kline_cache" / "kline_all.parquet"
    # 用全市场中位涨跌近似广度；简化：读 market_env 若无则全部 unknown
    snap = ROOT / "output" / "market_env_snapshot.json"
    out = {}
    if snap.exists():
        m = json.loads(snap.read_text(encoding="utf-8"))
        asof = str(m.get("asof") or "")[:10]
        idx = (m.get("indexes") or {}).get("sh_main") or {}
        if idx.get("severe"):
            tag = "severe"
        elif idx.get("weak"):
            tag = "weak"
        else:
            tag = "normal"
        if asof:
            out[asof] = tag
    # 用上证日K扩展（若有）
    try:
        import requests

        url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        r = requests.get(
            url,
            params={
                "secid": "1.000001",
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                "klt": 101,
                "fqt": 1,
                "end": "20500101",
                "lmt": 120,
            },
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"},
        )
        rows = (r.json().get("data") or {}).get("klines") or []
        closes = []
        dates = []
        for row in rows:
            p = str(row).split(",")
            dates.append(p[0][:10])
            closes.append(float(p[2]))
        s = pd.Series(closes, index=dates)
        ret5 = s.pct_change(5)
        for d, v in ret5.items():
            if pd.isna(v):
                continue
            if v <= -0.05:
                out[d] = "severe"
            elif v <= -0.02:
                out[d] = "weak"
            else:
                out[d] = "normal"
    except Exception as e:
        print("regime fetch warn:", e)
    return out


def settle_ret(g: pd.DataFrame, ai: int) -> float | None:
    """信号日 ai，T+1 开买 → T+2 收买。"""
    if ai + 2 >= len(g):
        return None
    buy = float(g.iloc[ai + 1]["open"])
    sell = float(g.iloc[ai + 2]["close"])
    if buy <= 0:
        return None
    return sell / buy - 1.0 - 0.0015


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-04-01")
    ap.add_argument("--end", default="2026-07-17")
    ap.add_argument("--top-n", type=int, default=2)
    ap.add_argument("--max-pool", type=int, default=80, help="每日最多评分票数（加速）")
    args = ap.parse_args()

    print("load kline…", flush=True)
    kdf = pd.read_parquet(ROOT / "data/kline_cache/kline_all.parquet")
    kdf["date"] = kdf["date"].astype(str).str[:10]
    kdf["symbol"] = kdf["symbol"].map(bare)
    by = {s: g.sort_values("date").reset_index(drop=True) for s, g in kdf.groupby("symbol")}
    dates = sorted(d for d in kdf["date"].unique() if args.start <= d <= args.end)
    print(f"days={len(dates)} symbols={len(by)}", flush=True)

    fund = {}
    ff = ROOT / "data/fund_flow_history.json"
    if ff.exists():
        raw = json.loads(ff.read_text(encoding="utf-8"))
        fund = {bare(k): v for k, v in raw.items() if isinstance(v, dict)}

    regimes = load_regime_map()
    scorer = VM25Scorer(prefer="opt")
    assert scorer.load(), "VM2.5 load failed"

    arms = {"M_model": [], "F_fund": []}
    overlap_days = []

    for di, d in enumerate(dates):
        # GC 池
        pool = []
        for sym, g in by.items():
            if d not in set(g["date"]):
                continue
            ai = int(g.index[g["date"] == d][0])
            if ai < 60 or not volume_gc_asof(g, ai):
                continue
            pool.append((sym, g, ai))
        if not pool:
            continue
        # 评分
        scored = []
        for sym, g, ai in pool[: args.max_pool] if len(pool) > args.max_pool else pool:
            # 若池太大，先按近5日金额粗筛
            pass
        if len(pool) > args.max_pool:
            pool = sorted(
                pool,
                key=lambda x: float(x[1].iloc[x[2]].get("amount") or 0),
                reverse=True,
            )[: args.max_pool]

        for sym, g, ai in pool:
            sub = g.iloc[: ai + 1].tail(180).copy()
            r = scorer.score(sub, sym)
            if r.get("error"):
                continue
            fh = fund.get(sym) or {}
            main = float(fh.get(d) or fh.get(d.replace("-", "")) or 0)
            # fund_hist 可能是 {date: net}
            if not main and isinstance(fh, dict):
                for k in (d, d.replace("-", "")):
                    if k in fh:
                        try:
                            main = float(fh[k])
                        except Exception:
                            pass
            scored.append(
                {
                    "symbol": sym,
                    "score": float(r["score"]),
                    "main_net": main,
                    "g": g,
                    "ai": ai,
                }
            )
        if len(scored) < args.top_n:
            continue

        m_pick = sorted(scored, key=lambda x: x["score"], reverse=True)[: args.top_n]
        f_pick = sorted(scored, key=lambda x: x["main_net"], reverse=True)[: args.top_n]
        m_set = {x["symbol"] for x in m_pick}
        f_set = {x["symbol"] for x in f_pick}
        overlap_days.append(len(m_set & f_set) / args.top_n)
        reg = regimes.get(d, "unknown")

        for arm, picks in (("M_model", m_pick), ("F_fund", f_pick)):
            rets = []
            for p in picks:
                rt = settle_ret(p["g"], p["ai"])
                if rt is None:
                    continue
                rets.append(rt)
                arms[arm].append(
                    {
                        "date": d,
                        "symbol": p["symbol"],
                        "ret": rt,
                        "regime": reg,
                        "score": p["score"],
                        "main_net": p["main_net"],
                    }
                )
            if rets:
                pass
        if (di + 1) % 5 == 0:
            print(
                f"  {d} pool={len(pool)} scored={len(scored)} overlap={overlap_days[-1]:.0%} regime={reg}",
                flush=True,
            )

    def summarize(name, rows):
        if not rows:
            return {"arm": name, "n": 0}
        rets = [r["ret"] for r in rows]
        by_reg = defaultdict(list)
        for r in rows:
            by_reg[r["regime"]].append(r["ret"])
        return {
            "arm": name,
            "n": len(rows),
            "win_rate": float(np.mean([x > 0 for x in rets])),
            "avg_ret": float(np.mean(rets)),
            "hit_3pct": float(np.mean([x >= 0.03 for x in rets])),
            "overlap_rate_mean": float(np.mean(overlap_days)) if overlap_days else None,
            "by_regime": {
                k: {
                    "n": len(v),
                    "avg_ret": float(np.mean(v)),
                    "win_rate": float(np.mean([x > 0 for x in v])),
                }
                for k, v in by_reg.items()
            },
        }

    # paired delta
    m_map = {(r["date"], r["symbol"]): r["ret"] for r in arms["M_model"]}
    # day-level equal-weight portfolio delta
    day_m = defaultdict(list)
    day_f = defaultdict(list)
    for r in arms["M_model"]:
        day_m[r["date"]].append(r["ret"])
    for r in arms["F_fund"]:
        day_f[r["date"]].append(r["ret"])
    deltas = []
    for d in sorted(set(day_m) & set(day_f)):
        deltas.append(float(np.mean(day_f[d]) - np.mean(day_m[d])))

    out = {
        "protocol": {
            "M": "VM2.5 score TopN in GC pool",
            "F": "main_net TopN in same pool",
            "exit": "T+1 open -> T+2 close - 15bp",
            "top_n": args.top_n,
        },
        "window": {"start": args.start, "end": args.end},
        "overlap_rate_mean": float(np.mean(overlap_days)) if overlap_days else None,
        "F_minus_M_day": {
            "n_days": len(deltas),
            "avg_delta": float(np.mean(deltas)) if deltas else None,
            "win_rate_F_better": float(np.mean([x > 0 for x in deltas])) if deltas else None,
        },
        "kpi": [summarize("M_model", arms["M_model"]), summarize("F_fund", arms["F_fund"])],
    }
    path = ROOT / "output" / "compare_model_vs_fund_top2.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2), flush=True)
    print("saved", path, flush=True)


if __name__ == "__main__":
    main()
