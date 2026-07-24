#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盘中万得精度刷新：板块流 + 个股 B′。

用法:
  python3 scripts/refresh_wind_intraday.py --session midday
  python3 scripts/refresh_wind_intraday.py --session pre_eod
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str], timeout: int = 900) -> int:
    print("+", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=str(ROOT), timeout=timeout)
    return int(r.returncode)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", choices=["midday", "pre_eod", "close"], required=True)
    ap.add_argument("--board-only", action="store_true")
    ap.add_argument("--stocks-only", action="store_true")
    ap.add_argument("--stock-limit", type=int, default=80)
    args = ap.parse_args()

    py = sys.executable
    rc = 0

    if not args.stocks_only:
        code = run(
            [
                py,
                "-u",
                "scripts/fetch_wind_board_flow.py",
                "--session",
                args.session if args.session != "close" else "close",
                "--sleep",
                "0.2",
            ]
        )
        if code != 0:
            rc = code

    if not args.board_only:
        code = run(
            [
                py,
                "-u",
                "scripts/enrich_candidates_wind.py",
                "--limit",
                str(max(1, args.stock_limit)),
                "--session",
                args.session,
                "--sleep",
                "0.3",
            ],
            timeout=600,
        )
        if code != 0:
            rc = code

    print(f"refresh_wind_intraday session={args.session} rc={rc}", flush=True)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
