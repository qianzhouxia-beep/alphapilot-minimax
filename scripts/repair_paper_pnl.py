#!/usr/bin/env python3
"""Repair paper_trading account cumulative PnL to equity / initial_capital - 1."""
import json
import shutil
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path

p = Path("/home/ubuntu/alphapilot/data/paper_trading.json")
bak = p.with_suffix(
    p.suffix + ".bak_pnlfix_" + datetime.now().strftime("%Y%m%d_%H%M%S")
)
shutil.copy2(p, bak)
pt = json.loads(p.read_text(encoding="utf-8"))
acct = pt.get("account") or {}
initial = float(acct.get("initial_capital") or pt.get("initial_capital") or 2e6)
cash = float(acct.get("cash") or 0)

total_mv = total_cost = 0.0
for s in pt.get("strategies") or []:
    for pos in s.get("positions") or []:
        sym = str(pos.get("symbol") or "")
        qty = float(pos.get("quantity") or 0)
        cost = float(pos.get("buy_price") or 0)
        total_cost += qty * cost
        lp = cost
        if sym:
            prefix = "sh" if sym.startswith("6") else "sz"
            try:
                r = urllib.request.urlopen(
                    "https://qt.gtimg.cn/q=" + prefix + sym, timeout=5
                )
                vals = r.read().decode("gbk").split('"')[1].split("~")
                if len(vals) > 3:
                    x = float(vals[3]) or float(vals[4])
                    if x > 0:
                        lp = x
                        pos["current_price"] = round(lp, 2)
                        pos["pnl_pct"] = (
                            round((lp - cost) / cost * 100, 2) if cost else 0
                        )
                        pos["pnl_amount"] = round((lp - cost) * qty, 2)
            except Exception:
                pass
        total_mv += qty * lp

settled = bought = sold = 0.0
for t in pt.get("trade_log") or []:
    a = t.get("action") or ""
    amt = float(t.get("amount") or 0)
    pn = float(t.get("pnl") or 0)
    if a.startswith("买入") or a == "买入":
        bought += amt
    elif "卖出" in a:
        sold += amt
        settled += pn

fp = total_mv - total_cost
equity = cash + total_mv
pnl = equity - initial
pct = pnl / initial * 100 if initial else 0.0

acct.update(
    {
        "market_value": round(total_mv, 2),
        "cash": round(cash, 2),
        "total_assets": round(equity, 2),
        "total_pnl_amount": round(pnl, 2),
        "total_pnl_pct": round(pct, 2),
        "asset_pnl_pct": round(pct, 2),
        "settled_pnl": round(settled, 2),
        "float_pnl": round(fp, 2),
        "total_bought": round(bought, 2),
        "total_sold": round(sold, 2),
        "used_capital": round(total_cost, 2),
        "initial_capital": initial,
    }
)
pt["account"] = acct
pt["initial_capital"] = initial
pt["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
pt["note_pnl_fix"] = (
    "2026-07-23: total_pnl = equity/initial - 1; refresh float from live marks"
)
p.write_text(json.dumps(pt, ensure_ascii=False, indent=2), encoding="utf-8")
print("bak", bak)
print(
    "equity",
    round(equity, 2),
    "pnl",
    round(pnl, 2),
    "pct",
    round(pct, 2),
    "float",
    round(fp, 2),
    "settled",
    round(settled, 2),
)

# soft-restart common api unit names if active
for unit in ("alphapilot-api", "alphapilot", "api_server"):
    r = subprocess.run(
        ["systemctl", "is-active", unit], capture_output=True, text=True
    )
    status = (r.stdout or r.stderr or "").strip()
    print(unit, status)
    if status == "active":
        subprocess.run(["sudo", "systemctl", "restart", unit], check=False)
        print("restarted", unit)
