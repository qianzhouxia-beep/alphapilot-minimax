# -*- coding: utf-8 -*-
"""查看 B轨 全部交易记录 (一次性)"""
import json
trades = json.load(open(r"C:\alphapilot\b_trades_fullchain.json"))
print("total:", len(trades))
for t in trades:
    print(t)
