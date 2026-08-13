#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每周策略健康度报告（知识库 C 部分收口）。

汇总一周的置信度数据、资金强度、信号档案，输出每周讨论依据。
建议 cron：周六 10:00
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

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

OUT = ROOT / "output"
KB_REPORTS = ROOT / "knowledge" / "reports"
KB_SIGNALS = ROOT / "knowledge" / "signals"


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def main() -> int:
    KB_REPORTS.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    week_start = now - timedelta(days=now.weekday())  # 本周一
    week_label = week_start.strftime("%Y-%m-%d")

    # 1) 置信度数据（top2_t1t5）
    conf_rows = []
    try:
        src = OUT / "top2_t1t5.json"
        if src.exists():
            d = json.loads(src.read_text(encoding="utf-8"))
            for r in d.get("rows", []):
                if r.get("asof") and r["asof"] >= week_label:
                    conf_rows.append(r)
    except Exception as e:
        log(f"读 top2_t1t5 失败: {e}")

    # 2) 本周每日决策单
    kb_daily = ROOT / "knowledge" / "daily"
    week_days = []
    if kb_daily.exists():
        for i in range(7):
            day = (week_start + timedelta(days=i)).strftime("%Y-%m-%d")
            if (kb_daily / f"{day}.md").exists():
                week_days.append(day)

    # 3) 信号档案 registry
    reg = []
    reg_path = KB_SIGNALS / "_registry.json"
    if reg_path.exists():
        try:
            reg = json.loads(reg_path.read_text(encoding="utf-8"))
        except Exception:
            reg = []

    md = [
        f"# 每周策略健康度报告 — {week_label}",
        "",
        f"> 自动生成：{now.strftime('%Y-%m-%d %H:%M:%S')} ｜ 脚本：`scripts/kb_weekly_report.py`",
        "",
        "## 本周概览",
        "",
        f"- 本周生成决策单：{len(week_days)} 天（{', '.join(week_days) if week_days else '无'}）",
        f"- 本周 Top2 样本日（有 T+N 数据）：{len(conf_rows)} 天",
        "",
        "## 本周 Top2 表现（T+1 / T+2）",
        "",
    ]
    if conf_rows:
        t1 = [x for r in conf_rows for dp in r.get("picks", []) if (x := (dp.get("rets") or {}).get(1)) is not None]
        t2 = [x for r in conf_rows for dp in r.get("picks", []) if (x := (dp.get("rets") or {}).get(2)) is not None]
        for label, vals in (("T+1", t1), ("T+2", t2)):
            if vals:
                md.append(f"- {label}：{len(vals)} 样本，平均 {sum(vals)/len(vals):+.2f}%，正率 {sum(1 for v in vals if v>0)/len(vals)*100:.0f}%")
            else:
                md.append(f"- {label}：暂无（等待交易日回填）")
    else:
        md.append("- 本周暂无 Top2 T+N 数据。")

    md += ["", "## 信号档案状态", ""]
    if reg:
        md.append("| 信号 | 状态 | 样本量 | 胜率 | 平均收益% | 备注 |")
        md.append("|---|---|---|---|---|---|")
        for r in reg:
            md.append(
                f"| {r.get('title','')} | {r.get('status_label','')} | {r.get('n_samples','—')} | "
                f"{r.get('win_rate','—')} | {r.get('avg_ret_pct','—')} | {r.get('note','')} |"
            )
    else:
        md.append("- 暂无已入库信号（`scripts/kb_bt_card.py` 可入库）。")

    md += ["", "## 待办/关注", ""]
    md.append("- 资金背离信号待 institutional_watch 数据积累（目标 09 月初）。")
    md.append("- cache_kline.py 增量更新 pyarrow bug 待修。")
    md.append("- 筹码数据依赖 WorkBuddy 本地上传，注意每日覆盖度。")
    md += ["", "---", "*供用户 + AlphaPilot + WorkBuddy 三方讨论依据。*"]

    target = KB_REPORTS / f"weekly_{week_label}.md"
    target.write_text("\n".join(md) + "\n", encoding="utf-8")
    # 同时维护 latest
    (KB_REPORTS / "weekly_latest.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    log(f"written {target} + weekly_latest.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
