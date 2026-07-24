#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模拟盘可交易协议复盘：信号 → 成交 → 持有 → 卖出。

对照协议：
  - Top2 日频（v19_daily）
  - 开盘涨停跳过（若 trade_log 有 skip 记录）
  - position_exposure 缩放
  - 目标持有至 T+2（允许止损/止盈提前退出）

输出: output/paper_tradable_audit.json
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PT_PATH = ROOT / "data" / "paper_trading.json"
REC_PATH = ROOT / "output" / "daily_recommend.json"
OUT_PATH = ROOT / "output" / "paper_tradable_audit.json"

COST_RT = 0.0015
HIT_THR = 0.03
TARGET_STRATEGY = "v19_daily"


def _day(s: str) -> str:
    return (s or "")[:10]


def pair_trades(log: list[dict], strategy_id: str):
    """FIFO match 买入/卖出 for one strategy. Returns (closed, open_from_log)."""
    opens = defaultdict(list)
    closed = []
    for t in log:
        if t.get("strategy_id") and t.get("strategy_id") != strategy_id:
            continue
        # allow missing strategy_id on old rows if action looks like daily
        action = t.get("action") or ""
        sym = t.get("symbol") or ""
        if not sym:
            continue
        if action == "买入":
            opens[sym].append(t)
        elif "卖出" in action:
            if not opens[sym]:
                continue
            buy = opens[sym].pop(0)
            bp = float(buy.get("price") or 0)
            sp = float(t.get("price") or 0)
            qty = int(t.get("quantity") or buy.get("quantity") or 0)
            gross = (sp / bp - 1.0) if bp > 0 else 0.0
            net = gross - COST_RT
            closed.append(
                {
                    "symbol": sym,
                    "name": t.get("name") or buy.get("name"),
                    "buy_time": buy.get("time"),
                    "sell_time": t.get("time"),
                    "buy_date": _day(buy.get("time") or ""),
                    "sell_date": _day(t.get("time") or ""),
                    "buy_price": bp,
                    "sell_price": sp,
                    "quantity": qty,
                    "gross_ret": round(gross, 6),
                    "net_ret": round(net, 6),
                    "pnl": t.get("pnl"),
                    "exit_reason": action,
                    "hit_3pct": net >= HIT_THR,
                    "win": net > 0,
                    "calendar_hold_days": (
                        (
                            datetime.strptime(_day(t.get("time") or ""), "%Y-%m-%d")
                            - datetime.strptime(_day(buy.get("time") or ""), "%Y-%m-%d")
                        ).days
                        if _day(t.get("time")) and _day(buy.get("time"))
                        else None
                    ),
                }
            )
    open_pos = []
    for sym, arr in opens.items():
        for buy in arr:
            open_pos.append(
                {
                    "symbol": sym,
                    "name": buy.get("name"),
                    "buy_time": buy.get("time"),
                    "buy_price": buy.get("price"),
                    "quantity": buy.get("quantity"),
                }
            )
    return closed, open_pos


def main() -> int:
    if not PT_PATH.exists():
        raise SystemExit(f"missing {PT_PATH}")

    pt = json.loads(PT_PATH.read_text(encoding="utf-8"))
    expo = pt.get("position_exposure")
    expo_src = "paper_trading"
    if expo is None and REC_PATH.exists():
        rec = json.loads(REC_PATH.read_text(encoding="utf-8"))
        expo = rec.get("position_exposure")
        expo_src = "daily_recommend"

    log = pt.get("trade_log") or []
    skips = [t for t in log if "跳过" in str(t.get("action") or "") or t.get("skip")]
    closed, open_pos = pair_trades(log, TARGET_STRATEGY)

    # also count buys tagged v19 or all buys if strategy missing
    buys = [t for t in log if t.get("action") == "买入" and (not t.get("strategy_id") or t.get("strategy_id") == TARGET_STRATEGY)]
    sells = [t for t in log if "卖出" in str(t.get("action") or "") and (not t.get("strategy_id") or t.get("strategy_id") == TARGET_STRATEGY)]

    n_closed = len(closed)
    hit = sum(1 for t in closed if t.get("hit_3pct")) / n_closed if n_closed else None
    win = sum(1 for t in closed if t.get("win")) / n_closed if n_closed else None
    avg_net = sum(float(t["net_ret"]) for t in closed) / n_closed if n_closed else None

    # protocol hold preference: calendar days around 2 (trading days ~1 full day)
    hold_ok = None
    if n_closed:
        holds = [t["calendar_hold_days"] for t in closed if t.get("calendar_hold_days") is not None]
        if holds:
            # T+2 close ≈ 2 calendar days on consecutive sessions; allow 1-4 for weekends
            hold_ok = sum(1 for h in holds if 1 <= h <= 4) / len(holds)

    strat = next((s for s in pt.get("strategies", []) if s.get("id") == TARGET_STRATEGY), None)
    pending_signals = (strat or {}).get("signals") or []
    positions = (strat or {}).get("positions") or []

    report = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "strategy_id": TARGET_STRATEGY,
        "position_exposure_today": expo,
        "position_exposure_source": expo_src,
        "protocol": pt.get("protocol"),
        "empty_reason": pt.get("empty_reason"),
        "account": pt.get("account"),
        "counts": {
            "buys": len(buys),
            "sells": len(sells),
            "closed_rounds": n_closed,
            "open_from_log": len(open_pos),
            "open_positions": len(positions),
            "pending_signals": len(pending_signals),
            "skip_records": len(skips),
        },
        "kpi": {
            "win_rate": win,
            "hit_3pct_rate": hit,
            "avg_net_return": avg_net,
            "protocol_hold_share_1to4d": hold_ok,
        },
        "protocol_checklist": {
            "top2_signals": len(pending_signals) <= 2,
            "exposure_read": expo is not None,
            "exposure_zero_should_block_buys": (expo == 0),
            "has_limit_skip_logging": any(
                "涨停" in str(t.get("action") or "") or t.get("skip") == "open_limit" for t in log
            ),
            "t2_force_exit_seen": any("T+2" in str(t.get("action") or "") for t in log),
        },
        "closed_trades": closed[-50:],
        "open_positions": [
            {
                "symbol": p.get("symbol"),
                "name": p.get("name"),
                "buy_date": p.get("buy_date"),
                "buy_price": p.get("buy_price"),
                "current_price": p.get("current_price"),
                "pnl_pct": p.get("pnl_pct"),
                "trading_days_held": p.get("trading_days_held", p.get("days_held")),
                "protocol": p.get("protocol"),
            }
            for p in positions
        ],
        "pending_signals": [
            {"symbol": s.get("symbol"), "name": s.get("name"), "score": s.get("score"), "price": s.get("price")}
            for s in pending_signals
        ],
        "notes": [
            "hit≥3% 按双边 15bp 净收益计",
            "日历持有天数≠交易日；周末/节假日会使日历天数变长",
            "对齐后新成交应出现 action 含 T+2 / 开盘涨停跳过",
        ],
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("======== Paper Tradable Audit ========")
    print(f"buys={len(buys)} sells={len(sells)} closed={n_closed} open_pos={len(positions)}")
    if n_closed:
        print(
            f"win={win*100:.1f}% hit3%={hit*100:.1f}% avg_net={avg_net*100:.2f}% "
            f"hold1-4d={None if hold_ok is None else round(hold_ok*100,1)}%"
        )
    print("exposure_today=", expo)
    print("checklist=", report["protocol_checklist"])
    print("saved", OUT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
