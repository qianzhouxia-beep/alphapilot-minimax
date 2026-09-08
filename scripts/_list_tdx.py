# -*- coding: utf-8 -*-
"""列出 TDX 部署目录全部文件，确认用户实际放了哪个"""
from pathlib import Path
import datetime

dirs = [
    r"D:\new_tdx_mock\PYPlugins\user",
]

out = []
for d in dirs:
    p = Path(d)
    out.append(f"===== {d} =====")
    if not p.exists():
        out.append("  NOT FOUND")
        continue
    for f in sorted(p.glob("*.py")):
        mt = datetime.datetime.fromtimestamp(f.stat().st_mtime)
        raw = f.read_bytes()
        # 读头部前 3 行
        head = ""
        for enc in ("utf-8", "gbk"):
            try:
                dec = raw.decode(enc)
                head = "\n    ".join(dec.splitlines()[:3])
                break
            except UnicodeDecodeError:
                continue
        out.append(f"  {f.name}  {f.stat().st_size}B  mtime={mt}")
        out.append(f"    {head}")
    out.append("")

Path(r"C:/Users/elvisq/Projects/alphapilot/output/_tdx_deploy_list.txt").write_text("\n".join(out), encoding="utf-8")
print("written")
