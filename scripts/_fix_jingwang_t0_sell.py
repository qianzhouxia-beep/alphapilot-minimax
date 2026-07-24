#!/usr/bin/env python3
"""撤销今日误卖的 T+0 景旺电子，恢复持仓。"""
import json
from pathlib import Path

PT = Path("/home/ubuntu/alphapilot/data/paper_trading.json")
d = json.loads(PT.read_text(encoding="utf-8"))
today = "2026-07-20"
restored = False
new_log = []
for t in d.get("trade_log") or []:
    if (
        t.get("symbol") == "603228"
        and str(t.get("time", "")).startswith(today)
        and "卖出" in str(t.get("action", ""))
    ):
        # 跳过这笔错误卖出
        print("drop bad sell", t)
        continue
    new_log.append(t)
d["trade_log"] = new_log

# 若仓位已无，从卖出记录反推恢复（用最后一笔被删卖单的信息）
has = False
for s in d.get("strategies") or []:
    for p in s.get("positions") or []:
        if p.get("symbol") == "603228":
            has = True
# 从日志找今日买入
buy = None
for t in reversed(new_log):
    if t.get("symbol") == "603228" and str(t.get("action", "")).startswith("买入"):
        buy = t
        break
if not has and buy:
    strat_id = buy.get("strategy_id") or "v19_daily"
    qty = int(buy.get("quantity") or 0)
    px = float(buy.get("price") or 0)
    pos = {
        "symbol": "603228",
        "name": buy.get("name") or "景旺电子",
        "entry_price": px,
        "buy_price": px,
        "current_price": px,
        "quantity": qty,
        "planned_quantity": int(buy.get("planned_quantity") or qty),
        "initial_quantity": qty,
        "pnl_pct": 0,
        "pnl_amount": 0,
        "stop_loss": round(px * 0.94, 2),
        "stop_pct": -6.0,
        "trailing_high": px,
        "days_held": 0,
        "trading_days_held": 0,
        "last_day_check": today,
        "strategy_id": strat_id,
        "buy_date": today,
        "protocol": "tradable_top2",
        "position_exposure": 0.25,
        "scale_in_pending": "首批" in str(buy.get("action", "")),
        "scale_in_done": "首批" not in str(buy.get("action", "")),
        "trail_armed": False,
        "peel_count": 0,
        "awaiting_new_high": False,
        "peel_peak_snapshot": px,
        "_restored_from_t0_bug": True,
    }
    for s in d.get("strategies") or []:
        if s.get("id") == strat_id:
            s.setdefault("positions", []).append(pos)
            restored = True
            print("restored pos", pos)
            break
    if not restored:
        # fallback append to v19
        for s in d.get("strategies") or []:
            if s.get("id") == "v19_daily":
                s.setdefault("positions", []).append(pos)
                restored = True
                break

d["updated_at"] = "2026-07-20 14:32"
PT.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print("done restored=", restored, "has_buy=", bool(buy))
