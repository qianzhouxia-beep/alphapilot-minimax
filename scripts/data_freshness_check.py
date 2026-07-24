#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盘后/盘中数据新鲜度检测，供 WorkBuddy 日检与 cron 告警。

检查:
  - sector_flow_today / concept_flow_today asof
  - fund_flow_history 最新交易日
  - wind_candidate_flow asof
  - kline / chip 文件 mtime
  - 可选：要求 asof == 今天

退出码: 0 全部通过；1 有失败；2 仅警告

用法:
  python3 scripts/data_freshness_check.py
  python3 scripts/data_freshness_check.py --require-today --json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _mtime(p: Path) -> str | None:
    if not p.exists():
        return None
    return datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")


def _load(p: Path):
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def fund_flow_max_date(path: Path) -> str | None:
    d = _load(path)
    if not isinstance(d, dict):
        return None
    mx = None
    for _code, hist in d.items():
        if not isinstance(hist, dict):
            continue
        for k in hist.keys():
            if isinstance(k, str) and len(k) >= 10 and k[0:4].isdigit():
                if mx is None or k > mx:
                    mx = k
    return mx


def check(require_today: bool) -> dict:
    today = _today()
    checks = []

    def add(name, status, detail):
        checks.append({"name": name, "status": status, "detail": detail})

    # sector flows
    for fname in ("sector_flow_today.json", "concept_flow_today.json"):
        p = ROOT / "data" / fname
        raw = _load(p)
        if raw is None:
            add(fname, "fail", "missing or corrupt")
            continue
        asof = str(raw.get("asof") or "")
        n = raw.get("total") or len(raw.get("data") or [])
        if require_today and asof != today:
            add(fname, "fail", f"asof={asof} expect={today} n={n} mtime={_mtime(p)}")
        elif asof:
            add(fname, "ok" if asof == today else "warn", f"asof={asof} n={n} mtime={_mtime(p)}")
        else:
            add(fname, "warn", f"no asof n={n} mtime={_mtime(p)}")

    # stock fund history
    ff = ROOT / "data" / "fund_flow_history.json"
    mx = fund_flow_max_date(ff)
    if mx is None:
        add("fund_flow_history.json", "fail", "missing")
    elif require_today and mx < today:
        # 个股资金流源站常 T-1，盘后当天允许昨天
        hour = datetime.now().hour
        if hour >= 18 and mx < today:
            add("fund_flow_history.json", "warn", f"max_date={mx} mtime={_mtime(ff)} (期望贴近今日)")
        else:
            add("fund_flow_history.json", "ok", f"max_date={mx} mtime={_mtime(ff)}")
    else:
        add("fund_flow_history.json", "ok", f"max_date={mx} mtime={_mtime(ff)}")

    # wind candidates
    wf = ROOT / "data" / "wind_candidate_flow.json"
    wr = _load(wf)
    if wr is None:
        add("wind_candidate_flow.json", "warn", "missing (Wind 未跑或 Key 未配)")
    else:
        asof = str(wr.get("asof") or "")
        n = wr.get("n")
        st = "ok" if (not require_today or asof == today) else "fail"
        if asof != today and require_today:
            st = "fail"
        elif asof != today:
            st = "warn"
        add("wind_candidate_flow.json", st, f"asof={asof} n={n} errors={wr.get('n_error')} mtime={_mtime(wf)}")

    # kline / chip
    for rel in (
        "data/kline_cache/kline_all.parquet",
        "chip_data_all.json",
        "data/chip_data_all.json",
    ):
        p = ROOT / rel
        if p.exists():
            add(rel, "ok", f"mtime={_mtime(p)} size={p.stat().st_size}")
        else:
            add(rel, "warn" if "chip" in rel else "fail", "missing")

    fails = sum(1 for c in checks if c["status"] == "fail")
    warns = sum(1 for c in checks if c["status"] == "warn")
    return {
        "date": today,
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "fails": fails,
        "warns": warns,
        "checks": checks,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--require-today", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--write", default="", help="写入 JSON 路径，默认 output/data_freshness.json")
    args = ap.parse_args()

    report = check(args.require_today)
    out = Path(args.write) if args.write else ROOT / "output" / "data_freshness.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"freshness fails={report['fails']} warns={report['warns']} -> {out}", flush=True)
        for c in report["checks"]:
            print(f"  [{c['status']}] {c['name']}: {c['detail']}", flush=True)

    if report["fails"]:
        return 1
    if report["warns"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
