#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 MCP 导出的单票资金流 JSON 片段合并进 fund_flow_history.stock_sdk.json。

用法（Cursor Agent 拉完后）:
  python scripts/pull_fundflow_via_mcp_batch.py data/mcp_ff_*.json
  python scripts/pull_fundflow_via_mcp_batch.py --merge-to-prod
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "fund_flow_history.stock_sdk.json"
PROD = ROOT / "data" / "fund_flow_history.json"
BACKUP = ROOT / "data" / "fund_flow_history.sina_backup.json"


def bare(code: str) -> str:
    return str(code or "").lower().replace("sh", "").replace("sz", "").replace("bj", "")[-6:]


def parse_one(obj, default_code: str | None = None) -> tuple[str, dict]:
    if isinstance(obj, dict) and "data" in obj and isinstance(obj["data"], list):
        rows = obj["data"]
        code = bare(obj.get("symbol") or obj.get("code") or default_code or "")
    elif isinstance(obj, list):
        rows = obj
        code = bare(default_code or "")
    else:
        raise ValueError("unsupported json shape")
    hist = {}
    for r in rows:
        d = str(r.get("date", ""))[:10]
        v = r.get("mainNetInflow")
        if d and v is not None:
            hist[d] = float(v)
    if not code and rows:
        # allow filename to carry code
        pass
    return code, hist


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--merge-to-prod", action="store_true", help="备份新浪库并用 stock_sdk 库替换 prod")
    ap.add_argument("--code", default="")
    args = ap.parse_args()

    data = {}
    if OUT.exists():
        data = json.loads(OUT.read_text(encoding="utf-8"))

    for fp in args.files:
        p = Path(fp)
        obj = json.loads(p.read_text(encoding="utf-8"))
        code_guess = bare(args.code) or bare(p.stem.replace("mcp_ff_", ""))
        code, hist = parse_one(obj, code_guess)
        if not code:
            print("skip no-code", p)
            continue
        data[code] = hist
        print(f"  {code}: {len(hist)} days")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print("saved", OUT, "stocks", len(data))

    if args.merge_to_prod:
        if PROD.exists() and not BACKUP.exists():
            BACKUP.write_text(PROD.read_text(encoding="utf-8"), encoding="utf-8")
            print("backed up sina ->", BACKUP)
        # 合并：sdk 覆盖，缺的保留 sina
        prod = json.loads(PROD.read_text(encoding="utf-8")) if PROD.exists() else {}
        merged = dict(prod)
        merged.update(data)
        PROD.write_text(json.dumps(merged, ensure_ascii=False), encoding="utf-8")
        print("merged into", PROD, "stocks", len(merged))


if __name__ == "__main__":
    main()
