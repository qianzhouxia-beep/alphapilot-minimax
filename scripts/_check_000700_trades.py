# -*- coding: utf-8 -*-
"""查 000700 完整交易历史 (B轨) (一次性)"""
import json, os

for f in [r"C:\alphapilot\b_trades_fullchain.json", r"C:\alphapilot\b_tdx_trades.json"]:
    if not os.path.exists(f): continue
    d = json.load(open(f, encoding='utf-8'))
    rows = d if isinstance(d, list) else []
    print("="*20, os.path.basename(f))
    for r in rows:
        if str(r.get('symbol','')).startswith('000700'):
            print(r)
