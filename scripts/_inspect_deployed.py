# -*- coding: utf-8 -*-
"""检查 QMT 实盘部署文件内容结构 (一次性)"""
import re
p = r"D:\国金证券QMT交易端\python\AP全链路交易_TRACK_A.py"
src = open(p, "r", encoding="utf-8", errors="replace").read()

print("=== 前 1500 字符 ===")
print(src[:1500])
print()
print("=== 所有 def ===")
for m in re.finditer(r"^def (\w+)", src, re.M):
    print(" ", m.group(1))
print()
print("=== 所有类 ===")
for m in re.finditer(r"^class (\w+)", src, re.M):
    print(" ", m.group(1))
print()
# 找 p2 确认相关
for kw in ["m5", "5m", "period", "bar", "get_market_data", "CONF", "P2", "sweet", "Sweet", "SWEET"]:
    idxs = [m.start() for m in re.finditer(kw, src)][:5]
    if idxs:
        print(f"kw={kw} at {idxs}")
