# -*- coding: utf-8 -*-
"""查 QMT 实盘 python 策略目录 + userdata 日志 (一次性)"""
import os

def show(root, label):
    print("="*25, label, root)
    if not os.path.isdir(root):
        print("  NOT EXIST"); return
    for sub in ["python", "userdata", "userdata_mini", "datadir"]:
        p = os.path.join(root, sub)
        if not os.path.isdir(p):
            print(f"  [{sub}] missing"); continue
        print(f"  [{sub}]:")
        try:
            for d in sorted(os.listdir(p)):
                fp = os.path.join(p, d)
                t = os.path.getmtime(fp)
                tt = __import__("time").strftime("%m-%d %H:%M", __import__("time").localtime(t))
                tag = "DIR " if os.path.isdir(fp) else "file"
                print(f"    {tag} {d}  mtime={tt}")
        except Exception as e:
            print("    ERR", e)

show("D:\\国金证券QMT交易端", "LIVE")
