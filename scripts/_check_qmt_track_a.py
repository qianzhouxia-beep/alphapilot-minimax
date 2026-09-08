# -*- coding: utf-8 -*-
"""检查本地 QMT 轨道 A 实盘/模拟文件：版本号 + 甜蜜区代码"""
import re, sys
from pathlib import Path

FILES = {
    "QMT实盘": r"D:\国金证券QMT交易端\python\AP全链路交易_TRACK_A.py",
    "QMT模拟": r"D:\国金QMT交易端模拟\python\AP全链交易模拟_TRACK_A.py",
}

OUT = r"C:/Users/elvisq/Projects/alphapilot/output/_qmt_track_a_check.txt"
lines_out = []

for tag, p in FILES.items():
    f = Path(p)
    lines_out.append(f"===== {tag}  {p} =====")
    if not f.exists():
        lines_out.append("  NOT FOUND")
        continue
    raw = f.read_bytes()
    lines_out.append(f"  size={len(raw)}  mtime={f.stat().st_mtime}")
    # 判断是否可读文本
    try:
        txt = raw.decode("utf-8")
        lines_out.append(f"  decode: utf-8 OK, first 200 chars:")
        lines_out.append("  " + txt[:200].replace("\n", " "))
    except UnicodeDecodeError:
        try:
            txt = raw.decode("gbk")
            lines_out.append(f"  decode: gbk OK (GBK中文文件), first 200 chars:")
            lines_out.append("  " + txt[:200].replace("\n", " "))
        except UnicodeDecodeError:
            lines_out.append("  decode FAILED (binary/encrypted?)")
            # 尝试看是否有明文标记
            for marker in [b"SWEET", b"VERSION", b"sweet_zone", b"v2."]:
                if marker in raw:
                    lines_out.append(f"  marker found: {marker}")
            continue
    # 检查关键标记
    marks = {
        "VERSION=定义": re.search(r'VERSION\s*=\s*["\']([^"\']+)["\']', txt),
        "SWEET_ZONE_MODE": re.search(r'SWEET_ZONE_MODE\s*=\s*(\d+)', txt),
        "SWEET_GAP_LO": re.search(r'SWEET_GAP_LO\s*=\s*([-\d.]+)', txt),
        "SWEET_GAP_HI": re.search(r'SWEET_GAP_HI\s*=\s*([-\d.]+)', txt),
        "_is_sweet_zone 函数": "_is_sweet_zone" in txt,
        "_order_by_sweet/_order_cands_by_sweet": ("_order_by_sweet" in txt) or ("_order_cands_by_sweet" in txt),
        "sweet_tag 日志": "sweet_tag" in txt,
        "[SWEET] 标签": "[SWEET]" in txt or "SWEET" in txt,
        "vwap_ref(次日确认)": "vwap_ref" in txt,
        "_trading_days_between(交易日)": "_trading_days_between" in txt,
    }
    for name, m in marks.items():
        if isinstance(m, re.Match):
            lines_out.append(f"  [OK] {name} = {m.group(1)}")
        elif m is True:
            lines_out.append(f"  [OK] {name}")
        elif m is False:
            lines_out.append(f"  [NO] {name}")
        else:
            lines_out.append(f"  [NO] {name}")
    lines_out.append("")

Path(OUT).write_text("\n".join(lines_out), encoding="utf-8")
print("written", OUT)
