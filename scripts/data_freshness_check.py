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

    # kline / chip — v2: 校验数据实际日期(不只 mtime)
    import pandas as _pd
    _today_d = _pd.Timestamp(today).date()

    def _latest_kline_date(path):
        try:
            df = _pd.read_parquet(path)
            if "date" in df.columns:
                return _pd.to_datetime(df["date"]).max()
        except Exception:
            pass
        return None

    def _kline_status(p, rel):
        if not p.exists():
            return "fail", "missing"
        d = _latest_kline_date(p)
        if d is None:
            return "warn", f"mtime={_mtime(p)} 无date列(旧格式?)"
        d_date = _pd.Timestamp(d).date()
        gap = (_today_d - d_date).days
        detail = f"最新={d_date} mtime={_mtime(p)} gap={gap}天"
        if gap <= 1:
            return "ok", detail
        if gap <= 3:
            return "warn", f"stale {detail}"
        return "fail", f"STALE {detail}"

    for rel in (
        "kline_all.parquet",                      # 根目录(16:00 东财源写入)
        "data/kline_cache/kline_all.parquet",     # 缓存(软链同源)
        "chip_data_all.json",
        "data/chip_data_all.json",
    ):
        p = ROOT / rel
        st, det = _kline_status(p, rel) if "parquet" in rel else ("ok", "")
        if "parquet" in rel:
            add(rel, st, det)
        else:
            if p.exists():
                add(rel, "ok", f"mtime={_mtime(p)} size={p.stat().st_size}")
            else:
                add(rel, "warn", "missing")

    # 核心输出文件: 每日推荐 + 盘中选股 必须贴近今日
    for rel in ("output/daily_recommend.json", "output/morning_live_picks.json"):
        p = ROOT / rel
        if not p.exists():
            add(rel, "fail", "missing")
            continue
        try:
            import json as _json
            dd = _json.load(open(p))
            _asof = None
            if isinstance(dd, dict):
                _asof = dd.get("asof") or dd.get("generated_at") or dd.get("updated_at")
            if _asof:
                _asd = _pd.Timestamp(str(_asof)[:10]).date()
                _gap = (_today_d - _asd).days
                st = "ok" if _gap <= 1 else ("warn" if _gap <= 3 else "fail")
                add(rel, st, f"asof={_asof[:10]} gap={_gap}天 mtime={_mtime(p)}")
            else:
                add(rel, "warn", f"无asof mtime={_mtime(p)}")
        except Exception as e:
            add(rel, "warn", f"读取失败 {e}")

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
