#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三臂入场对照：固定9:35 / GapSoft C / ML开盘择时

选股：严格量价金叉 + VM2.5 TopN + 资金硬门控（同 entry_gap）
分钟：通达信 mootdx.minutes(date=) 全日240根1分钟（09:30起）
出场：买入日下一根日K收盘（T+2），成本 15bp

臂:
  A_0935     : T+1 日 09:35 价买入（近涨停跳过）
  B_gap_soft : 现有 GapSoft C（日K open/low）
  C_ml_time  : walk-forward XGB 在 {09:35,09:45,10:00} 中选最低价窗口
               特征仅用开盘已知信息（隔夜/开盘缺口等），避免用到未来分钟

用法:
  python3 -u backtest_entry_timing_3arm.py --start 2026-04-01 --end 2026-07-17 --top-n 2
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
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent

from backtest_entry_gap import (  # noqa: E402
    entry_gap_soft,
    settle_t2_from_buy,
    summarize,
)
from backtest_exit_peel import limit_pct, pick_candidates_vm25, _bare  # noqa: E402

MIN_CACHE = ROOT / "data" / "minute_cache_tdx"
OUT_JSON = ROOT / "output" / "entry_timing_3arm_backtest.json"

# 240根：09:30-11:30(120) + 13:00-15:00(120)
IDX = {"0935": 5, "0945": 15, "1000": 30}
WINDOWS = ["0935", "0945", "1000"]


def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


_quotes = None


def _client():
    global _quotes
    if _quotes is None:
        from mootdx.quotes import Quotes

        _quotes = Quotes.factory(market="std")
    return _quotes


def fetch_minutes(sym: str, yyyymmdd: str) -> pd.DataFrame | None:
    """通达信按日1分钟；缓存到本地 parquet。"""
    MIN_CACHE.mkdir(parents=True, exist_ok=True)
    path = MIN_CACHE / f"{sym}_{yyyymmdd}.parquet"
    if path.exists():
        try:
            return pd.read_parquet(path)
        except Exception:
            pass
    try:
        df = _client().minutes(symbol=sym, date=yyyymmdd)
        if df is None or len(df) < 31:
            return None
        df = df.reset_index(drop=True)
        df.to_parquet(path, index=False)
        return df
    except Exception as e:
        log(f"  minute fail {sym} {yyyymmdd}: {e}")
        return None


def px_at(df: pd.DataFrame, window: str) -> float | None:
    i = IDX[window]
    if df is None or len(df) <= i:
        return None
    p = float(df.iloc[i]["price"])
    return p if p > 0 else None


def best_window(df: pd.DataFrame) -> tuple[str, float]:
    prices = {w: px_at(df, w) for w in WINDOWS}
    prices = {w: p for w, p in prices.items() if p}
    if not prices:
        return "0935", float("nan")
    w = min(prices, key=prices.get)
    return w, prices[w]


def overnight_features(g, bi: int, sym: str, gap: float) -> dict:
    """开盘已知特征（不含当日分钟路径）。"""
    prev = float(g.loc[bi - 1, "close"]) if bi >= 1 else float(g.loc[bi, "open"])
    op = float(g.loc[bi, "open"])
    # 近5/20日收益与波动
    closes = g["close"].astype(float).iloc[max(0, bi - 21) : bi].tolist()
    rets = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0:
            rets.append(closes[i] / closes[i - 1] - 1.0)
    vol20 = float(np.std(rets[-20:])) if len(rets) >= 5 else 0.0
    ret5 = float(np.prod([1 + x for x in rets[-5:]]) - 1) if rets else 0.0
    ret1 = float(rets[-1]) if rets else 0.0
    # 昨日振幅
    if bi >= 1:
        hi = float(g.loc[bi - 1, "high"])
        lo = float(g.loc[bi - 1, "low"])
        amp = (hi - lo) / prev if prev > 0 else 0.0
    else:
        amp = 0.0
    board = 0.2 if sym.startswith("3") or sym.startswith("68") else 0.1
    return {
        "gap": gap,
        "gap_abs": abs(gap),
        "ret1": ret1,
        "ret5": ret5,
        "vol20": vol20,
        "amp": amp,
        "board": board,
        "open_vs_prev_high": (op / hi - 1.0) if bi >= 1 and hi > 0 else 0.0,
    }


FEAT_COLS = ["gap", "gap_abs", "ret1", "ret5", "vol20", "amp", "board", "open_vs_prev_high"]


