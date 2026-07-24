#!/usr/bin/env python3
"""用 stock-sdk/东财资金流覆盖新浪库；缺票保留新浪。先备份 sina。"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SINA = ROOT / "data" / "fund_flow_history.json"
EM = ROOT / "data" / "fund_flow_history.stock_sdk.json"
PROG = ROOT / "data" / "fund_flow_stock_sdk_progress.json"
BACKUP = ROOT / "data" / "fund_flow_history.sina_backup.json"


def load_em():
    if EM.exists():
        return json.loads(EM.read_text(encoding="utf-8"))
    if PROG.exists():
        return json.loads(PROG.read_text(encoding="utf-8")).get("data") or {}
    return {}


def main():
    em = load_em()
    sina = json.loads(SINA.read_text(encoding="utf-8")) if SINA.exists() else {}
    if SINA.exists() and not BACKUP.exists():
        BACKUP.write_text(SINA.read_text(encoding="utf-8"), encoding="utf-8")
        print("backup", BACKUP)
    merged = dict(sina)
    overwritten = 0
    for k, v in em.items():
        if isinstance(v, dict) and v:
            merged[k] = v
            overwritten += 1
    SINA.write_text(json.dumps(merged, ensure_ascii=False), encoding="utf-8")
    depths = [len(v) for v in merged.values() if isinstance(v, dict)]
    mean = sum(depths) / len(depths) if depths else 0
    print(
        {
            "merged_stocks": len(merged),
            "em_overwritten": overwritten,
            "sina_kept": len(merged) - overwritten,
            "mean_depth": round(mean, 1),
            "out": str(SINA),
        }
    )


if __name__ == "__main__":
    main()
