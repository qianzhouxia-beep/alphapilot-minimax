#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""外盘/隔夜数据巡检（供 WorkBuddy 每日执行）。

用法:
  python3 -u scripts/check_overnight_freshness.py
  python3 -u scripts/check_overnight_freshness.py --repair
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repair", action="store_true", help="不新鲜则重拉 us_enhanced + overnight")
    ap.add_argument("--max-age-hours", type=float, default=10.0)
    args = ap.parse_args()

    from overnight_sentiment import check_overnight_freshness, get_full_overnight_data

    info = check_overnight_freshness(max_age_hours=args.max_age_hours)
    print(json.dumps(info, ensure_ascii=False, indent=2), flush=True)

    if info.get("ok"):
        print("OVERNIGHT_OK", flush=True)
        return 0

    print("OVERNIGHT_FAIL", flush=True)
    if not args.repair:
        return 2

    print("▶ repair: us_enhanced_collector.py", flush=True)
    subprocess.run(
        [sys.executable, "-u", str(ROOT / "us_enhanced_collector.py")],
        cwd=str(ROOT),
        timeout=180,
    )
    print("▶ repair: get_full_overnight_data()", flush=True)
    get_full_overnight_data()
    info2 = check_overnight_freshness(max_age_hours=args.max_age_hours)
    print(json.dumps(info2, ensure_ascii=False, indent=2), flush=True)
    if info2.get("ok"):
        print("OVERNIGHT_REPAIRED_OK", flush=True)
        return 0
    print("OVERNIGHT_REPAIR_STILL_FAIL", flush=True)
    out = ROOT / "output" / "overnight_alerts.json"
    out.write_text(json.dumps(info2, ensure_ascii=False, indent=2), encoding="utf-8")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
