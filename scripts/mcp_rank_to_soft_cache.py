#!/usr/bin/env python3
"""把 MCP get_fund_flow_rank 原始 JSON 转成 data/intraday_soft_gate.json。"""
from __future__ import annotations
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def bare(c):
    return str(c or "").lower().replace("sh","").replace("sz","").replace("bj","")[-6:]

def to_map(items):
    m = {}
    for i, it in enumerate(items or []):
        code = bare(it.get("code") or it.get("symbol"))
        if not code: continue
        m[code] = {
            "rank": i + 1,
            "name": it.get("name"),
            "mainNetInflow": it.get("mainNetInflow"),
            "mainNetInflowPercent": it.get("mainNetInflowPercent"),
            "changePercent": it.get("changePercent"),
            "price": it.get("price"),
        }
    return m

def main():
    today_path = Path(sys.argv[1])
    d5_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    today = json.loads(today_path.read_text(encoding="utf-8"))
    if isinstance(today, dict) and "data" in today:
        today = today["data"]
    rank_today = to_map(today)
    rank_5day = {}
    if d5_path and d5_path.exists():
        d5 = json.loads(d5_path.read_text(encoding="utf-8"))
        if isinstance(d5, dict) and "data" in d5:
            d5 = d5["data"]
        rank_5day = to_map(d5)
    out = {
        "source": "mcp-stock-sdk",
        "n_rank_today": len(rank_today),
        "n_rank_5day": len(rank_5day),
        "n_quotes": 0,
        "rank_today": rank_today,
        "rank_5day": rank_5day,
        "quotes": {},
    }
    dest = ROOT / "data" / "intraday_soft_gate.json"
    dest.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print("saved", dest, out["n_rank_today"], out["n_rank_5day"])

if __name__ == "__main__":
    main()
