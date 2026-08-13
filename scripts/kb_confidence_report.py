#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""置信度闭环（知识库 C 部分）：把「决策 → 结果」对上。

数据源：output/top2_t1t5.json（16:25 由 accumulate_top2_t1t5.py 更新，含每日 Top2 的 T+1..T+5 涨幅）
输出：
  knowledge/signals/top2_t1t5_confidence.md — 每日置信度档案（含字段由 Agent 检索）
  knowledge/reports/confidence_daily.md     — 人读报告
建议 cron：工作日 16:30（在 accumulate_top2_t1t5 之后）
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime
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
KB_SIGNALS = ROOT / "knowledge" / "signals"
KB_REPORTS = ROOT / "knowledge" / "reports"


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def main() -> int:
    src = OUT / "top2_t1t5.json"
    if not src.exists():
        log("未找到 output/top2_t1t5.json，跳过（先跑 accumulate_top2_t1t5.py）")
        return 2
    data = json.loads(src.read_text(encoding="utf-8"))
    summary = data.get("summary") or {}
    rows = data.get("rows") or []

    # 统计每个持有期的胜率（收益 > 0 的占比）
    lines = [
        "# Top2 选股 T+N 置信度档案（自动回写）",
        "",
        f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"> 数据源：`output/top2_t1t5.json`（每日 16:25 更新，样本日 {len(rows)} 天）",
        "",
        "## 汇总（全部历史 Top2）",
        "",
        "| 持有期 | 样本数 | 平均% | 中位% | 正收益数 | 最好% | 最差% | 胜率 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    stats = {}
    for i in range(1, 6):
        s = summary.get(str(i))
        if not s:
            continue
        n = s["n"]
        win = s.get("pos_count", 0)
        lines.append(
            f"| T+{i} | {n} | {s['avg_pct']:+.2f} | {s['median_pct']:+.2f} | {win} | "
            f"{s['best']:+.2f} | {s['worst']:+.2f} | {win/n*100:.1f}% |"
        )
        stats[str(i)] = {
            "n": n,
            "avg_pct": s["avg_pct"],
            "median_pct": s["median_pct"],
            "win_count": win,
            "win_rate": round(win / n, 3) if n else None,
        }

    # 最近 N 天表现（滚动窗口，观测稳定性）
    recent_days = rows[-30:] if len(rows) > 30 else rows
    lines += ["", "## 最近 30 个选股日表现", ""]
    lines.append("| 选股日 | 代码 | 名称 | T+1% | T+2% | T+3% | T+4% | T+5% |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in recent_days:
        for dp in r.get("picks", []):
            rets = dp.get("rets") or {}
            f = lambda v: "—" if v is None else f"{v:+.2f}"
            lines.append(
                f"| {r.get('asof')} | {dp.get('symbol')} | {dp.get('name')} | "
                f"{f(rets.get('1'))} | {f(rets.get('2'))} | {f(rets.get('3'))} | {f(rets.get('4'))} | {f(rets.get('5'))} |"
            )

    # 按代码统计胜率（哪些票常被选且表现好）
    by_sym: dict[str, list] = defaultdict(list)
    for r in rows:
        for dp in r.get("picks", []):
            t1 = (dp.get("rets") or {}).get("1")
            if t1 is not None:
                by_sym[dp.get("symbol", "")].append(t1)
    lines += ["", "## 按代码统计（出现 ≥3 次的 Top2 票，T+1 平均）", ""]
    lines.append("| 代码 | 名称 | 出现次数 | T+1平均% | T+1正率 |")
    lines.append("|---|---|---|---|---|")
    for sym, vals in sorted(by_sym.items(), key=lambda x: -len(x[1])):
        if len(vals) < 3:
            continue
        name = ""
        for r in rows:
            for dp in r.get("picks", []):
                if dp.get("symbol") == sym:
                    name = dp.get("name") or ""
                    break
            if name:
                break
        lines.append(
            f"| {sym} | {name} | {len(vals)} | {sum(vals)/len(vals):+.2f} | "
            f"{sum(1 for v in vals if v > 0)/len(vals)*100:.0f}% |"
        )

    lines += ["", "## 置信度小结（给 Agent 决策用）", ""]
    t1 = stats.get("1")
    if t1:
        lines.append(
            f"- T+1 持有：样本 {t1['n']}，平均 {t1['avg_pct']:+.2f}%，胜率 {t1['win_rate']*100:.1f}%"
        )
    t2 = stats.get("2")
    if t2:
        lines.append(
            f"- T+2 持有（可交易协议口径）：样本 {t2['n']}，平均 {t2['avg_pct']:+.2f}%，胜率 {t2['win_rate']*100:.1f}%"
        )
    lines.append("- 样本量仍偏小，结论仅供参考；不足 30 样本的统计口径标注为「初步」。")

    KB_SIGNALS.mkdir(parents=True, exist_ok=True)
    KB_REPORTS.mkdir(parents=True, exist_ok=True)
    (KB_SIGNALS / "top2_t1t5_confidence.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (KB_REPORTS / "confidence_daily.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    log("已回写 knowledge/signals/top2_t1t5_confidence.md + knowledge/reports/confidence_daily.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
