#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回测结论卡统一入库工具（知识库 B 部分）。

回测脚本跑完后，用本脚本把结论卡写入 knowledge/signals/ 与 knowledge/reports/，
让结论以统一格式沉淀、可被 Agent 检索。

用法：
  python3 scripts/kb_bt_card.py --signal "vwap_dip" --status candidate \
      --title "VWAP回踩" --n 13 --win-rate 0.308 --avg-ret 0.06 \
      --desc "回踩VWAP 0.8%买入，30分钟收益" --note "跑输直接买基线"
  python3 scripts/kb_bt_card.py --list   # 列出已入库信号
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("ALPHAPILOT_ROOT") or str(SCRIPT_ROOT))
for _candidate in (ROOT, SCRIPT_ROOT):
    if (_candidate / "alphapilot_pipeline_v3.py").exists() or (_candidate / "knowledge").exists():
        ROOT = _candidate
        break
else:
    ROOT = SCRIPT_ROOT
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

SIGNALS = ROOT / "knowledge" / "signals"
REGISTRY = SIGNALS / "_registry.json"
STATUSES = {"live": "✅ 已上线", "candidate": "🔶 候选待验证", "rejected": "❌ 已否决", "pending": "🕐 待数据"}


def load_registry() -> list[dict]:
    if REGISTRY.exists():
        try:
            return json.loads(REGISTRY.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def save_registry(rows: list[dict]) -> None:
    REGISTRY.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def add_card(args) -> int:
    SIGNALS.mkdir(parents=True, exist_ok=True)
    rows = load_registry()
    rows = [r for r in rows if r.get("signal") != args.signal]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = {
        "signal": args.signal,
        "title": args.title,
        "status": args.status,
        "status_label": STATUSES.get(args.status, args.status),
        "n_samples": args.n,
        "win_rate": args.win_rate,
        "avg_ret_pct": args.avg_ret,
        "desc": args.desc,
        "note": args.note,
        "updated_at": now,
        "report": args.report,
    }
    rows.append(row)
    rows.sort(key=lambda r: r.get("signal") or "")
    save_registry(rows)

    # 追加/更新 signals/index.md 表格
    idx = SIGNALS / "index.md"
    if idx.exists():
        lines = idx.read_text(encoding="utf-8").split("\n")
        # 找到信号一览表格行并更新（若已有该 signal 行）
        replaced = False
        for i, ln in enumerate(lines):
            if ln.startswith("| ") and f"`{args.signal}`" in ln and "|" in ln:
                lines[i] = (
                    f"| {args.title} | {args.desc} | {row['status_label']} | {args.note or ''} | "
                    f"{args.n if args.n is not None else '—'} | 见 registry |"
                )
                replaced = True
                break
        if not replaced:
            # 在表格尾追加一行（先定位分隔行 "|---|---|" 作为表格边界）
            header_done = False
            for i, ln in enumerate(lines):
                if ln.startswith("|") and "---" in ln:
                    header_done = True
                    continue
                if header_done and ln.startswith("| "):
                    # 找下一行非表格行，插入
                    j = i
                    while j < len(lines) and lines[j].startswith("| "):
                        j += 1
                    lines.insert(j, (
                        f"| {args.title} | {args.desc} | {row['status_label']} | {args.note or ''} | "
                        f"{args.n if args.n is not None else '—'} | 见 registry |"
                    ))
                    break
        idx.write_text("\n".join(lines), encoding="utf-8")

    print(f"[kb_bt_card] 已入库信号: {args.signal} ({row['status_label']})", flush=True)
    return 0


def list_cards(_args) -> int:
    rows = load_registry()
    if not rows:
        print("暂无已入库信号")
        return 0
    print(f"{'signal':<18}{'title':<20}{'status':<12}{'n':<6}{'win_rate':<9}{'avg_ret':<8}updated")
    for r in rows:
        print(
            f"{r.get('signal',''):<18}{str(r.get('title',''))[:18]:<20}{r.get('status_label',''):<12}"
            f"{str(r.get('n_samples') or ''):<6}{str(r.get('win_rate') or ''):<9}{str(r.get('avg_ret_pct') or ''):<8}{r.get('updated_at','')}"
        )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="回测结论卡入库")
    ap.add_argument("--list", action="store_true", help="列出已入库信号")
    ap.add_argument("--signal", help="信号标识（如 vwap_dip）")
    ap.add_argument("--title", default="", help="信号名")
    ap.add_argument("--status", choices=list(STATUSES), default="candidate")
    ap.add_argument("--n", type=int, help="样本量")
    ap.add_argument("--win-rate", type=float, help="胜率 0~1")
    ap.add_argument("--avg-ret", type=float, help="平均收益(百分数值,如 0.06 表示0.06个百分点)")
    ap.add_argument("--desc", default="", help="一句话描述")
    ap.add_argument("--note", default="", help="结论/备注")
    ap.add_argument("--report", default="", help="关联回测报告路径")
    args = ap.parse_args()
    if args.list:
        return list_cards(args)
    if not args.signal:
        ap.error("--signal 必填")
    return add_card(args)


if __name__ == "__main__":
    raise SystemExit(main())
