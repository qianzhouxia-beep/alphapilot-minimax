# -*- coding: utf-8 -*-
"""去重 vwap_broken 信号：每(日,股票)取尾盘最后一条 (一次性)"""
import json

sig = json.load(open(r"C:\Users\elvisq\Projects\alphapilot\scripts\_vwap_signals.json"))
# 去重: key=(date, symbol) -> 取 ret 最极端(最弱)一条? 实际都是同一点位,取第一条即可
dedup = {}
for s in sig:
    k = (s["date"], s["symbol"])
    dedup[k] = s  # 后覆盖,取最后一条(尾盘)
out = sorted(dedup.values(), key=lambda x: (x["date"], x["symbol"]))
print("unique signal-days:", len(out))
for s in out:
    print(" ", s["date"], s["symbol"], "px=%.2f vwap=%.2f ret=%.1f%%" % (s["px"], s["vwap"], s["ret"]))
json.dump(out, open(r"C:\Users\elvisq\Projects\alphapilot\scripts\_vwap_signals_dedup.json", "w"), ensure_ascii=False, indent=1)
