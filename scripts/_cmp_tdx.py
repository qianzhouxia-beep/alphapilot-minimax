# -*- coding: utf-8 -*-
"""对比 TDX 部署版本 vs 本地权威版"""
import hashlib
from pathlib import Path

LOCAL = Path(r"C:\Users\elvisq\Projects\alphapilot\production_strategies\track_a\TrackA_track_a_tdx_full_chain_sim.py")

# 找 TDX 部署位置
candidates = [
    r"D:\new_tdx_mock\PYPlugins\user\TrackA_track_a_tdx_full_chain_sim.py",
    r"D:\new_tdx\PYPlugins\user\TrackA_track_a_tdx_full_chain_sim.py",
]

out = []
out.append(f"LOCAL: {LOCAL}")
out.append(f"  size={LOCAL.stat().st_size}  mtime={LOCAL.stat().st_mtime}")
out.append(f"  md5={hashlib.md5(LOCAL.read_bytes()).hexdigest()}")
out.append("")

for c in candidates:
    p = Path(c)
    out.append(f"TDX: {c}")
    if not p.exists():
        out.append("  NOT FOUND")
        continue
    raw = p.read_bytes()
    out.append(f"  size={len(raw)}  mtime={p.stat().st_mtime}")
    out.append(f"  md5={hashlib.md5(raw).hexdigest()}")
    out.append(f"  same_as_local={raw == LOCAL.read_bytes()}")
    # 检查是否加密
    dec = None
    for enc in ("utf-8", "gbk"):
        try:
            dec = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if dec and ("def " in dec or "import " in dec):
        out.append("  PLAINTEXT (readable)")
        # 版本
        import re
        m = re.search(r'\[INIT\] track-A[^"]*?v([\d.]+)', dec)
        out.append(f"  [INIT] version: {m.group(1) if m else '?'}")
        for kw in ["SWEET_ZONE_MODE", "vwap_ref", "_trading_days_between", "timezone", "TDX", "TdxQuant"]:
            out.append(f"    {kw}: {'YES' if kw in dec else 'no'}")
    else:
        out.append("  ENCRYPTED/BINARY?")
    out.append("")

Path(r"C:/Users/elvisq/Projects/alphapilot/output/_tdx_cmp.txt").write_text("\n".join(out), encoding="utf-8")
print("written")
