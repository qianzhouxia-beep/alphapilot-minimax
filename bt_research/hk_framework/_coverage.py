#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import statistics as st

import config as C

k = set(json.load(open(C.F_KLINE)).keys())
s = json.load(open(C.F_SOUTH))
ds = sorted(s.keys())
u = set()
for d in ds:
    u |= set(s[d].keys())
print("south days", len(ds), ds[0], "->", ds[-1])
print("kline codes", len(k), "union south codes", len(u))
miss = sorted(u - k)
print("missing kline", len(miss))
print("sample missing", miss[:15])
print("xsec size min/med/max",
      min(len(s[d]) for d in ds), int(st.median(len(s[d]) for d in ds)),
      max(len(s[d]) for d in ds))
