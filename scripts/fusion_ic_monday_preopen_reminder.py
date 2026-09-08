# -*- coding: utf-8 -*-
"""周一 09:00 开盘前提醒：六端策略是否已重启（融合 IC 输入管线的前提）。

融合 IC 链路的成败取决于：新买入必须带 fusion_scores、平仓写 jsonl。
前提 = 开盘前六端策略已重启（checkpoints 08-29 19:45 用户手动项）。
本脚本只做提醒 + 快速检查本机 pos_state/candidates 是否就绪，不修改任何东西。
"""
import json
import ctypes
from datetime import datetime
from pathlib import Path

LEDGER = Path(r"C:\alphapilot")
POS_FILES = {
    "qmt_live": LEDGER / "live_pos_state.json",
    "qmt_sim": LEDGER / "sim_pos_state.json",
    "tdx_sim": LEDGER / "tdx_pos_state.json",
}


def main() -> int:
    lines = ["=== Fusion IC 开盘前检查 @ {} ===".format(
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"))]
    lines.append("")
    lines.append("【开盘前必办（用户手动项，checkpoints 08-29 19:45）】")
    lines.append("  1. B 端 QMT 客户端导入加密策略 TrackB_live v2.4-tpl / TrackB_sim v2.4")
    lines.append("  2. 六端全部重启策略：A QMT live v2.25-tpl / A QMT sim v2.25 / A TDX v2.24 x2 / B TDX v1.15")
    lines.append("  3. 重启后日志 [INIT] ... v2.2X，买入日志带 SWEET 标签")
    lines.append("  4. 新买入必须带 fusion_scores（否则融合 IC 周一无样本）")
    lines.append("")
    lines.append("【当前本机持仓状态（供参考）】")
    for src, p in POS_FILES.items():
        if not p.exists():
            lines.append(f"  {src}: 文件不存在")
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            positions = d.get("positions") or {}
            with_fs = sum(
                1 for pos in positions.values()
                if isinstance(pos, dict) and isinstance(pos.get("fusion_scores"), dict)
            )
            lines.append(f"  {src}: {len(positions)} 仓, 其中 {with_fs} 带 fusion_scores")
        except Exception as e:
            lines.append(f"  {src}: 读取失败 {e!r}")

    text = "\n".join(lines)
    try:
        ctypes.windll.user32.MessageBoxW(
            0,
            "Fusion IC 开盘前提醒（周一）：\n\n" + text,
            "AlphaPilot Fusion IC Pre-open", 0x40,
        )
    except Exception:
        pass
    print(text, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
