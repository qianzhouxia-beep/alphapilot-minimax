#!/usr/bin/env python3
import json
from pathlib import Path
import sys
sys.path.insert(0, "/home/ubuntu/alphapilot")
from enriched_data import get_quotes_batch

pt = json.loads(Path("/home/ubuntu/alphapilot/data/paper_trading.json").read_text(encoding="utf-8"))
acc = pt.get("account") or {}
print("ACCOUNT:", json.dumps(acc, ensure_ascii=False, indent=2))
print("initial_capital", pt.get("initial_capital"))
print("injections", pt.get("capital_injections"))

syms = []
rows = []
for s in pt.get("strategies") or []:
    for p in s.get("positions") or []:
        sym = str(p.get("symbol") or "")[-6:]
        syms.append(sym)
        rows.append((s.get("id"), p))
q = get_quotes_batch(syms) or {}
mv = 0.0
cost = 0.0
print("POSITIONS:")
for sid, p in rows:
    sym = str(p.get("symbol") or "")[-6:]
    name = p.get("name")
    qq = q.get(sym) or {}
    live = float(qq.get("price") or p.get("current_price") or p.get("buy_price") or 0)
    buy = float(p.get("buy_price") or 0)
    qty = float(p.get("quantity") or 0)
    mv += live * qty
    cost += buy * qty
    pnl = (live / buy - 1) * 100 if buy else 0
    print(sid, sym, name, "qty", qty, "buy", buy, "live", live, "pnl%", round(pnl, 2), "mv", round(live * qty, 2))

cash = float(acc.get("cash") or 0)
equity = cash + mv
init = float(pt.get("initial_capital") or 0)
inj = 0.0
for x in pt.get("capital_injections") or []:
    if isinstance(x, dict):
        inj += float(x.get("amount") or x.get("cash") or 0)
    else:
        try:
            inj += float(x)
        except Exception:
            pass
print("cash", cash)
print("mv", round(mv, 2), "cost_basis", round(cost, 2), "float_pnl", round(mv - cost, 2))
print("equity", round(equity, 2))
print("init+inj", init + inj)
if init + inj:
    print("true_cum_pct", round((equity / (init + inj) - 1) * 100, 2))
print("stored total_pnl_pct", acc.get("total_pnl_pct"), "total_assets", acc.get("total_assets"), "float_pnl", acc.get("float_pnl"))

# realized from sells
realized = 0.0
for t in pt.get("trade_log") or []:
    if t.get("pnl") is not None:
        try:
            realized += float(t.get("pnl") or 0)
        except Exception:
            pass
print("sum trade_log.pnl", round(realized, 2))
# show sells with pnl
n = 0
for t in pt.get("trade_log") or []:
    if t.get("pnl") is not None:
        n += 1
        if n <= 15:
            print(" pnlrow", t.get("time"), t.get("action"), t.get("symbol"), t.get("pnl"), t.get("amount"))
print("pnl rows", n)
