# -*- coding: utf-8 -*-
"""周一 16:20 融合 IC 核验提醒（AlphaPilot_fusion_ic_monday_check 触发）。
在 16:15 后自动拉服务器状态并落盘，弹窗提醒用户查看。"""
import os
import subprocess
import sys
import ctypes
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\elvisq\Projects\alphapilot")
OUT = ROOT / "output" / "fusion_ic_monday_check.log"
SCRIPT = ROOT / "scripts" / "check_fusion_ic_checkpoint.py"

env = dict(os.environ)
env["PYTHONIOENCODING"] = "utf-8"


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    lines.append("=== fusion IC Monday check @ {} ===".format(
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    try:
        r = subprocess.run(
            [sys.executable, str(SCRIPT), "--pull-server"],
            cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=120,
            encoding="utf-8", errors="replace",
        )
        lines.append("exit_code={}".format(r.returncode))
        lines.append("--- stdout ---")
        lines.append(r.stdout or "")
        if r.stderr:
            lines.append("--- stderr ---")
            lines.append(r.stderr or "")
    except Exception as e:
        lines.append("EXC: {!r}".format(e))
    text = "\n".join(lines)
    OUT.write_text(text, encoding="utf-8")
    # 提取关键行做醒目弹窗（不用开日志就能看懂）
    key_lines = []
    for kw in ("GATE_jsonl_non_backfill", "GATE_open_pos_fusion",
               "GATE_weights_after_1615", "INTERP", "GATE_goal_complete",
               "n_used", "rolling_ic", "error"):
        for ln in text.splitlines():
            if ln.startswith(kw):
                key_lines.append(ln)
                break
    # 从 server stdout 里补 n_samples 信息
    if "SERVER" in text and "n_samples" in text:
        for ln in text.splitlines():
            if "n_samples" in ln:
                key_lines.append(ln)
    popup = "\n".join(key_lines) if key_lines else text[:800]
    try:
        ctypes.windll.user32.MessageBoxW(
            0, "FUSION IC 周一核验\n\n{}\n\n完整日志:\n{}".format(popup, OUT),
            "AlphaPilot Fusion IC Check", 0x40,
        )
    except Exception:
        pass
    print(text, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
