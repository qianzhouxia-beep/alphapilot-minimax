# -*- coding: utf-8 -*-
"""找 QMT 模拟端 B 轨今日日志 (一次性)"""
import os, time

for root in ["D:\\国金QMT交易端模拟\\userdata\\log"]:
    print("="*20, root)
    if not os.path.isdir(root):
        print("NOT EXIST"); continue
    for fn in sorted(os.listdir(root)):
        if "FormulaOutput_20260831" in fn or "Formula_20260831" in fn:
            fp = os.path.join(root, fn)
            print(" ", fn, os.path.getsize(fp), time.strftime("%m-%d %H:%M", time.localtime(os.path.getmtime(fp))))