def train_predict(history: list[dict], feat: dict) -> tuple[str, float]:
    """返回 (窗口, 置信度)；样本不足默认 0935 / conf=0。"""
    if len(history) < 40:
        return "0935", 0.0
    try:
        from xgboost import XGBClassifier
    except ImportError:
        return "0935", 0.0

    X = np.array([[h["feat"][c] for c in FEAT_COLS] for h in history], dtype=float)
    y = np.array([WINDOWS.index(h["label"]) for h in history], dtype=int)
    if len(set(y.tolist())) < 2:
        return "0935", 0.0
    clf = XGBClassifier(
        n_estimators=60,
        max_depth=3,
        learning_rate=0.08,
        subsample=0.9,
        colsample_bytree=0.9,
        objective="multi:softprob",
        num_class=3,
        eval_metric="mlogloss",
        verbosity=0,
    )
    clf.fit(X, y)
    xp = np.array([[feat[c] for c in FEAT_COLS]], dtype=float)
    proba = clf.predict_proba(xp)[0]
    pred = int(np.argmax(proba))
    return WINDOWS[pred], float(proba[pred])


def hybrid_c_ml_fill(st_c: dict, mdf: pd.DataFrame, win: str, conf: float, conf_min: float = 0.42):
    """C 定资格/权重；ML 置信度够才改择时，否则完全跟 C。

    - open_ok: 用 ML 窗口分钟价（C 已允许当日买）
    - limit_*: ML 价 ≤ 限价则用 ML 价，否则回退 C 成交价
    """
    w = float(st_c.get("weight") or 1.0)
    c_buy = float(st_c["buy"])
    mode = st_c.get("entry_mode") or ""
    if conf < conf_min:
        return c_buy, w, f"c_only_{mode}", False

    ml_px = px_at(mdf, win) or px_at(mdf, "0935")
    if not ml_px:
        return c_buy, w, f"c_only_{mode}", False

    if mode == "open_ok":
        return ml_px, w, f"c_ml_{win}", True

    # 限价带：不得超过 C 的限价（若有）；否则不得超过 C 实际成交价
    lim = st_c.get("limit")
    cap = float(lim) if lim else c_buy
    if ml_px <= cap + 1e-9:
        return ml_px, w, f"c_ml_{win}", True
    return c_buy, w, f"c_fb_{mode}", False


