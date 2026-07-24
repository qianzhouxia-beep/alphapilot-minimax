#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性迁移：对齐模拟盘 JSON 到 Top2 可交易闭环字段。

- 重命名 v19_daily → VM2.5 Top2 日频
- 合并僵尸 eod_sniper 持仓到 s2_eod（保留仓位，统一尾盘板块）
- 写入 protocol / position_exposure（从 daily_recommend）
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path("/home/ubuntu/alphapilot")
PT = ROOT / "data/paper_trading.json"
REC = ROOT / "output/daily_recommend.json"


def main() -> int:
    pt = json.loads(PT.read_text(encoding="utf-8"))
    expo = 1.0
    flags = {}
    if REC.exists():
        rec = json.loads(REC.read_text(encoding="utf-8"))
        expo = float(rec.get("position_exposure", 1.0) or 0.0)
        flags = rec.get("market_env_flags") or {}

    by_id = {s.get("id"): s for s in pt.get("strategies") or []}

    # daily
    daily = by_id.get("v19_daily")
    if daily:
        daily["name"] = "VM2.5 Top2 日频"
        daily["status"] = daily.get("status") or "active"
        for p in daily.get("positions") or []:
            p.setdefault("protocol", "tradable_top2")
            p.setdefault("strategy_id", "v19_daily")

    # merge eod_sniper -> s2_eod
    sniper = by_id.get("eod_sniper")
    s2 = by_id.get("s2_eod")
    if sniper and s2:
        for p in sniper.get("positions") or []:
            p["strategy_id"] = "s2_eod"
            p["protocol"] = "eod_overlay"
            p["_migrated_from"] = "eod_sniper"
            s2.setdefault("positions", []).append(p)
        s2["used"] = float(s2.get("used") or 0) + float(sniper.get("used") or 0)
        s2["name"] = "尾盘狙击（S2）"
        s2["allocated"] = max(float(s2.get("allocated") or 0), float(sniper.get("allocated") or 0))
        # keep empty eod_sniper shell as inactive for history ids in trade_log
        sniper["positions"] = []
        sniper["signals"] = []
        sniper["status"] = "migrated"
        sniper["name"] = "尾盘狙击（已合并到S2）"
        sniper["used"] = 0
    elif sniper and not s2:
        sniper["id"] = "s2_eod"
        sniper["name"] = "尾盘狙击（S2）"
        for p in sniper.get("positions") or []:
            p["strategy_id"] = "s2_eod"
            p["protocol"] = "eod_overlay"

    if s2:
        s2["name"] = "尾盘狙击（S2）"
        for p in s2.get("positions") or []:
            p.setdefault("protocol", "eod_overlay")

    pt["position_exposure"] = expo
    pt["market_env_flags"] = flags
    pt["protocol"] = {
        "name": "tradable_top2",
        "entry": "T+1 open skip if limit-up",
        "exit": "T+2 close (stops may exit earlier)",
        "top_n": 2,
        "cost_rt": 0.0015,
        "strategy_id": "v19_daily",
        "eod_overlay": "s2_eod",
    }
    pt["empty_reason"] = "position_exposure_zero" if expo <= 0 else None
    pt["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    pt["migrated_protocol_at"] = pt["updated_at"]

    # drop fully migrated empty eod_sniper from strategies list (optional keep)
    pt["strategies"] = [
        s for s in pt.get("strategies") or []
        if not (s.get("id") == "eod_sniper" and s.get("status") == "migrated" and not s.get("positions"))
    ]

    PT.write_text(json.dumps(pt, ensure_ascii=False, indent=2), encoding="utf-8")
    print("OK migrated", PT)
    print("strategies:", [(s.get("id"), s.get("name"), len(s.get("positions") or [])) for s in pt["strategies"]])
    print("expo", expo, "protocol", pt["protocol"]["name"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
