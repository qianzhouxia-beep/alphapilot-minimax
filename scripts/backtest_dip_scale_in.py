#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跌幅补仓 A/B 回测（多数据源扩大样本）。

数据源:
  1) 纸面：paper_trading.json + 所有 bak* 合并 trade_log
  2) 可交易历史：v3_tradable_gated*_backtest.json 真实入场票
     协议近似：T+1 开盘买 → 可卖日(T+2) 开盘若相对昨收跌≥thr
       - no_dip: 开盘减半 + 收盘清剩余
       - with_dip(equal_double): 开盘减半 + 等量补仓 + 收盘全清
       - hold_t2: 不做减半/补仓，直接可卖日收盘清（基线）
  3) 全市场日K：kline_all.parquet 全区间 / 大样本规则仿真

输出:
  output/reviews/dip_scale_backtest_YYYY-MM-DD.json

用法:
  python3 -u scripts/backtest_dip_scale_in.py
  python3 -u scripts/backtest_dip_scale_in.py --full-kline --max-syms 2000
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path("/home/ubuntu/alphapilot")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parents[1]

PT_PATH = ROOT / "data" / "paper_trading.json"
KLINE = ROOT / "data" / "kline_cache" / "kline_all.parquet"
OUT_DIR = ROOT / "output" / "reviews"
TRADABLE_CANDIDATES = [
    ROOT / "output" / "v3_tradable_gated_sleeve_backtest.json",
    ROOT / "output" / "v3_tradable_gated_backtest.json",
    ROOT / "output" / "v3_tradable_top3_backtest.json",
]

DIP_THR = 0.05
QTY = 10000  # 名义股数单位


def _bare(s: str) -> str:
    x = str(s or "")
    for p in ("sh", "sz", "bj", "SH", "SZ", "BJ"):
        if x.lower().startswith(p.lower()) and len(x) > 6:
            x = x[len(p) :]
            break
    digits = "".join(ch for ch in x if ch.isdigit())
    return digits[-6:].zfill(6) if digits else x


def _load_all_paper_logs() -> list[dict]:
    logs: list[dict] = []
    seen = set()
    data_dir = ROOT / "data"
    files = [PT_PATH] + sorted(data_dir.glob("paper_trading.json.bak*"))
    for fp in files:
        if not fp.exists():
            continue
        try:
            pt = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        for t in pt.get("trade_log") or []:
            key = (
                str(t.get("time")),
                str(t.get("symbol")),
                str(t.get("action")),
                str(t.get("price")),
                str(t.get("quantity")),
            )
            if key in seen:
                continue
            seen.add(key)
            logs.append(t)
    return logs


def _paper_counterfactual(trade_log: list[dict]) -> dict:
    by_sym: dict[str, list] = defaultdict(list)
    for t in trade_log:
        sym = str(t.get("symbol") or "")
        act = str(t.get("action") or "")
        if not sym:
            continue
        if act.startswith("买入") or act.startswith("卖出"):
            by_sym[sym].append(t)

    cases = []
    for sym, events in by_sym.items():
        events = sorted(events, key=lambda e: str(e.get("time") or ""))
        has_dip = any(e.get("action") == "买入(补仓跌幅)" for e in events)
        if not has_dip:
            continue
        name = events[0].get("name") or sym

        def _sim(skip_dip: bool):
            pos = 0
            cost = 0.0
            realized = 0.0
            dip_qty = 0
            dip_cost = 0.0
            for e in events:
                px = float(e.get("price") or 0)
                q = int(e.get("quantity") or 0)
                act = str(e.get("action") or "")
                if q <= 0 or px <= 0:
                    continue
                if act == "买入(补仓跌幅)" and skip_dip:
                    continue
                if act.startswith("买入"):
                    cost += px * q
                    pos += q
                    if act == "买入(补仓跌幅)":
                        dip_qty += q
                        dip_cost += px * q
                elif act.startswith("卖出"):
                    if pos <= 0:
                        continue
                    q = min(q, pos)
                    avg = cost / pos
                    realized += (px - avg) * q
                    cost -= avg * q
                    pos -= q
            return realized, pos, dip_qty, dip_cost

        r1, rem1, dip_qty, dip_cost = _sim(False)
        r0, rem0, _, _ = _sim(True)
        init = None
        for e in events:
            if str(e.get("action") or "").startswith("买入") and e.get("action") != "买入(补仓跌幅)":
                init = float(e.get("price") or 0) * int(e.get("quantity") or 0)
                if init:
                    break
        cases.append(
            {
                "symbol": sym,
                "name": name,
                "dip_qty": dip_qty,
                "dip_notional": round(dip_cost, 2),
                "with_dip": {
                    "realized_pnl": round(r1, 2),
                    "remaining_qty": rem1,
                    "ret_on_init_pct": round(r1 / init * 100, 2) if init else None,
                },
                "without_dip": {
                    "realized_pnl": round(r0, 2),
                    "remaining_qty": rem0,
                    "ret_on_init_pct": round(r0 / init * 100, 2) if init else None,
                },
                "delta_pnl_without_minus_with": round(r0 - r1, 2),
            }
        )

    tot_with = sum(c["with_dip"]["realized_pnl"] for c in cases)
    tot_wo = sum(c["without_dip"]["realized_pnl"] for c in cases)
    return {
        "n_cases": len(cases),
        "n_trade_log_rows": len(trade_log),
        "total_pnl_with_dip": round(tot_with, 2),
        "total_pnl_without_dip": round(tot_wo, 2),
        "advantage_without_dip": round(tot_wo - tot_with, 2),
        "cases": cases,
    }


