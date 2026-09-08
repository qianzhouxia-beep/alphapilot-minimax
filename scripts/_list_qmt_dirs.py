# -*- coding: utf-8 -*-
"""枚举 QMT 安装目录(实盘/模拟)找策略与日志 (一次性)"""
import os, glob, time

for root in ["D:\\国盛证券QMT交易端", "D:\\国金QMT交易端模拟", "D:\\国金证券QMT交易端"]:
    print("="*20, root)
    if not os.path.isdir(root):
        print("  NOT EXIST")
        continue
    try:
        for d in sorted(os.listdir(root)):
            p = os.path.join(root, d)
            tag = "DIR " if os.path.isdir(p) else "file"
            print("  ", tag, d)
    except Exception as e:
        print("  ERR", e)
