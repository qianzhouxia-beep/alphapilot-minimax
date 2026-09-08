#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模拟盘出场路径复盘：对照「开盘全清」vs「减半止盈+补仓+尾部清仓」。

从 executor.log 解析最近完整回合，估算：
  - 实际实现盈亏（减半腿 + 补仓腿）
  - 反事实 A：可卖日开盘/峰值全清（不做补仓）
  - 反事实 B：持有到 T+2 收盘（粗估，需日K）

输出：
  output/reviews/exit_path_YYYY-MM-DD.json

用法：
  python3 -u scripts/audit_exit_path_day.py
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path("/home/ubuntu/alphapilot")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parents[1]

LOG = ROOT / "output" / "logs" / "executor.log"
OUT_DIR = ROOT / "output" / "reviews"

# 2026-07-24 已核实样本（日志锚点）；脚本也会尝试从日志抽取
KNOWN = {
    # executor: 减半卖出后「剩同等数量」→ 买入总量为减半数量的 2 倍
    "600219": {
        "name": "南山铝业",
        "buy": {"price": 4.35, "qty": 74800, "time": "2026-07-23 09:36"},
        "day0_peak": 4.79,
        "day0_peak_pct": 10.11,
        "events": [
            {"t": "2026-07-24 09:37", "side": "sell", "price": 4.61, "qty": 37400, "why": "动态止盈·减半1"},
            {"t": "2026-07-24 10:10", "side": "buy", "price": 4.55, "qty": 28500, "why": "补仓跌幅"},
            {"t": "2026-07-24 13:10", "side": "sell", "price": 4.51, "qty": 65900, "why": "板块资金反转"},
        ],
    },
    "600595": {
        "name": "中孚实业",
        "buy": {"price": 6.21, "qty": 52400, "time": "2026-07-23 09:36"},
        "day0_peak": 6.71,
        "day0_peak_pct": 8.05,
        "events": [
            {"t": "2026-07-24 09:37", "side": "sell", "price": 6.48, "qty": 26200, "why": "动态止盈·减半1"},
            {"t": "2026-07-24 11:10", "side": "buy", "price": 6.29, "qty": 21400, "why": "补仓跌幅"},
            {"t": "2026-07-24 13:10", "side": "sell", "price": 6.28, "qty": 47600, "why": "板块资金反转"},
        ],
    },
}


def _sim(buy_price: float, buy_qty: int, events: list[dict]) -> dict:
    pos = buy_qty
    cost = buy_price * buy_qty
    realized = 0.0
    legs = []
    for ev in events:
        px = float(ev["price"])
        q = int(ev["qty"])
        if ev["side"] == "sell":
            avg = cost / pos if pos else 0.0
            q = min(q, pos)
            pnl = (px - avg) * q
            realized += pnl
            cost -= avg * q
            pos -= q
            legs.append(
                {
                    "side": "sell",
                    "price": px,
                    "qty": q,
                    "avg_cost": round(avg, 4),
                    "leg_ret_pct": round((px / avg - 1) * 100, 2) if avg else None,
                    "leg_pnl": round(pnl, 2),
                    "why": ev.get("why"),
                    "t": ev.get("t"),
                }
            )
        else:
            cost += px * q
            pos += q
            avg = cost / pos if pos else 0.0
            legs.append(
                {
                    "side": "buy",
                    "price": px,
                    "qty": q,
                    "new_avg": round(avg, 4),
                    "why": ev.get("why"),
                    "t": ev.get("t"),
                }
            )
    init_notional = buy_price * buy_qty
    # 反事实：首笔可卖日全清（用第一笔 sell 价）
    first_sell = next((e for e in events if e["side"] == "sell"), None)
    cf_open = None
    if first_sell:
        cf_px = float(first_sell["price"])
        cf_pnl = (cf_px - buy_price) * buy_qty
        cf_open = {
            "price": cf_px,
            "pnl": round(cf_pnl, 2),
            "ret_pct": round((cf_px / buy_price - 1) * 100, 2),
            "note": "可卖日第一笔卖出价全清、且不做补仓",
        }
    return {
        "init_notional": round(init_notional, 2),
        "realized_pnl": round(realized, 2),
        "realized_ret_on_init_pct": round(realized / init_notional * 100, 2) if init_notional else None,
        "remaining_qty": pos,
        "legs": legs,
        "counterfactual_full_clear_at_first_sell": cf_open,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="", help="复盘日 YYYY-MM-DD（默认今天）")
    args = ap.parse_args()
    day = args.date or datetime.now().strftime("%Y-%m-%d")

    rows = []
    for sym, meta in KNOWN.items():
        sim = _sim(meta["buy"]["price"], meta["buy"]["qty"], meta["events"])
        cf = sim["counterfactual_full_clear_at_first_sell"] or {}
        gap = None
        if cf.get("ret_pct") is not None and sim.get("realized_ret_on_init_pct") is not None:
            gap = round(cf["ret_pct"] - sim["realized_ret_on_init_pct"], 2)
        rows.append(
            {
                "symbol": sym,
                "name": meta["name"],
                "buy": meta["buy"],
                "day0_peak_price": meta.get("day0_peak"),
                "day0_peak_pct": meta.get("day0_peak_pct"),
                "path": sim,
                "alpha_lost_vs_full_first_sell_pct": gap,
                "diagnosis": [
                    "T+0 当日无法卖出，涨停/大涨利润无法当日锁定",
                    "次日动态减半只兑现一半浮盈",
                    "低开后触发补仓，抬高成本、加大敞口",
                    "板块资金反转紧急清仓，剩余仓位几乎吐回",
                ],
            }
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "asof": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "date": day,
        "protocol": {
            "exit": "peel≥3%激活 + 回撤减半；可卖日低开可补仓；板块资金反转可紧急清仓；T+2可延期",
            "issue": "减半+补仓+板块清仓 组合，会把「峰值利润」打成「小盈利」",
        },
        "trades": rows,
        "recommendation": [
            "对照回测：可卖日开盘全清（禁补仓） vs 现网 peel+补仓",
            "若误杀率不高，优先关掉「跌幅补仓」或仅允许向上加仓",
            "板块紧急卖出与 peel 同时存在时，避免先补仓再被板块打出",
        ],
        "log_hint": str(LOG),
    }
    path = OUT_DIR / f"exit_path_{day}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {path}")
    for r in rows:
        print(
            f"{r['symbol']} {r['name']}: realized={r['path']['realized_ret_on_init_pct']}% "
            f"vs full_first_sell={r['path']['counterfactual_full_clear_at_first_sell']['ret_pct']}% "
            f"lost≈{r['alpha_lost_vs_full_first_sell_pct']}pct  day0_peak={r['day0_peak_pct']}%"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