def _load_kline():
    if not KLINE.exists():
        return None
    import pandas as pd

    df = pd.read_parquet(KLINE, columns=["symbol", "date", "open", "high", "low", "close"])
    df["symbol"] = df["symbol"].map(_bare)
    df["date"] = df["date"].astype(str).str[:10]
    return df.sort_values(["symbol", "date"]).reset_index(drop=True)


def _paths_on_sell_day(buy_px: float, prev_close: float, open_px: float, close_px: float, thr: float):
    """可卖日三条路径，名义 qty=QTY。返回 dict 或 None（未触发跌幅）。"""
    if buy_px <= 0 or prev_close <= 0 or open_px <= 0 or close_px <= 0:
        return None
    day_chg = open_px / prev_close - 1.0
    if day_chg > -thr:
        return None
    half = QTY // 2
    rem = QTY - half
    init = buy_px * QTY
    # no_dip: 开盘减半 + 收盘清剩余
    pnl_no = (open_px - buy_px) * half + (close_px - buy_px) * rem
    # with_dip equal_double: 减半后补 rem，收盘全清
    pnl_dip = (open_px - buy_px) * half + (close_px - buy_px) * rem + (close_px - open_px) * rem
    # flat: 可卖日收盘一次清（无减半无补仓）
    pnl_flat = (close_px - buy_px) * QTY
    return {
        "day_chg_open": round(day_chg, 4),
        "pnl_no_dip": round(pnl_no, 2),
        "pnl_with_dip": round(pnl_dip, 2),
        "pnl_flat_close": round(pnl_flat, 2),
        "ret_no_pct": round(pnl_no / init * 100, 4),
        "ret_dip_pct": round(pnl_dip / init * 100, 4),
        "ret_flat_pct": round(pnl_flat / init * 100, 4),
        "delta_no_minus_dip": round(pnl_no - pnl_dip, 2),
    }


