#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从板块多周期资金 API + 万得行业流构建晨间可用的研报偏好 bias。

输出:
  output/sector_research_bias.json          # 最新指针（晨间读取）
  output/sector_reports/{YYYYMMDD}_{session}_bias.json  # 归档

分轨:
  - 通达信多周期 → prefer/avoid（avoid 仍可硬剔，走 research_sector_gate）
  - 万得 consult → wind_prefer 并入 prefer（软加分）；wind_avoid / rotation_watch
    仅作解释与观察，**不**写入硬 avoid（避免积分口径一刀切改交易）

可被:
  - sector_research_report.py 盘后生成时调用
  - cron 08:50 盘前刷新（保证晨间有最新偏好）
  - 手工: python3 scripts/build_sector_research_bias.py
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sector_research_report import (  # noqa: E402
    PERIODS,
    analyze_sector_rotation,
    fetch_sector_dashboard,
    generate_forecast,
    load_wind_board_flow,
)

OUT = ROOT / "output"
BIAS_LATEST = OUT / "sector_research_bias.json"
REPORT_DIR = OUT / "sector_reports"


def _merge_unique(base: list[str], extra: list[str], limit: int = 24) -> list[str]:
    out: list[str] = []
    for n in list(base) + list(extra):
        n = str(n or "").strip()
        if n and n not in out:
            out.append(n)
        if len(out) >= limit:
            break
    return out


def build_bias_payload(
    dashboards: dict,
    session: str,
    date_str: str | None = None,
    wind_flow: dict | None = None,
) -> dict:
    date_str = date_str or datetime.now().strftime("%Y-%m-%d")
    rotation = analyze_sector_rotation(dashboards)
    forecast = generate_forecast(dashboards, {}, rotation)
    today = dashboards.get("today") or {}
    analysis = today.get("analysis") or {}

    prefer: list[str] = []
    for s in forecast.get("tier1") or []:
        n = s.get("name") if isinstance(s, dict) else str(s)
        if n and n not in prefer:
            prefer.append(n)
    for s in forecast.get("tier2") or []:
        n = s.get("name") if isinstance(s, dict) else str(s)
        if n and n not in prefer:
            prefer.append(n)

    avoid: list[str] = []
    for s in forecast.get("weak") or []:
        n = s if isinstance(s, str) else (s.get("name") if isinstance(s, dict) else None)
        if n and n not in avoid:
            avoid.append(n)
    for s in forecast.get("tier3_watch") or []:
        n = s.get("name") if isinstance(s, dict) else str(s)
        if n and n not in avoid:
            avoid.append(n)
    for s in analysis.get("avoid") or []:
        n = s.get("name") if isinstance(s, dict) else str(s)
        if n and n not in avoid:
            avoid.append(n)

    prefer_set = set(prefer)
    avoid = [a for a in avoid if a not in prefer_set]

    watch = [
        (s.get("name") if isinstance(s, dict) else str(s))
        for s in (forecast.get("tier3_watch") or [])
    ]

    wind_prefer: list[str] = []
    wind_avoid: list[str] = []
    rotation_watch: list[str] = []
    wind_meta: dict = {}
    if wind_flow is None:
        wind_flow = load_wind_board_flow()
    if isinstance(wind_flow, dict):
        consult = wind_flow.get("consult") or {}
        wind_prefer = list(consult.get("prefer") or [])
        wind_avoid = list(consult.get("avoid") or [])
        rotation_watch = list(consult.get("rotation_watch") or [])
        wind_meta = {
            "asof": wind_flow.get("asof"),
            "updated_at": wind_flow.get("updated_at"),
            "all_a_tone": ((consult.get("all_a_sentiment") or {}).get("tone")),
            "purpose": wind_flow.get("purpose") or "consult_research_only",
            "trading_gate_unchanged": True,
        }
        # 仅把万得新鲜流入并入 prefer（软加分）；不把 wind_avoid 写入硬 avoid
        prefer = _merge_unique(wind_prefer, prefer, limit=24)

    prefer_set = set(prefer)
    avoid = [a for a in avoid if a not in prefer_set]

    return {
        "date": date_str,
        "session": session,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "sector_api_multi_period+wind_board_flow",
        "prefer": prefer,
        "avoid": avoid,
        "watch": [w for w in watch if w],
        "wind_prefer": wind_prefer,
        "wind_avoid": wind_avoid,
        "rotation_watch": rotation_watch,
        "wind": wind_meta,
        "counts": {
            "strong": len(rotation.get("strong_sectors") or []),
            "weak": len(rotation.get("weak_sectors") or []),
            "improving": len(rotation.get("improving_sectors") or []),
            "deteriorating": len(rotation.get("deteriorating_sectors") or []),
            "prefer": len(prefer),
            "avoid": len(avoid),
            "wind_prefer": len(wind_prefer),
            "rotation_watch": len(rotation_watch),
        },
        "rotation_sample": {
            "strong": [s["name"] for s in (rotation.get("strong_sectors") or [])[:8]],
            "weak": [s["name"] for s in (rotation.get("weak_sectors") or [])[:8]],
        },
    }


def write_bias(payload: dict) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    BIAS_LATEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    arch = REPORT_DIR / f"{payload['date'].replace('-', '')}_{payload['session']}_bias.json"
    arch.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return BIAS_LATEST


def fetch_and_build(session: str = "preopen") -> dict:
    dashboards = {}
    for period in PERIODS:
        dashboards[period] = fetch_sector_dashboard(period) or {}
    return build_bias_payload(dashboards, session=session)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--session",
        default="preopen",
        help="标签：preopen/morning/afternoon",
    )
    args = ap.parse_args()
    print(f"build_sector_research_bias session={args.session}", flush=True)
    payload = fetch_and_build(session=args.session)
    path = write_bias(payload)
    print(
        f"saved {path} prefer={payload['prefer'][:8]} avoid={payload['avoid'][:8]} "
        f"wind_prefer={payload.get('wind_prefer', [])[:6]} "
        f"rotation_watch={payload.get('rotation_watch', [])[:6]} "
        f"counts={payload['counts']}",
        flush=True,
    )
    if not payload["prefer"] and not payload["avoid"]:
        print("WARN: empty prefer/avoid — API 可能无数据", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
