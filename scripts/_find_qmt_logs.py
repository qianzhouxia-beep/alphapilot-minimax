# -*- coding: utf-8 -*-
"""找 QMT 实盘 userdata/log + users 下的策略运行日志 (一次性)"""
import os, time

def walk_logs(root, days=7):
    now = time.time()
    for dirpath, dirnames, filenames in os.walk(root):
        for fn in sorted(filenames):
            fp = os.path.join(dirpath, fn)
            try:
                mt = os.path.getmtime(fp)
            except Exception:
                continue
            if now - mt > days * 86400:
                continue
            sz = os.path.getsize(fp)
            if sz == 0:
                continue
            print("LOG ", fp, sz, time.strftime("%m-%d %H:%M", time.localtime(mt)))

print("== userdata/log ==")
walk_logs("D:\\国金证券QMT交易端\\userdata\\log")
print()
print("== userdata/users ==")
walk_logs("D:\\国金证券QMT交易端\\userdata\\users")
print()
print("== userdata/data ==")
walk_logs("D:\\国金证券QMT交易端\\userdata\\data")
