#!/usr/bin/env python3
"""A 股板块看板（通达信）。

数据源（不用东财）:
  - data/fund_flow_history.json   ← tdxhub 个股主力净额
  - data/stock_industry_map.json  ← 通达信 F10 行业映射

周期: 今日(1日) / 5日 / 10日 / 20日 / 60日 —— 按交易日条数聚合到 industry_l1。
"""
from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
DATA = ROOT / "data"
SNAP = OUT / "sector_rotation_snapshot.json"

PERIODS = ("today", "5day", "10day", "20day", "60day")
PERIOD_DAYS = {"today": 1, "5day": 5, "10day": 10, "20day": 20, "60day": 60}
PERIOD_LABELS = {
    "today": "今日",
    "5day": "5日",
    "10day": "10日",
    "20day": "20日",
    "60day": "60日",
}


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        import json

        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _bare(code: str) -> str:
    s = str(code or "").lower().replace("sh", "").replace("sz", "").replace("bj", "")
    return "".join(ch for ch in s if ch.isdigit())[-6:]


def _sum_stock_flow(hist: dict, days: int) -> float:
    if not isinstance(hist, dict) or days <= 0:
        return 0.0
    keys = sorted((k for k in hist.keys() if k), reverse=True)[:days]
    total = 0.0
    for k in keys:
        try:
            total += float(hist[k] or 0)
        except Exception:
            continue
    return total


def _latest_asof(ff: dict) -> Optional[str]:
    latest = None
    for hist in ff.values():
        if not isinstance(hist, dict) or not hist:
            continue
        d = max(hist.keys())
        if latest is None or d > latest:
            latest = d
    return latest