def settle_from_fill(g, bi: int, buy: float, cost_rt: float, mode: str, weight: float = 1.0):
    return settle_t2_from_buy(g, bi, buy, cost_rt, mode, weight)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-04-01")
    ap.add_argument("--end", default="2026-07-17")
    ap.add_argument("--top-n", type=int, default=2)
    ap.add_argument("--threshold", type=float, default=0.03)
    ap.add_argument("--cost-rt", type=float, default=0.0015)
    ap.add_argument("--prefer", default="opt")
    ap.add_argument("--limit-frac", type=float, default=0.97)
    ap.add_argument("--no-fund-gate", action="store_true")
    args = ap.parse_args()
    args.fund_gate = not args.no_fund_gate

    os.chdir(ROOT)
    from vm25_scorer import VM25Scorer
    from backtest_v3_pipeline import volume_gc_asof, fund_gate_ok as fund_gate_pipeline

    kpath = ROOT / "data/kline_cache/kline_all.parquet"
    if not kpath.exists():
        kpath = ROOT / "kline_all.parquet"
    log(f"load kline {kpath}")
    kdf = pd.read_parquet(kpath)
    kdf["date"] = kdf["date"].astype(str).str[:10]
    kdf["symbol"] = kdf["symbol"].astype(str).map(_bare)
    kdf = kdf[~kdf["symbol"].str.startswith(("8", "4"))]
    kdf = kdf.sort_values(["symbol", "date"]).reset_index(drop=True)
    groups = {
        sym: g.sort_values("date").reset_index(drop=True)
        for sym, g in kdf.groupby("symbol", sort=False)
    }
    cal_sym = "600519" if "600519" in groups else next(iter(groups))
    dates = sorted(d for d in groups[cal_sym]["date"].unique() if args.start <= d <= args.end)

    scorer = VM25Scorer(prefer=args.prefer)
    assert scorer.load(), "VM2.5 load failed"
    log(f"days={len(dates)} symbols={len(groups)} top_n={args.top_n}")

    arms = {"A_0935": [], "B_gap_soft": [], "C_ml_time": [], "D_c_ml": []}
    ml_hist: list[dict] = []
    n_min_ok = n_min_miss = 0
    n_hybrid_ml = n_hybrid_c = 0

    for i, d in enumerate(dates):
        picks = pick_candidates_vm25(
            groups, d, args, scorer, volume_gc_asof, fund_gate_pipeline
        )
        if i % 5 == 0:
            log(f"  {d} picks={len(picks)} ml_hist={len(ml_hist)} min_ok={n_min_ok} miss={n_min_miss}")

        for row in picks:
            sym = _bare(str(row["symbol"]))
            g = groups.get(sym)
            if g is None:
                continue
            m = g.index[g["date"] == d]
            if len(m) == 0:
                continue
            signal_ai = int(m[0])
            if signal_ai + 2 >= len(g):
                continue
            bi = signal_ai + 1
            buy_date = str(g.loc[bi, "date"])[:10]
            prev = float(g.loc[signal_ai, "close"])
            op = float(g.loc[bi, "open"])
            if prev <= 0 or op <= 0:
                continue
            gap = op / prev - 1.0
            lim = limit_pct(sym) * args.limit_frac
            near_limit = gap >= lim

            # —— B GapSoft C ——
            st_b = entry_gap_soft(g, signal_ai, sym, args.cost_rt, args.limit_frac)
            if st_b is None:
                continue
            c_skipped = bool(st_b.get("skip"))
            if c_skipped:
                arms["B_gap_soft"].append(
                    {
                        "date": d,
                        "symbol": sym,
                        "skipped": True,
                        "skip_reason": st_b.get("skip"),
                    }
                )
                arms["D_c_ml"].append(
                    {
                        "date": d,
                        "symbol": sym,
                        "skipped": True,
                        "skip_reason": st_b.get("skip"),
                    }
                )
            else:
                arms["B_gap_soft"].append(
                    {
                        "date": d,
                        "symbol": sym,
                        "skipped": False,
                        "ret": st_b["ret"],
                        "full_ret": st_b["full_ret"],
                        "weight": st_b["weight"],
                        "entry_mode": st_b["entry_mode"],
                        "buy": st_b["buy"],
                        "buy_date": st_b["buy_date"],
                    }
                )

            # —— 分钟：A / C_ml / D_c_ml ——
            ymd = buy_date.replace("-", "")
            mdf = fetch_minutes(sym, ymd)
            if mdf is None or near_limit:
                n_min_miss += 1
                reason = "open_limit" if near_limit else "no_minute"
                for arm in ("A_0935", "C_ml_time"):
                    arms[arm].append(
                        {
                            "date": d,
                            "symbol": sym,
                            "skipped": True,
                            "skip_reason": reason,
                        }
                    )
                # D：C 已通过但无分钟 → 退回纯 C（尚未写入 D）
                if not c_skipped:
                    arms["D_c_ml"].append(
                        {
                            "date": d,
                            "symbol": sym,
                            "skipped": False,
                            "ret": st_b["ret"],
                            "full_ret": st_b["full_ret"],
                            "weight": st_b["weight"],
                            "entry_mode": "c_only_nominute",
                            "buy": st_b["buy"],
                            "buy_date": st_b["buy_date"],
                            "ml_used": False,
                        }
                    )
                continue
            n_min_ok += 1

            lab, _ = best_window(mdf)
            feat = overnight_features(g, bi, sym, gap)
            win, conf = train_predict(ml_hist, feat)

            # A: 固定 9:35
            px_a = px_at(mdf, "0935")
            if not px_a:
                arms["A_0935"].append(
                    {"date": d, "symbol": sym, "skipped": True, "skip_reason": "no_0935"}
                )
            else:
                st_a = settle_from_fill(g, bi, px_a, args.cost_rt, "0935", 1.0)
                if st_a and not st_a.get("skip"):
                    arms["A_0935"].append(
                        {
                            "date": d,
                            "symbol": sym,
                            "skipped": False,
                            "ret": st_a["ret"],
                            "full_ret": st_a["full_ret"],
                            "weight": 1.0,
                            "entry_mode": "0935",
                            "buy": st_a["buy"],
                            "buy_date": st_a["buy_date"],
                        }
                    )
                else:
                    arms["A_0935"].append(
                        {
                            "date": d,
                            "symbol": sym,
                            "skipped": True,
                            "skip_reason": (st_a or {}).get("skip") or "settle_fail",
                        }
                    )

            # C: 纯 ML 择时（无视 GapSoft）
            px_c = px_at(mdf, win) or px_at(mdf, "0935")
            if not px_c:
                arms["C_ml_time"].append(
                    {"date": d, "symbol": sym, "skipped": True, "skip_reason": "no_ml_px"}
                )
            else:
                st_c = settle_from_fill(g, bi, px_c, args.cost_rt, f"ml_{win}", 1.0)
                if st_c and not st_c.get("skip"):
                    arms["C_ml_time"].append(
                        {
                            "date": d,
                            "symbol": sym,
                            "skipped": False,
                            "ret": st_c["ret"],
                            "full_ret": st_c["full_ret"],
                            "weight": 1.0,
                            "entry_mode": f"ml_{win}",
                            "buy": st_c["buy"],
                            "buy_date": st_c["buy_date"],
                            "ml_window": win,
                            "label_window": lab,
                        }
                    )
                else:
                    arms["C_ml_time"].append(
                        {
                            "date": d,
                            "symbol": sym,
                            "skipped": True,
                            "skip_reason": (st_c or {}).get("skip") or "settle_fail",
                        }
                    )

            # D: GapSoft C × ML（仅 C 过门时）
            if not c_skipped:
                fill_d, w_d, mode_d, ml_used = hybrid_c_ml_fill(st_b, mdf, win, conf)
                if ml_used:
                    n_hybrid_ml += 1
                else:
                    n_hybrid_c += 1
                st_d = settle_from_fill(g, bi, fill_d, args.cost_rt, mode_d, w_d)
                if st_d and not st_d.get("skip"):
                    arms["D_c_ml"].append(
                        {
                            "date": d,
                            "symbol": sym,
                            "skipped": False,
                            "ret": st_d["ret"],
                            "full_ret": st_d["full_ret"],
                            "weight": w_d,
                            "entry_mode": mode_d,
                            "buy": st_d["buy"],
                            "buy_date": st_d["buy_date"],
                            "ml_window": win,
                            "ml_conf": round(conf, 4),
                            "ml_used": ml_used,
                            "label_window": lab,
                            "c_buy": st_b["buy"],
                        }
                    )
                else:
                    arms["D_c_ml"].append(
                        {
                            "date": d,
                            "symbol": sym,
                            "skipped": True,
                            "skip_reason": (st_d or {}).get("skip") or "settle_fail",
                        }
                    )

            if lab in WINDOWS and not any(np.isnan(feat[c]) for c in FEAT_COLS):
                ml_hist.append({"feat": feat, "label": lab, "date": buy_date, "symbol": sym})

    kpis = [
        summarize(arms[k], k, args.threshold)
        for k in ("A_0935", "B_gap_soft", "C_ml_time", "D_c_ml")
    ]

    filled_c = [t for t in arms["C_ml_time"] if not t.get("skipped") and t.get("ml_window")]
    ml_acc = (
        float(np.mean([t["ml_window"] == t.get("label_window") for t in filled_c]))
        if filled_c
        else None
    )
    filled_d = [t for t in arms["D_c_ml"] if not t.get("skipped")]
    d_ml_used = [t for t in filled_d if t.get("ml_used")]
    d_vs_c = None
    if filled_d:
        # 相对纯 C：同日同票收益差（仅 D 与 B 都成交）
        b_map = {
            (t["date"], t["symbol"]): t
            for t in arms["B_gap_soft"]
            if not t.get("skipped")
        }
        deltas = []
        for t in filled_d:
            b = b_map.get((t["date"], t["symbol"]))
            if b:
                deltas.append(float(t["ret"]) - float(b["ret"]))
        d_vs_c = {
            "n_paired": len(deltas),
            "avg_delta_ret": float(np.mean(deltas)) if deltas else None,
            "win_rate_vs_c": float(np.mean([x > 0 for x in deltas])) if deltas else None,
            "ml_used_rate": float(len(d_ml_used) / max(len(filled_d), 1)),
        }

    out = {
        "protocol": {
            "rank": "VM2.5 + strict GC + hard fund gate",
            "exit": "T+2 close",
            "A": "T+1 09:35 minute price",
            "B": "GapSoft C alone",
            "C": "ML timing alone (ignore GapSoft)",
            "D": "GapSoft C gate + ML timing when conf>=0.42; else pure C",
            "minute_source": "mootdx.minutes(date=)",
            "cost_rt": args.cost_rt,
            "top_n": args.top_n,
        },
        "window": {"start": args.start, "end": args.end},
        "minute_stats": {"ok": n_min_ok, "miss": n_min_miss, "ml_samples": len(ml_hist)},
        "hybrid_stats": {"ml_timed": n_hybrid_ml, "c_fallback": n_hybrid_c},
        "ml_window_accuracy": ml_acc,
        "D_vs_B": d_vs_c,
        "kpi": kpis,
        "recommendation": _prefer(kpis),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    log("======== Entry Timing Arms (incl C×ML) ========")
    print(json.dumps(out["protocol"], ensure_ascii=False), flush=True)
    for k in kpis:
        print(json.dumps(k, ensure_ascii=False), flush=True)
    print("ml_acc", ml_acc, "D_vs_B", d_vs_c, "recommend", out["recommendation"], flush=True)
    log(f"saved {OUT_JSON}")


def _prefer(kpis: list[dict]) -> dict:
    by = {k["arm"]: k for k in kpis if k.get("n_filled")}
    if not by:
        return {"prefer": None, "reason": "no fills"}
    best = max(
        by.values(),
        key=lambda x: (x.get("avg_ret") or -9, -(abs(x.get("max_drawdown") or 9))),
    )
    return {
        "prefer": best["arm"],
        "avg_ret": best.get("avg_ret"),
        "win_rate": best.get("win_rate"),
        "max_drawdown": best.get("max_drawdown"),
        "reason": "highest avg_ret among filled arms",
    }


if __name__ == "__main__":
    main()
