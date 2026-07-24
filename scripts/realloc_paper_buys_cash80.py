#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将南山铝业/中孚实业补录仓位改为：总现金 80% 等权分配，09:36 价。"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path("/home/ubuntu/alphapilot")
sys.path.insert(0, str(ROOT))
PT = ROOT / "data" / "paper_trading.json"
FILLS = {"600219": ("南山铝业", 4.35), "600595": ("中孚实业", 6.21)}


def round_lot(n: float) -> int:
    return int(n // 100) * 100


def main() -> None:
    bak = PT.with_name(
        "paper_trading.json.bak_realloc80_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    shutil.copy2(PT, bak)
    pt = json.loads(PT.read_text(encoding="utf-8"))
    strat = next(s for s in pt["strategies"] if s.get("id") == "v19_daily")

    remain = []
    refund = 0.0
    for p in strat.get("positions") or []:
        sym = str(p.get("symbol") or "")[-6:]
        if sym in FILLS:
            cost = float(p.get("buy_price") or 0) * float(p.get("quantity") or 0)
            refund += cost
            print("remove", sym, "refund", round(cost, 2))
        else:
            remain.append(p)
    strat["positions"] = remain
    pt["account"]["cash"] = round(float(pt["account"]["cash"]) + refund, 2)

    cash = float(pt["account"]["cash"])
    budget = cash * 0.80
    per = budget / 2
    print("cash", cash, "budget80%", round(budget, 2), "per", round(per, 2))

    try:
        from trade_executor import STOP_LADDERS

        init_stop = STOP_LADDERS[0][1]
    except Exception:
        init_stop = -0.05

    today = datetime.now().strftime("%Y-%m-%d")
    new_log = []
    for row in pt.get("trade_log") or []:
        sym = str(row.get("symbol") or "")[-6:]
        if row.get("backfill") and sym in FILLS:
            continue
        if str(row.get("entry_reason") or "").startswith("backfill_fund_top2_0936") and sym in FILLS:
            continue
        new_log.append(row)

    for sym, (name, fill) in FILLS.items():
        qty = round_lot(per / fill)
        if qty < 100:
            raise SystemExit(f"too small {sym}")
        cost = qty * fill
        if cost > float(pt["account"]["cash"]) + 1:
            qty = round_lot(float(pt["account"]["cash"]) / fill)
            cost = qty * fill
        pt["account"]["cash"] = round(float(pt["account"]["cash"]) - cost, 2)
        strat.setdefault("positions", []).append(
            {
                "symbol": sym,
                "name": name,
                "entry_price": round(fill, 2),
                "buy_price": round(fill, 2),
                "current_price": round(fill, 2),
                "quantity": qty,
                "planned_quantity": qty,
                "initial_quantity": qty,
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
                "position_exposure": 0.8,
                "protocol": "cash80_equal",
                "entry_weight": 0.5,
                "entry_reason": "backfill_fund_top2_0936_cash80",
                "note": "补录：总现金80%等权，09:36价",
            }
        )
        new_log.append(
            {
                "time": f"{today} 09:36",
                "symbol": sym,
                "name": name,
                "action": "买入",
                "price": round(fill, 2),
                "quantity": qty,
                "amount": round(cost, 2),
                "strategy_id": "v19_daily",
                "position_exposure": 0.8,
                "protocol": "cash80_equal",
                "planned_quantity": qty,
                "entry_weight": 0.5,
                "entry_reason": "backfill_fund_top2_0936_cash80",
                "backfill": True,
            }
        )
        print(f"{sym} {name} x{qty} @{fill} = {cost:.0f}")

    strat["used"] = round(
        sum(
            float(p.get("buy_price") or 0) * float(p.get("quantity") or 0)
            for p in strat.get("positions") or []
        ),
        2,
    )
    pt["trade_log"] = new_log
    pt["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    pt["note_backfill_0936"] = {
        "alloc": "cash_80pct_equal_2",
        "fills": {k: v[1] for k, v in FILLS.items()},
        "cash_after": pt["account"]["cash"],
    }
    PT.write_text(json.dumps(pt, ensure_ascii=False, indent=2), encoding="utf-8")
    print("cash_left", pt["account"]["cash"], "daily_used", strat["used"])
    print("backup", bak)


if __name__ == "__main__":
    main()
