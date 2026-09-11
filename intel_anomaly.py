#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""情报层：盘中异动归因（阶段3）。

将盘前情报（intel_prebrief.json 的事件判定）与盘中板块资金告警
（intraday_sector_watch.py 的 sector_watch_alerts.json）关联，
为异动给出"可能原因"，输出 output/intel_anomaly.json。

- 只做解释，不改交易信号（trade_executor 仍以 sector_watch_alerts 为准）。
- 任何源缺失时优雅降级：无情报事件 → 仅提示"无盘前事件匹配"。

挂法（建议 10:00/11:00/13:30/14:30 与 intraday_sector_watch 同批次）:
  python3 -u intel_anomaly.py >> output/logs/intel_anomaly.log 2>&1
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path("/home/ubuntu/alphapilot")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

PREBRIEF = ROOT / "output" / "intel_prebrief.json"
WATCH = ROOT / "output" / "sector_watch_alerts.json"
OUT = ROOT / "output" / "intel_anomaly.json"


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def match_events(events: list[dict], sectors: list[str]) -> list[dict]:
    """把情报事件与涉及的板块匹配。"""
    hits = []
    for e in events or []:
        secs = set(e.get("sectors") or [])
        if not secs:
            continue
        overlap = secs & set(sectors)
        if overlap:
            hits.append({**e, "matched_sectors": sorted(overlap)})
    return hits


def run() -> int:
    log("情报层 盘中异动归因 开始")
    prebrief = load_json(PREBRIEF)
    watch = load_json(WATCH)

    events = prebrief.get("events") or []
    risk = prebrief.get("risk_assessment") or {}
    alerts = watch.get("alerts") or []

    # 归因对象：盘中告警涉及的板块 + 大盘风险
    alert_sectors = sorted({a.get("sector", "") for a in alerts if a.get("sector")})

    matched = match_events(events, alert_sectors)
    attribution = []
    for a in alerts:
        sec = a.get("sector", "")
        ev_hits = [m for m in matched if sec in m.get("matched_sectors", [])]
        reasons = [m["reason"] for m in ev_hits] or [
            "盘前无该板块事件匹配（可能为盘内资金面驱动）"
        ]
        attribution.append({
            "symbol": a.get("symbol"),
            "name": a.get("name"),
            "sector": sec,
            "action": a.get("action"),
            "severity": a.get("severity"),
            "alarm_reason": a.get("reason"),
            "intel_reasons": reasons,
        })

    payload = {
        "asof": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "risk_level": risk.get("level", "normal"),
        "risk_cap": risk.get("suggest_expo_cap"),
        "market_intel_summary": (risk.get("reasons") or [])[:5],
        "attribution": attribution,
        "n_attribution": len(attribution),
        "note": "情报归因仅作解释，不改变 trade_executor 的卖出信号",
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"写入 {OUT}：告警 {len(alerts)} 条，归因 {len(attribution)} 条，匹配事件 {len(matched)} 个")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