def _summarize_rows(rows: list[dict], label: str) -> dict:
    if not rows:
        return {"ok": True, "label": label, "n_dip_events": 0}
    n = len(rows)
    sum_no = sum(r["pnl_no_dip"] for r in rows)
    sum_dip = sum(r["pnl_with_dip"] for r in rows)
    sum_flat = sum(r["pnl_flat_close"] for r in rows)
    win_no = sum(1 for r in rows if r["delta_no_minus_dip"] > 0)
    win_dip = sum(1 for r in rows if r["delta_no_minus_dip"] < 0)
    # 最大单笔差额（补仓更亏）
    worst_dip = min(rows, key=lambda r: r["delta_no_minus_dip"])
    best_dip = max(rows, key=lambda r: r["delta_no_minus_dip"])
    return {
        "ok": True,
        "label": label,
        "n_dip_events": n,
        "total_pnl_no_dip": round(sum_no, 2),
        "total_pnl_with_dip": round(sum_dip, 2),
        "total_pnl_flat_close": round(sum_flat, 2),
        "advantage_no_dip_vs_dip": round(sum_no - sum_dip, 2),
        "advantage_flat_vs_dip": round(sum_flat - sum_dip, 2),
        "pct_cases_no_dip_better": round(win_no / n * 100, 1),
        "pct_cases_dip_better": round(win_dip / n * 100, 1),
        "avg_ret_no_pct": round(sum(r["ret_no_pct"] for r in rows) / n, 3),
        "avg_ret_dip_pct": round(sum(r["ret_dip_pct"] for r in rows) / n, 3),
        "avg_ret_flat_pct": round(sum(r["ret_flat_pct"] for r in rows) / n, 3),
        "median_ret_no_pct": round(sorted(r["ret_no_pct"] for r in rows)[n // 2], 3),
        "median_ret_dip_pct": round(sorted(r["ret_dip_pct"] for r in rows)[n // 2], 3),
        "worst_dip_extra_loss_event": {
            "symbol": worst_dip.get("symbol"),
            "buy_date": worst_dip.get("buy_date"),
            "delta_no_minus_dip": worst_dip["delta_no_minus_dip"],
            "day_chg_open": worst_dip["day_chg_open"],
        },
        "best_no_dip_event": {
            "symbol": best_dip.get("symbol"),
            "buy_date": best_dip.get("buy_date"),
            "delta_no_minus_dip": best_dip["delta_no_minus_dip"],
        },
        "sample_head": rows[:8],
    }


def _kline_rule_sim(df, thr: float, max_syms: int, full: bool) -> dict:
    """向量化：全区间 / 大样本日K规则仿真。"""
    if df is None or df.empty:
        return {"ok": False, "reason": "no_kline"}
    import pandas as pd
    import numpy as np

    counts = df.groupby("symbol")["date"].nunique().sort_values(ascending=False)
    n_take = max_syms if full else min(80, max_syms)
    sample_syms = set(counts.head(n_take).index.tolist())
    sub = df[df["symbol"].isin(sample_syms)].copy()
    sub = sub.sort_values(["symbol", "date"])
    sub["buy_px"] = sub["close"]
    sub["next_open"] = sub.groupby("symbol")["open"].shift(-1)
    sub["next_close"] = sub.groupby("symbol")["close"].shift(-1)
    sub["next_date"] = sub.groupby("symbol")["date"].shift(-1)
    sub = sub.dropna(subset=["next_open", "next_close"])
    day_chg = sub["next_open"] / sub["buy_px"] - 1.0
    mask = day_chg <= -thr
    hit = sub.loc[mask].copy()
    if hit.empty:
        return {
            "ok": True,
            "label": "full_kline_rule" if full else "sample_kline_rule",
            "n_dip_events": 0,
            "n_symbols": len(sample_syms),
            "date_min": str(df["date"].min()),
            "date_max": str(df["date"].max()),
            "thr": thr,
        }

    buy_px = hit["buy_px"].to_numpy(dtype=float)
    open_px = hit["next_open"].to_numpy(dtype=float)
    close_px = hit["next_close"].to_numpy(dtype=float)
    half = QTY // 2
    rem = QTY - half
    init = buy_px * QTY
    pnl_no = (open_px - buy_px) * half + (close_px - buy_px) * rem
    pnl_dip = pnl_no + (close_px - open_px) * rem
    pnl_flat = (close_px - buy_px) * QTY
    delta = pnl_no - pnl_dip
    ret_no = pnl_no / init * 100.0
    ret_dip = pnl_dip / init * 100.0
    ret_flat = pnl_flat / init * 100.0

    rows = []
    # 只保留少量样本头，统计用向量
    head_n = min(8, len(hit))
    for i in range(head_n):
        rows.append(
            {
                "symbol": str(hit.iloc[i]["symbol"]),
                "buy_date": str(hit.iloc[i]["date"]),
                "sell_date": str(hit.iloc[i]["next_date"]),
                "day_chg_open": round(float(day_chg.loc[hit.index[i]]), 4),
                "pnl_no_dip": round(float(pnl_no[i]), 2),
                "pnl_with_dip": round(float(pnl_dip[i]), 2),
                "pnl_flat_close": round(float(pnl_flat[i]), 2),
                "ret_no_pct": round(float(ret_no[i]), 4),
                "ret_dip_pct": round(float(ret_dip[i]), 4),
                "ret_flat_pct": round(float(ret_flat[i]), 4),
                "delta_no_minus_dip": round(float(delta[i]), 2),
            }
        )

    n = int(len(hit))
    worst_i = int(np.argmin(delta))
    best_i = int(np.argmax(delta))
    return {
        "ok": True,
        "label": "full_kline_rule" if full else "sample_kline_rule",
        "n_dip_events": n,
        "n_symbols": len(sample_syms),
        "date_min": str(df["date"].min()),
        "date_max": str(df["date"].max()),
        "thr": thr,
        "total_pnl_no_dip": round(float(pnl_no.sum()), 2),
        "total_pnl_with_dip": round(float(pnl_dip.sum()), 2),
        "total_pnl_flat_close": round(float(pnl_flat.sum()), 2),
        "advantage_no_dip_vs_dip": round(float(delta.sum()), 2),
        "advantage_flat_vs_dip": round(float((pnl_flat - pnl_dip).sum()), 2),
        "pct_cases_no_dip_better": round(float((delta > 0).mean() * 100), 1),
        "pct_cases_dip_better": round(float((delta < 0).mean() * 100), 1),
        "avg_ret_no_pct": round(float(ret_no.mean()), 3),
        "avg_ret_dip_pct": round(float(ret_dip.mean()), 3),
        "avg_ret_flat_pct": round(float(ret_flat.mean()), 3),
        "median_ret_no_pct": round(float(np.median(ret_no)), 3),
        "median_ret_dip_pct": round(float(np.median(ret_dip)), 3),
        "worst_dip_extra_loss_event": {
            "symbol": str(hit.iloc[worst_i]["symbol"]),
            "buy_date": str(hit.iloc[worst_i]["date"]),
            "delta_no_minus_dip": round(float(delta[worst_i]), 2),
            "day_chg_open": round(float(day_chg.loc[hit.index[worst_i]]), 4),
        },
        "best_no_dip_event": {
            "symbol": str(hit.iloc[best_i]["symbol"]),
            "buy_date": str(hit.iloc[best_i]["date"]),
            "delta_no_minus_dip": round(float(delta[best_i]), 2),
        },
        "sample_head": rows,
    }


def _tradable_overlay(df, thr: float) -> dict:
    """用已有 tradable 回测入场，叠跌幅补仓路径。"""
    if df is None or df.empty:
        return {"ok": False, "reason": "no_kline"}
    src = None
    for p in TRADABLE_CANDIDATES:
        if p.exists():
            src = p
            break
    if not src:
        return {"ok": False, "reason": "no_tradable_backtest_json"}

    payload = json.loads(src.read_text(encoding="utf-8"))
    trades_map = payload.get("trades") or {}
    # 优先 A0_baseline（满仓可交易基线）
    arm = "A0_baseline" if "A0_baseline" in trades_map else next(iter(trades_map), None)
    if not arm:
        return {"ok": False, "reason": "empty_trades"}
    trades = [t for t in trades_map[arm] if not t.get("skipped")]
    by_sym = {sym: g.reset_index(drop=True) for sym, g in df.groupby("symbol")}

    rows = []
    skipped = defaultdict(int)
    for t in trades:
        sym = _bare(t.get("symbol"))
        buy_date = str(t.get("buy_date") or "")[:10]
        g = by_sym.get(sym)
        if g is None or g.empty:
            skipped["no_kline_sym"] += 1
            continue
        idx = g.index[g["date"] == buy_date]
        if len(idx) == 0:
            skipped["no_buy_date"] += 1
            continue
        bi = int(idx[0])
        if bi + 1 >= len(g):
            skipped["no_sell_day"] += 1
            continue
        d0 = g.iloc[bi]
        d1 = g.iloc[bi + 1]
        buy_px = float(t.get("buy") or d0["open"] or 0)
        # 昨收：买入日开盘的参照用买入日前收；若无则用 buy 日 close 作近似
        prev = float(g.iloc[bi - 1]["close"]) if bi > 0 else float(d0["close"])
        path = _paths_on_sell_day(buy_px, prev, float(d1["open"]), float(d1["close"]), thr)
        if not path:
            skipped["no_dip_trigger"] += 1
            continue
        path.update(
            {
                "symbol": sym,
                "buy_date": buy_date,
                "sell_date": str(d1["date"]),
                "orig_ret": t.get("ret"),
                "industry": t.get("industry_l1"),
            }
        )
        rows.append(path)

    out = _summarize_rows(rows, f"tradable_{arm}")
    out["source"] = str(src.relative_to(ROOT))
    out["arm"] = arm
    out["n_trades_total"] = len(trades)
    out["skip_reasons"] = dict(skipped)
    out["thr"] = thr
    out["window"] = (payload.get("config") or {})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--thr", type=float, default=DIP_THR)
    ap.add_argument("--full-kline", action="store_true", help="用更多标的跑全区间日K规则")
    ap.add_argument("--max-syms", type=int, default=800)
    args = ap.parse_args()

    paper_logs = _load_all_paper_logs()
    paper = _paper_counterfactual(paper_logs)
    kdf = _load_kline()
    tradable = _tradable_overlay(kdf, args.thr)
    ksim = _kline_rule_sim(kdf, args.thr, args.max_syms, full=True if args.full_kline else False)
    # 默认也跑一版「扩大样本」：至少 500 只、全日期
    ksim_large = _kline_rule_sim(kdf, args.thr, max(args.max_syms, 500), full=True)

    verdict = []
    if paper["n_cases"] > 0:
        verdict.append(
            "纸面(含bak合并) n={}: 无补仓合计差额 {:+.0f}".format(
                paper["n_cases"], paper["advantage_without_dip"]
            )
        )
    if tradable.get("n_dip_events", 0) > 0:
        verdict.append(
            "可交易历史 {}: 触发跌幅 {}/{} 笔；金额无补仓优势 {:+.0f}；"
            "等权均值 no={:.2f}% dip={:.2f}%；无补仓更好占比 {}%".format(
                tradable.get("arm"),
                tradable["n_dip_events"],
                tradable.get("n_trades_total"),
                tradable["advantage_no_dip_vs_dip"],
                tradable["avg_ret_no_pct"],
                tradable["avg_ret_dip_pct"],
                tradable["pct_cases_no_dip_better"],
            )
        )
    if ksim_large.get("n_dip_events", 0) > 0:
        verdict.append(
            "全市场日K扩大样 n={}（{}只）: 金额无补仓优势 {:+.0f}；"
            "等权均值 no={:.2f}% dip={:.2f}%；无补仓更好占比 {}%".format(
                ksim_large["n_dip_events"],
                ksim_large.get("n_symbols"),
                ksim_large["advantage_no_dip_vs_dip"],
                ksim_large["avg_ret_no_pct"],
                ksim_large["avg_ret_dip_pct"],
                ksim_large["pct_cases_no_dip_better"],
            )
        )
    verdict.append("生产默认仍关闭 ENABLE_DIP_SCALE_IN=0")

    out = {
        "asof": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data_sources": {
            "paper_files": "paper_trading.json + bak*",
            "tradable": tradable.get("source"),
            "kline": str(KLINE.relative_to(ROOT)) if KLINE.exists() else None,
            "kline_span": {
                "min": None if kdf is None else str(kdf["date"].min()),
                "max": None if kdf is None else str(kdf["date"].max()),
                "n_rows": 0 if kdf is None else int(len(kdf)),
                "n_syms": 0 if kdf is None else int(kdf["symbol"].nunique()),
            },
        },
        "paper_counterfactual": paper,
        "tradable_overlay": {k: v for k, v in tradable.items() if k != "sample_head"},
        "tradable_sample_head": tradable.get("sample_head"),
        "kline_rule_sim_default": {k: v for k, v in ksim.items() if k != "sample_head"},
        "kline_rule_sim_large": {k: v for k, v in ksim_large.items() if k != "sample_head"},
        "production_default": {
            "ENABLE_DIP_SCALE_IN": "0",
            "DIP_SCALE_MODE": "planned_only",
            "SCALE_IN_DIP_PCT": args.thr,
        },
        "verdict": verdict,
        "method_note": [
            "路径对比仅在「可卖日开盘相对昨收跌≥thr」子集上计算",
            "with_dip = 开盘减半 + 等量补仓 + 收盘全清（旧 equal_double）",
            "no_dip = 开盘减半 + 收盘清剩余（不加仓）",
            "flat = 可卖日收盘一次清",
            "金额单位：名义 10000 股/笔，跨票可加总比较尾部风险",
        ],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    day = datetime.now().strftime("%Y-%m-%d")
    path = OUT_DIR / f"dip_scale_backtest_{day}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {path}")
    print(json.dumps({"verdict": verdict, "tradable": out["tradable_overlay"], "kline_large": out["kline_rule_sim_large"], "paper": {k: paper[k] for k in paper if k != "cases"}}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