def aggregate_tdx_sectors(days: int = 1, level: str = "l1") -> tuple[list[dict], dict]:
    """通达信个股资金 → 行业聚合。返回 (rows, meta)。"""
    ff = _load_json(DATA / "fund_flow_history.json") or {}
    ind_map = _load_json(DATA / "stock_industry_map.json") or {}
    if not isinstance(ff, dict) or not isinstance(ind_map, dict):
        return [], {"error": "missing fund_flow_history or stock_industry_map"}

    field = {
        "l1": "industry_l1",
        "l2": "industry_l2",
        "l3": "industry_l3",
        "leaf": "industry",
    }.get(level, "industry_l1")

    buckets: dict[str, float] = defaultdict(float)
    stock_n: dict[str, int] = defaultdict(int)
    used = 0

    for code, hist in ff.items():
        if not isinstance(hist, dict):
            continue
        bare = _bare(code)
        meta = ind_map.get(bare) or ind_map.get(code) or {}
        if not isinstance(meta, dict):
            continue
        name = str(meta.get(field) or meta.get("industry_l1") or meta.get("industry") or "").strip()
        if not name:
            continue
        net = _sum_stock_flow(hist, days)
        buckets[name] += net
        stock_n[name] += 1
        used += 1

    rows = []
    for name, net in buckets.items():
        rows.append(
            {
                "name": name,
                "net_yi": round(net / 1e8, 2),
                "change_pct": None,  # 资金看板以净额为主；涨跌另接指数时可补
                "stock_count": stock_n[name],
                "source": "tdx",
            }
        )
    rows.sort(key=lambda x: -x["net_yi"])

    # 简单锋面：流入前 20% allow，流出后 20% deny
    n = len(rows)
    allow_n = max(1, n // 5) if n else 0
    deny_n = max(1, n // 5) if n else 0
    for i, r in enumerate(rows):
        if i < allow_n and r["net_yi"] > 0:
            r["status"] = "allow"
        elif i >= n - deny_n and r["net_yi"] < 0:
            r["status"] = "deny"
        else:
            r["status"] = "neutral"

    meta = {
        "provider": "通达信 tdxhub",
        "level": field,
        "days": days,
        "stocks_used": used,
        "sector_count": len(rows),
        "asof": _latest_asof(ff),
        "fund_flow_mtime": (
            datetime.fromtimestamp((DATA / "fund_flow_history.json").stat().st_mtime).isoformat(
                timespec="seconds"
            )
            if (DATA / "fund_flow_history.json").exists()
            else None
        ),
        "industry_map_mtime": (
            datetime.fromtimestamp((DATA / "stock_industry_map.json").stat().st_mtime).isoformat(
                timespec="seconds"
            )
            if (DATA / "stock_industry_map.json").exists()
            else None
        ),
    }
    return rows, meta


def _flow_bars_and_scatter(industries: list[dict]) -> tuple[list[dict], list[dict]]:
    top = industries[:12]
    bottom = list(reversed(industries[-12:])) if len(industries) >= 12 else list(reversed(industries))
    flow_bars = [
        {"name": x["name"], "net_yi": x["net_yi"], "change_pct": x.get("change_pct"), "status": x.get("status")}
        for x in top
    ]
    seen = {t["name"] for t in top}
    flow_bars += [
        {"name": x["name"], "net_yi": x["net_yi"], "change_pct": x.get("change_pct"), "status": x.get("status")}
        for x in bottom
        if x["name"] not in seen
    ]

    scatter_pool = industries[:25] + industries[-25:]
    seen2: set[str] = set()
    scatter = []
    for x in scatter_pool:
        if x["name"] in seen2:
            continue
        seen2.add(x["name"])
        # 散点 Y：用相对排名映射到「强弱分」避免无涨跌时全挤在 0
        # 仍保留 change_pct 字段；前端无涨跌时用 rank_score
        scatter.append(
            {
                "name": x["name"],
                "net_yi": x["net_yi"],
                "change_pct": x.get("change_pct"),
                "rank_score": round(50 - (x["rank"] - 1) / max(len(industries) - 1, 1) * 100, 1),
                "status": x.get("status"),
            }
        )
    return flow_bars, scatter


def _build_analysis(industries: list[dict], summary: dict, period: str) -> dict:
    if not industries:
        return {"headline": "暂无通达信板块资金数据", "bullets": [], "watch": [], "avoid": []}

    top = industries[:5]
    bottom = list(reversed(industries[-5:]))
    label = PERIOD_LABELS.get(period, period)
    net = summary.get("net_yi") or 0
    tone = "净流入" if net >= 0 else "净流出"
    headline = f"通达信·{label} 一级行业整体{tone} {net:+.1f} 亿"

    top3 = "、".join(f"{x['name']}({x['net_yi']:+.1f}亿)" for x in top[:3])
    bot3 = "、".join(f"{x['name']}({x['net_yi']:+.1f}亿)" for x in bottom[:3])
    bullets = [
        f"流入前三：{top3}",
        f"流出前三：{bot3}",
        f"锋面 {summary.get('allow', 0)} 个 · 回避 {summary.get('deny', 0)} 个（按净额分位）",
    ]
    return {
        "headline": headline,
        "bullets": bullets,
        "watch": [{"name": x["name"], "net_yi": x["net_yi"]} for x in top[:4]],
        "avoid": [{"name": x["name"], "net_yi": x["net_yi"]} for x in bottom[:4]],
    }


def build_dashboard(force_refresh: bool = False, period: str = "today") -> dict:
    """force_refresh 对通达信聚合是即时重算（读本地 JSON，无需打外网）。"""
    period = period if period in PERIODS else "today"
    days = PERIOD_DAYS[period]
    rows, tdx_meta = aggregate_tdx_sectors(days=days, level="l1")

    industries = []
    for i, r in enumerate(rows):
        industries.append(
            {
                "name": r["name"],
                "net_yi": r["net_yi"],
                "change_pct": r.get("change_pct"),
                "rank": i + 1,
                "status": r.get("status", "neutral"),
                "stock_count": r.get("stock_count"),
            }
        )

    flow_bars, scatter = _flow_bars_and_scatter(industries)
    allow_n = sum(1 for x in industries if x["status"] == "allow")
    deny_n = sum(1 for x in industries if x["status"] == "deny")
    neutral_n = len(industries) - allow_n - deny_n
    inflow_sum = round(sum(x["net_yi"] for x in industries if x["net_yi"] > 0), 2)
    outflow_sum = round(sum(x["net_yi"] for x in industries if x["net_yi"] < 0), 2)
    summary = {
        "industry_count": len(industries),
        "allow": allow_n,
        "deny": deny_n,
        "neutral": neutral_n,
        "inflow_yi": inflow_sum,
        "outflow_yi": outflow_sum,
        "net_yi": round(inflow_sum + outflow_sum, 2),
    }
    analysis = _build_analysis(industries, summary, period)

    # 概念锋面仍可读本地 snapshot（若有）；没有则空
    snap = _load_json(SNAP) or {}
    concept_top = snap.get("concept_top10") or []

    return {
        "ts": tdx_meta.get("asof") or time.strftime("%Y-%m-%dT%H:%M:%S"),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "period": period,
        "period_label": PERIOD_LABELS[period],
        "periods": [{"id": p, "label": PERIOD_LABELS[p]} for p in PERIODS],
        "provider": "通达信",
        "has_3day": True,
        "has_concept": bool(concept_top),
        "summary": summary,
        "flow_bars": flow_bars,
        "scatter": scatter,
        "analysis": analysis,
        "today_top10": industries[:10],
        "today_bottom10": industries[-10:] if industries else [],
        "concept_top10": concept_top,
        "allow": [x for x in industries if x["status"] == "allow"][:20],
        "deny": [x for x in industries if x["status"] == "deny"][:20],
        "industries": industries,
        "meta": {
            **tdx_meta,
            "force_refresh": force_refresh,
            "period": period,
            "data_source": "tdx fund_flow_history × stock_industry_map(L1)",
            "update_cadence": "通达信资金流由交易日盘后脚本 pull_fundflow_tdx 更新；看板刷新=本地即时重算聚合，不请求东财",
            "ports": {
                "api_uvicorn": "127.0.0.1:8000",
                "nginx_public": "150.158.100.236:80",
                "zeabur_proxy": "https://alphapilot.api-tokenmaster.com → :80 → uvicorn :8000",
                "tdxhub": "http://tdxhub.icfqs.com:7615",
            },
            "refresh_effect": "手动刷新会重新读取通达信资金/行业映射并按所选周期聚合；不会调用东财接口",
        },
    }


def get_sector_detail(name: str, period: str = "today") -> Optional[dict]:
    dash = build_dashboard(force_refresh=False, period=period)
    for it in dash.get("industries") or []:
        if it.get("name") == name:
            return {
                "sector": it,
                "period": period,
                "provider": "通达信",
                "analysis": dash.get("analysis"),
                "peers_in_flow": [
                    x
                    for x in (dash.get("industries") or [])
                    if x.get("status") == it.get("status") and x.get("name") != name
                ][:8],
                "ts": dash.get("ts"),
            }
    return None
