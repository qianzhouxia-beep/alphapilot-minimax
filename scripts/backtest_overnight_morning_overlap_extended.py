#!/usr/bin/env python3
"""Historical overlap backtest — single pass, two hold modes + boost grid."""
from __future__ import annotations

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
OUT = ROOT / "output" / "reviews" / "overnight_morning_overlap_backtest_extended.json"


def bare(s: str) -> str:
    s = str(s or "")
    for p in ("sh", "sz", "bj", "SH", "SZ", "BJ"):
        s = s.replace(p, "")
    return s[-6:] if len(s) >= 6 else s


def z(s: pd.Series) -> pd.Series:
    x = s.astype(float)
    sd = x.std(ddof=0)
    if not np.isfinite(sd) or sd < 1e-12:
        return pd.Series(np.zeros(len(x)), index=x.index)
    return (x - x.mean()) / sd


def summarize(arr, label):
    arr = np.asarray(arr, dtype=float)
    if len(arr) == 0:
        return {"scheme": label, "n_days": 0}
    eq = np.cumprod(1 + arr)
    peak = np.maximum.accumulate(eq)
    dd = eq / peak - 1
    return {
        "scheme": label,
        "n_days": int(len(arr)),
        "total_return": round(float(eq[-1] - 1), 4),
        "avg_day_return": round(float(arr.mean()), 4),
        "win_rate": round(float((arr > 0).mean()), 4),
        "max_drawdown": round(float(dd.min()), 4),
    }


def main() -> int:
    print("loading fund_flow...", flush=True)
    raw = json.loads(FF_PATH.read_text(encoding="utf-8"))
    rows = []
    for sym, days in raw.items():
        if not isinstance(days, dict):
            continue
        code = bare(sym)
        if len(code) != 6:
            continue
        for d, v in days.items():
            try:
                rows.append({"symbol": code, "date": str(d)[:10], "main_net": float(v)})
            except (TypeError, ValueError):
                continue
    ff = pd.DataFrame(rows)
    print(f"fund rows={len(ff)} days={ff['date'].nunique()}", flush=True)

    print("loading kline...", flush=True)
    kl = pd.read_parquet(KLINE_PATH)
    kl = kl.copy()
    kl["symbol"] = kl["symbol"].map(bare)
    kl["date"] = kl["date"].astype(str).str[:10]
    kl = kl.sort_values(["symbol", "date"])
    kl["prev_close"] = kl.groupby("symbol")["close"].shift(1)
    kl["next_open"] = kl.groupby("symbol")["open"].shift(-1)
    kl["gap_pct"] = (kl["open"] / kl["prev_close"] - 1.0) * 100.0
    kl["ret_oc"] = kl["close"] / kl["open"] - 1.0
    kl["ret_oo"] = kl["next_open"] / kl["open"] - 1.0
    kl = kl[["symbol", "date", "open", "gap_pct", "ret_oc", "ret_oo"]]

    dates = sorted(set(ff["date"]) & set(kl["date"]))
    pairs = [(dates[i - 1], dates[i]) for i in range(1, len(dates))]
    print(f"range {dates[0]} -> {dates[-1]} pairs={len(pairs)}", flush=True)

    COST = 0.002
    ON = 100
    TOP = 2
    boosts = [1.0, 1.08, 1.12, 1.20, 1.30]
    holds = [("open_to_close", "ret_oc"), ("open_to_next_open", "ret_oo")]

    # pre-join panels per day to speed boost grid
    day_cache = []
    for prev_d, d in pairs:
        ff_prev = ff[ff["date"] == prev_d][["symbol", "main_net"]].rename(
            columns={"main_net": "main_net_prev"}
        )
        day = kl[kl["date"] == d].merge(ff_prev, on="symbol", how="inner")
        day = day[(day["open"] > 0) & day["ret_oc"].notna()]
        if len(day) < 50:
            continue
        o_set = set(
            ff_prev.sort_values("main_net_prev", ascending=False).head(ON)["symbol"]
        )
        day = day.copy()
        day["m"] = 0.5 * z(day["gap_pct"]) + 0.5 * z(day["main_net_prev"])
        day["in_o"] = day["symbol"].isin(o_set)
        day_cache.append((d, day, o_set))
    print(f"usable days={len(day_cache)}", flush=True)

    by_hold = {}
    boost_grid = {h: [] for h, _ in holds}

    for hold, col in holds:
        # default boost 1.12 comparison of A/B/C
        schemes = {"A_morning_only": [], "B_overlap_boost": [], "C_intersect_only": []}
        for d, day, o_set in day_cache:
            if col == "ret_oo" and day["ret_oo"].isna().all():
                continue
            tmp = day.dropna(subset=[col]).copy()
            if len(tmp) < 50:
                continue
            tmp["b"] = tmp["m"] * np.where(tmp["in_o"], 1.12, 1.0)

            def pick(score, pool=None):
                src = tmp if pool is None else tmp[tmp["symbol"].isin(pool)]
                if src.empty:
                    return []
                return src.sort_values(score, ascending=False).head(TOP)["symbol"].tolist()

            def rets(syms):
                sub = tmp[tmp["symbol"].isin(syms)]
                if sub.empty:
                    return None
                return float(sub[col].mean() - COST)

            a, b, c = pick("m"), pick("b"), pick("m", o_set)
            ra, rb, rc = rets(a), rets(b), rets(c)
            if None in (ra, rb, rc):
                continue
            schemes["A_morning_only"].append(ra)
            schemes["B_overlap_boost"].append(rb)
            schemes["C_intersect_only"].append(rc)
        by_hold[hold] = [summarize(v, k) for k, v in schemes.items()]

        for boost in boosts:
            a_rets, b_rets = [], []
            for d, day, o_set in day_cache:
                tmp = day.dropna(subset=[col]).copy()
                if len(tmp) < 50:
                    continue
                tmp["b"] = tmp["m"] * np.where(tmp["in_o"], boost, 1.0)
                a = tmp.sort_values("m", ascending=False).head(TOP)
                b = tmp.sort_values("b", ascending=False).head(TOP)
                a_rets.append(float(a[col].mean() - COST))
                b_rets.append(float(b[col].mean() - COST))
            sa, sb = summarize(a_rets, "A"), summarize(b_rets, "B")
            boost_grid[hold].append(
                {
                    "boost": boost,
                    "A_total": sa["total_return"],
                    "B_total": sb["total_return"],
                    "B_minus_A": round(sb["total_return"] - sa["total_return"], 4),
                    "A_win": sa["win_rate"],
                    "B_win": sb["win_rate"],
                    "n_days": sa["n_days"],
                }
            )

    payload = {
        "data_source": {
            "fund_flow_history": str(FF_PATH),
            "kline": str(KLINE_PATH),
            "date_range": [dates[0], dates[-1]],
            "n_pairs": len(pairs),
            "usable_days": len(day_cache),
        },
        "by_hold": by_hold,
        "boost_grid": boost_grid,
        "note": (
            "历史代理回测：隔夜=T-1资金Top100；开盘分=当日高开gap_z+T-1资金_z；"
            "成本双边20bp；非生产05:00/09:35原样复现，验证交叉加分方向"
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
    print(f"saved {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
