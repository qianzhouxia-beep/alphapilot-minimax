#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 mootdx finance 缓存/接口生成 fundamental_data.json，供 train_v25 / vm25_scorer 使用。

用法:
  python3 scripts/build_fundamental_data.py
  python3 scripts/build_fundamental_data.py --refresh-missing
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path("/home/ubuntu/alphapilot")
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from enriched_data import get_mootdx_finance_fundamentals  # noqa: E402
from data_fetcher import get_stock_list  # noqa: E402


def bare(sym: str) -> str:
    s = str(sym).strip()
    if "." in s:
        s = s.split(".")[0]
    return s.zfill(6)[-6:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--refresh-missing",
        action="store_true",
        help="对缓存未命中的票再拉一次 mootdx",
    )
    args = ap.parse_args()

    stocks = get_stock_list()
    symbols = [bare(s) for s in stocks["symbol"].tolist()]
    cache_dir = ROOT / "output" / ".finance_cache"

    out: dict = {}
    miss = []
    for i, sym in enumerate(symbols):
        fu = None
        if not args.refresh_missing:
            # 优先走 enriched 接口（自带缓存）
            fu = get_mootdx_finance_fundamentals(sym)
        else:
            cp = cache_dir / f"{sym}.json"
            if cp.exists():
                fu = get_mootdx_finance_fundamentals(sym)
            else:
                fu = get_mootdx_finance_fundamentals(sym)
        if fu and (
            abs(float(fu.get("eps") or 0)) > 1e-12
            or abs(float(fu.get("revenue") or 0)) > 1e-12
            or abs(float(fu.get("bps") or 0)) > 1e-12
            or abs(float(fu.get("roe") or 0)) > 1e-12
        ):
            out[sym] = {
                "eps": float(fu.get("eps") or 0),
                "revenue": float(fu.get("revenue") or 0),
                "net_profit": float(fu.get("net_profit") or 0),
                "bps": float(fu.get("bps") or 0),
                "roe": float(fu.get("roe") or 0),
                "profit_margin": float(fu.get("profit_margin") or 0),
                "revenue_yoy": float(fu.get("revenue_yoy") or 0),
                "net_profit_yoy": float(fu.get("net_profit_yoy") or 0),
                "gross_margin": float(fu.get("gross_margin") or 0),
                # pe/pb 由 features_v2 用 close/eps、close/bps 动态算
            }
        else:
            miss.append(sym)
        if (i + 1) % 500 == 0:
            print(f"  {i+1}/{len(symbols)} ok={len(out)} miss={len(miss)}", flush=True)

    path = ROOT / "fundamental_data.json"
    path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    # 同步一份到 data/
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "fundamental_data.json").write_text(
        json.dumps(out, ensure_ascii=False), encoding="utf-8"
    )
    print(
        f"saved {path} n={len(out)} / {len(symbols)} "
        f"({len(out)/max(len(symbols),1):.1%}) miss={len(miss)}"
    )


if __name__ == "__main__":
    main()
