#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补录纸面买入：南山铝业/中孚实业 @ 今日 09:36 分时价。

用途：资金门改版后重跑的 Top2，按 09:36 价补进 v19_daily。
"""
from __future__ import annotations

import json
import shutil
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path("/home/ubuntu/alphapilot")
sys.path.insert(0, str(ROOT))
PT = ROOT / "data" / "paper_trading.json"
FILLS = {
    "600219": {"name": "南山铝业", "price": None},
    "600595": {"name": "中孚实业", "price": None},
}


def minute_px(code: str, hhmm: str = "0936") -> float:
    url = f"http://web.ifzq.gtimg.cn/appstock/app/minute/query?code={code}"
    raw = urllib.request.urlopen(url, timeout=15).read().decode("utf-8", "ignore")
    d = json.loads(raw)
    data = ((d.get("data") or {}).get(code) or {}).get("data") or {}
    mins = data.get("data") or []
    for row in mins:
        parts = str(row).split()
        if parts and parts[0] == hhmm:
            return float(parts[1])
    raise RuntimeError(f"no {hhmm} bar for {code}")


def round_lot(n: float) -> int:
    return int(n // 100) * 100


def main() -> None:
    FILLS["600219"]["price"] = minute_px("sh600219", "0936")
    FILLS["600595"]["price"] = minute_px("sh600595", "0936")
    print("fills@", {k: v["price"] for k, v in FILLS.items()})

    from order_tickets import (
        approve_tickets,
        load_tickets,
        reject_tickets,
        save_tickets,
        mark_ticket_status,
    )

    doc = load_tickets(user_id="owner")
    reject_ids = []
    approve_ids = []
    id_by_sym = {}
    for t in doc.get("tickets") or []:
        if t.get("status") != "pending_review":
            continue
        sym = str(t.get("symbol") or "")[-6:]
        if sym in ("300768", "688363"):
            reject_ids.append(t["id"])
        if sym in FILLS:
            approve_ids.append(t["id"])
            id_by_sym[sym] = t["id"]

    if reject_ids:
        reject_tickets(reject_ids, user_id="owner", reason="改跟资金门，撤消模型 Top2")
        print("rejected", reject_ids)
    if approve_ids:
        approve_tickets(approve_ids, user_id="owner")
        print("approved", approve_ids)

    bak = PT.with_name(
        f"paper_trading.json.bak_backfill0936_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    shutil.copy2(PT, bak)
    print("backup", bak)

    pt = json.loads(PT.read_text(encoding="utf-8"))
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    expo = float(pt.get("position_exposure") or 0.5)
    cash = float(pt["account"].get("cash") or 0)
    strat = None
    for s in pt.get("strategies") or []:
        if s.get("id") == "v19_daily":
            strat = s
            break
    if strat is None:
        raise SystemExit("no v19_daily")

    held = {str(p.get("symbol"))[-6:] for p in (strat.get("positions") or [])}
    # 等权 2 只，日频 expo 缩放，首批 50%（与 trade_executor 一致）
    n = len(FILLS)
    pool_cash = cash * expo
    per = pool_cash / n if n else 0
    scale = 0.5

    try:
        from trade_executor import STOP_LADDERS

        init_stop = STOP_LADDERS[0][1]
    except Exception:
        init_stop = -0.05

    for sym, meta in FILLS.items():
        if sym in held:
            print("skip already held", sym)
            continue
        fill = float(meta["price"])
        name = meta["name"]
        planned = round_lot(per / fill)
        first = round_lot(planned * scale)
        if planned < 200:
            first = planned
        if first < 100:
            first = 100 if planned >= 100 else planned
        if first < 100:
            print("skip too small", sym, fill)
            continue
        cost = first * fill
        if cost > float(pt["account"]["cash"]) + 1:
            afford = round_lot(float(pt["account"]["cash"]) / fill)
            if afford < 100:
                print("skip no cash", sym)
                continue
            first = afford
            planned = afford
            cost = first * fill

        pt["account"]["cash"] = round(float(pt["account"]["cash"]) - cost, 2)
        pos = {
            "symbol": sym,
            "name": name,
            "entry_price": round(fill, 2),
            "buy_price": round(fill, 2),
            "current_price": round(fill, 2),
            "quantity": first,
            "planned_quantity": planned,
            "initial_quantity": first,
            "pnl_pct": 0,
            "pnl_amount": 0,
            "stop_loss": round(fill * (1 + init_stop), 2),
            "stop_pct": round(init_stop * 100, 1),
            "trailing_high": round(fill, 2),
            "days_held": 0,
            "trading_days_held": 0,
            "last_day_check": today,
            "strategy_id": "v19_daily",
            "buy_date": today,
            "entry_time": f"{today} 09:36",
            "position_exposure": expo,
            "protocol": "gap_soft",
            "entry_weight": round(1.0 / n, 4),
            "entry_reason": "backfill_fund_top2_0936",
            "ticket_id": id_by_sym.get(sym),
            "note": "人工补录：资金门 Top2 @09:36 分时价",
        }
        strat.setdefault("positions", []).append(pos)
        strat["used"] = round(float(strat.get("used") or 0) + cost, 2)
        pt.setdefault("trade_log", []).append(
            {
                "time": f"{today} 09:36",
                "symbol": sym,
                "name": name,
                "action": "买入(首批50%)" if first < planned else "买入",
                "price": round(fill, 2),
                "quantity": first,
                "amount": round(cost, 2),
                "strategy_id": "v19_daily",
                "position_exposure": expo,
                "protocol": "gap_soft",
                "planned_quantity": planned,
                "entry_weight": round(1.0 / n, 4),
                "entry_reason": "backfill_fund_top2_0936",
                "backfill": True,
            }
        )
        tid = id_by_sym.get(sym)
        if tid:
            mark_ticket_status(
                tid,
                "filled",
                user_id="owner",
                extra={
                    "fill_price": fill,
                    "fill_qty": first,
                    "exec_channel": "paper_backfill_0936",
                    "filled_at": f"{today} 09:36:00",
                },
            )
        print(f"BOUGHT {sym} {name} x{first} @{fill:.2f} = {cost:.0f}")

    # 清掉日频 signals，避免执行器再买一遍
    strat["signals"] = []
    pt["updated_at"] = now
    pt["note_backfill_0936"] = {
        "at": now,
        "fills": {k: v["price"] for k, v in FILLS.items()},
        "source": "tencent_minute_0936",
    }
    PT.write_text(json.dumps(pt, ensure_ascii=False, indent=2), encoding="utf-8")
    print("cash_left", pt["account"]["cash"])
    print("saved", PT)


if __name__ == "__main__":
    main()
