# -*- coding: utf-8 -*-
"""读 QMT 实盘部署策略的关键函数 (一次性, 只读)"""
import re

p = r"D:\国金证券QMT交易端\python\AP全链路交易_TRACK_A.py"
src = open(p, "r", encoding="utf-8", errors="replace").read()
print("len:", len(src))

# 找版本号
for m in re.finditer(r"v2\.\d+[-\w]*|VERSION\s*=\s*[\"'][^\"']+", src):
    print("VER:", m.group(0))
    if m.start() > 200000: break

# 关键函数位置
for fn in ["_get_m5_bars", "_get_quote", "_get_last", "_get_turnover",
           "_get_prev_close", "_get_active_buy_ratio", "_p2_decide",
           "_is_sweet_zone", "_order_cands_by_sweet"]:
    idx = src.find("def " + fn)
    print(fn, "->", idx)

def dump(fn, n=60):
    i = src.find("def " + fn)
    if i < 0:
        print("MISSING", fn); return
    print("\n" + "="*30, fn)
    print(src[i:i+n*200].split("\n\n")[0][:4000] if False else src[i:i+6000])

dump("_get_m5_bars", 40)
dump("_get_turnover", 30)
