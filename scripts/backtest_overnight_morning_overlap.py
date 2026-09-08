#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""隔夜池 ∩ 开盘信号 交叉验证回测（代理版）

问题：生产上 09:35 曾覆盖隔夜 daily_recommend，成对历史快照不足。
本脚本用可复现代理验证「重叠加分是否提升收益」：

  隔夜池 O_t  = 按 T-1 主力净流入 Top N（代理 05:00 先验）
  开盘分 M_t  = 当日高开 gap_z ×0.5 + T-1 资金 z ×0.5（代理 09:35 动量，无未来函数）
  方案：
    A baseline     : 全市场按 M 取 Top2
    B overlap_boost: 若在 O 内则 M × boost，再取 Top2
    C intersect    : 只在 O 内按 M 取 Top2

交易假设：T 日开盘买入、收盘卖出；成本 round-trip 20bp。
结论仅作方向验证；正式晋升仍需真实 overnight/morning 归档样本。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/ubuntu/alphapilot")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FF_PATH = ROOT / "data" / "fund_flow_history.json"
KLINE_PATH = ROOT / "data" / "kline_cache" / "kline_all.parquet"
OUT_PATH = ROOT / "output" / "reviews" / "overnight_morning_overlap_backtest.json"


def _bare(s: str) -> str:
    s = str(s or "")
    for p in ("sh", "sz", "bj", "SH", "SZ", "BJ"):
        s = s.replace(p, "")
    return s[-6:] if len(s) >= 6 else s


def load_fund_panel() -> pd.DataFrame:
    raw = json.loads(FF_PATH.read_text(encoding="utf-8"))
    rows = []
    for sym, days in raw.items():
        if not isinstance(days, dict):
            continue
        code = _bare(sym)
        if len(code) != 6:
            continue
        for d, v in days.items():
            try:
                rows.append({"symbol": code, "date": str(d)[:10], "main_net": float(v)})
            except (TypeError, ValueError):
                continue
    df = pd.DataFrame(rows)
    if df.empty:
        raise SystemExit("fund_flow_history empty")
    return df


def load_kline() -> pd.DataFrame:
    df = pd.read_parquet(KLINE_PATH)
    df = df.copy()
    df["symbol"] = df["symbol"].map(_bare)
    df["date"] = df["date"].astype(str).str[:10]
    df = df.sort_values(["symbol", "date"])
    df["prev_close"] = df.groupby("symbol")["close"].shift(1)
    df["gap_pct"] = (df["open"] / df["prev_close"] - 1.0) * 100.0
    df["intraday_ret"] = df["close"] / df["open"] - 1.0
    return df[["symbol", "date", "open", "close", "gap_pct", "intraday_ret", "prev_close"]]


def _z(series: pd.Series) -> pd.Series:
    x = series.astype(float)
    mu = x.mean()
    sd = x.std(ddof=0)
    if not np.isfinite(sd) or sd < 1e-12:
        return pd.Series(np.zeros(len(x)), index=x.index)
    return (x - mu) / sd


def summarize(daily_rets: list[float], label: str) -> dict:
    arr = np.array(daily_rets, dtype=float)
    if len(arr) == 0:
        return {"scheme": label, "n_days": 0}
    equity = np.cumprod(1.0 + arr)
    peak = np.maximum.accumulate(equity)
    dd = equity / peak - 1.0
    return {
        "scheme": label,
        "n_days": int(len(arr)),
        "total_return": round(float(equity[-1] - 1.0), 4),
        "avg_day_return": round(float(arr.mean()), 4),
        "win_rate": round(float((arr > 0).mean()), 4),
        "max_drawdown": round(float(dd.min()), 4),
        "sharpe_proxy": round(float(arr.mean() / (arr.std(ddof=0) + 1e-12) * np.sqrt(252)), 3),
    }


