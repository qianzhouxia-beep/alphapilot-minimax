# -*- coding: utf-8 -*-
"""查 B轨模拟 300191 / 各信号股票的完整交易记录 (一次性)"""
import json

trades = json.load(open(r"C:\alphapilot\b_trades_fullchain.json"))
print("trades total:", len(trades))
print("keys:", list(trades[0].keys()) if trades else None)
targets = {"300191", "000524", "603236", "002839", "002667", "000700", "002292", "003032"}
for t in trades:
    sym = str(t.get("symbol", ""))
    if any(sym.startswith(x) for x in targets):
        print(json.dumps(t, ensure_ascii=False, default=str))
