# -*- coding: utf-8 -*-
"""对比 TDX 部署 v2.23 vs 本地 v2.26，找出新增/变化代码"""
from pathlib import Path
import difflib

tdx = Path(r"D:\new_tdx_mock\PYPlugins\user\TrackA_track_a_tdx_full_chain_sim_v2.31.py").read_text(encoding="utf-8", errors="replace")
local = Path(r"C:\Users\elvisq\Projects\alphapilot\production_strategies\track_a\TrackA_track_a_tdx_full_chain_sim_v2.31.py").read_text(encoding="utf-8", errors="replace")

tdx_lines = tdx.splitlines()
local_lines = local.splitlines()

out = []
out.append(f"TDX deployed v2.23: {len(tdx_lines)} lines")
out.append(f"LOCAL     v2.26: {len(local_lines)} lines")
out.append("")

diff = list(difflib.unified_diff(tdx_lines, local_lines, lineterm="", n=2))
# 统计
added = [l for l in diff if l.startswith("+") and not l.startswith("+++")]
removed = [l for l in diff if l.startswith("-") and not l.startswith("---")]
out.append(f"added lines: {len(added)}, removed: {len(removed)}")
out.append("")

# 打印关键 diff（跳过纯注释）
out.append("===== DIFF (key, non-comment) =====")
count = 0
for l in diff:
    if l.startswith("+++") or l.startswith("---") or l.startswith("@@"):
        out.append(l)
        continue
    content = l[1:].strip() if l.startswith(("+", "-")) else l.strip()
    if not content:
        continue
    # 过滤纯注释行
    if content.startswith("#") or content.startswith('"""') or content.startswith("'''"):
        # 但版本注释重要，保留
        if "v2." in content or "2026-" in content or "hold" in content.lower():
            out.append(l[:150])
        continue
    out.append(l[:200])
    count += 1

Path(r"C:/Users/elvisq/Projects/alphapilot/output/_tdx_diff.txt").write_text("\n".join(out), encoding="utf-8")
print("written, key diff lines:", count)