def run(boost: float, overnight_n: int, top_n: int, cost_rt: float) -> dict:
    ff = load_fund_panel()
    kl = load_kline()
    dates = sorted(set(ff["date"]) & set(kl["date"]))
    # 需要 T-1 资金
    date_index = {d: i for i, d in enumerate(dates)}
    usable = []
    for d in dates:
        i = date_index[d]
        if i == 0:
            continue
        usable.append((dates[i - 1], d))

    schemes = {
        "A_morning_only": [],
        "B_overlap_boost": [],
        "C_intersect_only": [],
    }
    day_details = []

    for prev_d, d in usable:
        ff_prev = ff[ff["date"] == prev_d][["symbol", "main_net"]].rename(
            columns={"main_net": "main_net_prev"}
        )
        day_kl = kl[kl["date"] == d][["symbol", "gap_pct", "intraday_ret", "open"]].copy()
        day_kl = day_kl[day_kl["open"] > 0]
        day_kl = day_kl.merge(ff_prev, on="symbol", how="inner")
        if len(day_kl) < 50:
            continue

        # 隔夜池：T-1 资金 TopN
        o_set = set(
            ff_prev.sort_values("main_net_prev", ascending=False)
            .head(overnight_n)["symbol"]
            .tolist()
        )

        day_kl["m_score"] = 0.5 * _z(day_kl["gap_pct"]) + 0.5 * _z(day_kl["main_net_prev"])
        day_kl["in_overnight"] = day_kl["symbol"].isin(o_set)
        day_kl["b_score"] = day_kl["m_score"] * np.where(
            day_kl["in_overnight"], boost, 1.0
        )

        def pick(score_col: str, pool: pd.DataFrame | None = None) -> list[str]:
            src = day_kl if pool is None else day_kl[day_kl["symbol"].isin(pool)]
            if src.empty:
                return []
            return (
                src.sort_values(score_col, ascending=False)
                .head(top_n)["symbol"]
                .tolist()
            )

        a = pick("m_score")
        b = pick("b_score")
        c = pick("m_score", o_set)

        def day_ret(syms: list[str]) -> float | None:
            if not syms:
                return None
            sub = day_kl[day_kl["symbol"].isin(syms)]
            if sub.empty:
                return None
            return float(sub["intraday_ret"].mean() - cost_rt)

        ra, rb, rc = day_ret(a), day_ret(b), day_ret(c)
        if ra is None or rb is None or rc is None:
            continue
        schemes["A_morning_only"].append(ra)
        schemes["B_overlap_boost"].append(rb)
        schemes["C_intersect_only"].append(rc)
        day_details.append(
            {
                "date": d,
                "overnight_n": len(o_set),
                "A": {"syms": a, "ret": round(ra, 4)},
                "B": {"syms": b, "ret": round(rb, 4)},
                "C": {"syms": c, "ret": round(rc, 4)},
                "overlap_in_A": sum(1 for s in a if s in o_set),
                "overlap_in_B": sum(1 for s in b if s in o_set),
            }
        )

    summary = [summarize(v, k) for k, v in schemes.items()]
    # 排序：总收益
    best = max(summary, key=lambda x: x.get("total_return", -1e9)) if summary else {}
    out = {
        "hypothesis": "隔夜池与开盘信号交叉验证（重叠加分）应提升收益",
        "proxy_note": (
            "隔夜=T-1资金TopN；开盘分=当日gap_z+T-1资金_z；"
            "非生产 05:00/09:35 原样复现，仅验证方向"
        ),
        "params": {
            "boost": boost,
            "overnight_n": overnight_n,
            "top_n": top_n,
            "cost_rt": cost_rt,
            "entry_exit": "open_to_close_same_day",
        },
        "summary": summary,
        "winner_by_total_return": best.get("scheme"),
        "n_days": len(day_details),
        "tail_days": day_details[-5:],
        "verdict": _verdict(summary),
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def _verdict(summary: list[dict]) -> str:
    by = {s["scheme"]: s for s in summary if s.get("n_days")}
    a, b = by.get("A_morning_only"), by.get("B_overlap_boost")
    if not a or not b:
        return "INSUFFICIENT_DATA"
    if b["total_return"] > a["total_return"] and b["win_rate"] >= a["win_rate"] - 0.02:
        return "SUPPORTS_OVERLAP_BOOST"
    if b["total_return"] > a["total_return"]:
        return "WEAK_SUPPORT_RETURN_UP_WINRATE_MIXED"
    return "DOES_NOT_BEAT_BASELINE"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boost", type=float, default=1.12)
    ap.add_argument("--overnight-n", type=int, default=100)
    ap.add_argument("--top-n", type=int, default=2)
    ap.add_argument("--cost-rt", type=float, default=0.002)
    args = ap.parse_args()
    out = run(args.boost, args.overnight_n, args.top_n, args.cost_rt)
    print(json.dumps({k: out[k] for k in (
        "verdict", "winner_by_total_return", "n_days", "params", "summary", "proxy_note"
    )}, ensure_ascii=False, indent=2))
    print(f"saved {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
