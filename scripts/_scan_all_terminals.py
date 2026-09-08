# -*- coding: utf-8 -*-
"""扫描各交易端日志的 [VWAP] broken / vwap_weak_early / 早盘卖出 (一次性)"""
import re, os

SCANS = [
    ("QMT live (TrackA)", r"D:\国金证券QMT交易端\userdata\log",
     ["20260824", "20260825", "20260826", "20260827", "20260828", "20260831"]),
    ("QMT sim (TrackB)", r"D:\国金QMT交易端模拟\userdata\log",
     ["20260824", "20260825", "20260826", "20260827", "20260828", "20260831"]),
]
# TDX 日志是单文件累积
SCANS += [
    ("TDX A (full_chain)", r"C:\alphapilot\tdx_full_chain.log", None),
    ("TDX B (auction)", r"C:\alphapilot\b_tdx_auction.log", None),
]

pat_time = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")

for label, path, dates in SCANS:
    print("=" * 80)
    print("### %s" % label)
    vwap_hits = []
    sell_weak = []
    if dates:
        files = [os.path.join(path, "XtClient_FormulaOutput_%s.log" % d) for d in dates]
    else:
        files = [path]
    for f in files:
        if not os.path.exists(f):
            continue
        with open(f, encoding="utf-8", errors="replace") as fh:
            for ln in fh:
                if "[VWAP]" in ln:
                    vwap_hits.append(ln.strip()[:200])
                elif "vwap_weak_early" in ln or "wyckoff_bc" in ln:
                    sell_weak.append(ln.strip()[:200])
    print("  [VWAP] broken hits:", len(vwap_hits))
    seen = set()
    for h in vwap_hits:
        # 去重：同一天同一股票同一条信息
        key = h.split("px=")[0]
        if key in seen:
            continue
        seen.add(key)
        print("   ", h)
    print("  vwap_weak_early / wyckoff_bc sells:", len(sell_weak))
    seen2 = set()
    for s in sell_weak:
        key = s.split("all")[0].split("half")[0]
        if key in seen2:
            continue
        seen2.add(key)
        print("   ", s)
