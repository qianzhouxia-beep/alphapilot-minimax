#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from mootdx.quotes import Quotes
import pandas as pd
import re
import json

q = Quotes.factory(market="std")
for code in ["600519", "300750", "000001"]:
    f = q.F10(symbol=code)
    print("====", code)
    gk = f.get("公司概况")
    print("公司概况 type", type(gk))
    print(str(gk)[:1500])
    print("---行业分析---")
    print(str(f.get("行业分析"))[:800])
    print()

# Find industry-like blocknames containing 酒 / 半导体 / 银行
df = q.block()
print("total rows", len(df), "unique blocks", df["blockname"].nunique())
for kw in ["白酒", "酿酒", "半导体", "银行", "电力", "煤炭"]:
    sub = df[df["blockname"].astype(str).str.contains(kw, na=False)]
    names = sub["blockname"].drop_duplicates().tolist()
    print(kw, "blocks", names[:20], "n_codes", len(sub))

# For 600519, which blocks contain it?
sub = df[df["code"].astype(str).str.zfill(6) == "600519"]
print("600519 blocks sample:", sub["blockname"].drop_duplicates().tolist()[:40])
print("600519 block_type value_counts:\n", sub["block_type"].value_counts().head(15))
