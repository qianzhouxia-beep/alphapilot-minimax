#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取港交所「可进行卖空的指定证券名单」CSV -> data/shortable.json。
名单每周/每季更新；建议每周跑一次（cron）。"""
import csv
import datetime as dt
import io as _io
import os
import re
import urllib.request

import config as C
import dataio as dio

BASE = ("https://www.hkex.com.hk/-/media/HKEX-Market/Services/Trading/"
        "Securities/Securities-Lists/Designated-Securities-Eligible-for-Short-Selling/")
UA = "Mozilla/5.0"


def _try(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8-sig", "replace")


def main():
    # 先试最近 20 天可能的文件名
    today = dt.date.today()
    text = None
    for k in range(0, 25):
        d = (today - dt.timedelta(days=k)).strftime("%Y%m%d")
        for suf in ("_c", "_e"):
            url = f"{BASE}ds_list{d}{suf}.csv"
            try:
                t = _try(url)
                if "股份代號" in t or "Stock Code" in t:
                    text = t
                    print(f"got {url}")
                    break
            except Exception:
                continue
        if text:
            break
    if not text:
        raise SystemExit("short list not found in last 25 days")

    rows = list(csv.reader(_io.StringIO(text)))
    codes = []
    for r in rows:
        if len(r) >= 2:
            v = re.sub(r"\D", "", r[1])
            if v:
                codes.append(v.zfill(5))
    codes = sorted(set(codes))
    dio.save_atomic({"effective": today.strftime("%Y-%m-%d"), "n": len(codes),
                     "codes": codes}, C.F_SHORTABLE)
    print(f"shortable n={len(codes)} -> {C.F_SHORTABLE}")


if __name__ == "__main__":
    main()
