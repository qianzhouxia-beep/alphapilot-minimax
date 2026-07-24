#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盘中软门控：实时行情 + 资金流排名 → 分数软加权，不硬杀。

缓存由 scripts/refresh_intraday_soft_gate.mjs（stock-sdk / MCP 同源）刷新:
  data/intraday_soft_gate.json
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "data" / "intraday_soft_gate.json"


def _bare(sym: str) -> str:
    s = str(sym or "").lower().replace("sh", "").replace("sz", "").replace("bj", "")
    return s[-6:]


def _load_cache(path: Path | None = None) -> dict:
    p = path or CACHE
    if not p.exists():
        alt = Path("data/intraday_soft_gate.json")
        p = alt if alt.exists() else p
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def fund_rank_bonus(rank: int | None, universe: int = 5000) -> float:
    if rank is None or rank <= 0:
        return 0.0
    pct = rank / max(universe, 1)
    x = 1.0 - pct
    return float(0.05 * math.tanh(3.0 * (x - 0.5) * 2))


def main_net_bonus(main_net: float | None) -> float:
    if main_net is None:
        return 0.0
    return float(0.04 * math.tanh(float(main_net) / 5e8))


def quote_soft_adjust(chg: float | None, turnover: float | None = None) -> float:
    adj = 0.0
    if chg is not None:
        if chg <= -5:
            adj -= 0.04
        elif chg >= 8:
            adj -= 0.02
        elif 0 <= chg <= 3:
            adj += 0.01
    if turnover is not None:
        if turnover < 1:
            adj -= 0.01
        elif 2 <= turnover <= 15:
            adj += 0.01
        elif turnover > 30:
            adj -= 0.02
    return adj


def apply_soft_intraday_gate(
    items: list[dict[str, Any]],
    cache_path: Path | None = None,
    mode: str = "soft",
) -> list[dict[str, Any]]:
    if not items:
        return items
    cache = _load_cache(cache_path)
    rank_today = cache.get("rank_today") or {}
    rank_5d = cache.get("rank_5day") or {}
    quotes = cache.get("quotes") or {}

    out = []
    for r in items:
        code = _bare(r.get("symbol") or r.get("code") or "")
        base = float(r.get("score", 0) or 0)
        rt = rank_today.get(code) or {}
        r5 = rank_5d.get(code) or {}
        q = quotes.get(code) or {}

        b_rank = fund_rank_bonus(rt.get("rank"))
        b_rank5 = 0.5 * fund_rank_bonus(r5.get("rank"))
        b_net = main_net_bonus(rt.get("mainNetInflow"))
        chg = q.get("changePercent", q.get("change_pct", rt.get("changePercent")))
        to = q.get("turnover", q.get("turnoverRate"))
        b_q = quote_soft_adjust(
            float(chg) if chg is not None else None,
            float(to) if to is not None else None,
        )
        bonus = b_rank + b_rank5 + b_net + b_q
        r = dict(r)
        r["score_raw_pre_soft"] = round(base, 4)
        r["soft_intraday_bonus"] = round(bonus, 4)
        r["fund_rank_today"] = rt.get("rank")
        r["fund_rank_5d"] = r5.get("rank")
        r["main_net_today"] = rt.get("mainNetInflow")
        if chg is not None:
            r["change_pct"] = float(chg)
        r["score"] = round(max(0.01, base + bonus), 4)
        r["soft_gate_mode"] = mode
        out.append(r)

    out.sort(key=lambda x: float(x.get("score", 0) or 0), reverse=True)
    return out


if __name__ == "__main__":
    demo = [{"symbol": "600519", "score": 0.7}, {"symbol": "000858", "score": 0.65}]
    print(json.dumps(apply_soft_intraday_gate(demo), ensure_ascii=False, indent=2))
