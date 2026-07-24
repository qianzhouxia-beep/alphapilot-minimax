#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""落盘数据新鲜度监测：预警 + 自动修复（默认不阻断交易）。

用法:
  python3 -u scripts/data_readiness_gate.py
  python3 -u scripts/data_readiness_gate.py --repair   # 失败项尝试自动重拉
  python3 -u scripts/data_readiness_gate.py --fail     # 仅运维：关键失败 exit 2
  python3 -u scripts/data_readiness_gate.py --block-on-fail  # 可选：写空 picks（默认关闭）

产物:
  output/data_readiness.json
  output/data_alerts.json          # 有问题时更新，供人工查看
  output/logs/data_alerts.log      # 追加告警流水
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(os.environ.get("ALPHAPILOT_ROOT", "/home/ubuntu/alphapilot"))
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)

OUT_PATH = ROOT / "output" / "data_readiness.json"
ALERT_PATH = ROOT / "output" / "data_alerts.json"
ALERT_LOG = ROOT / "output" / "logs" / "data_alerts.log"
PICKS_PATH = ROOT / "output" / "morning_live_picks.json"


def _now() -> datetime:
    return datetime.now()


def _age_hours(path: Path) -> float | None:
    if not path.exists():
        return None
    return (_now().timestamp() - path.stat().st_mtime) / 3600.0


def _size(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0


def _weekday_slack_hours() -> float:
    wd = _now().weekday()
    if wd == 0:
        return 72.0
    if wd >= 5:
        return 96.0
    return 36.0


def check_file(
    rel: str,
    *,
    critical: bool,
    max_age_h: float | None,
    min_bytes: int = 100,
    alt: str | None = None,
) -> dict:
    path = ROOT / rel
    if (not path.exists() or path.stat().st_size < min_bytes) and alt:
        path = ROOT / alt
    age = _age_hours(path)
    exists = path.exists() and _size(path) >= min_bytes
    stale = bool(exists and max_age_h is not None and age is not None and age > max_age_h)
    ok = exists and not stale
    level = "ok" if ok else ("fail" if critical else "warn")
    reason = None
    if not exists:
        reason = "missing_or_tiny"
    elif stale:
        reason = f"stale_{age:.1f}h>{max_age_h}h"
    return {
        "path": str(path.relative_to(ROOT)) if exists and ROOT in path.parents else rel,
        "critical": critical,
        "ok": ok,
        "level": level,
        "exists": exists,
        "bytes": _size(path) if exists else 0,
        "age_hours": None if age is None else round(age, 2),
        "max_age_hours": max_age_h,
        "reason": reason,
        "repair": None,
    }


def _allowed_kline_lag_days(today, hour: int) -> int:
    """收盘后要求更严：避免「空更新成功」把过期K线当成 ready。

    - 周一：允许周末缺口（最多 3 天到上周五）
    - 周二～周五：盘后(≥16点) lag 必须为 0；盘前允许 1（昨收）
    - 周末：允许到上周五（Sat=1, Sun=2）
    """
    wd = today.weekday()  # Mon=0
    if wd == 5:  # Sat
        return 1
    if wd == 6:  # Sun
        return 2
    if wd == 0:  # Mon
        return 3 if hour < 16 else 0
    # Tue-Fri
    return 0 if hour >= 16 else 1


def check_kline_max_date(max_lag_days: int | None = None) -> dict:
    p = ROOT / "data/kline_cache/kline_all.parquet"
    out = {
        "path": "data/kline_cache/kline_all.parquet",
        "critical": True,
        "ok": False,
        "level": "fail",
        "max_date": None,
        "reason": None,
        "repair": "kline",
    }
    if not p.exists():
        out["reason"] = "missing"
        return out
    try:
        import pandas as pd

        df = pd.read_parquet(p, columns=["date"])
        mx = str(df["date"].astype(str).str[:10].max())
        out["max_date"] = mx
        now = _now()
        today = now.date()
        d = datetime.strptime(mx, "%Y-%m-%d").date()
        lag = (today - d).days
        out["lag_days"] = lag
        allow = (
            max_lag_days
            if max_lag_days is not None
            else _allowed_kline_lag_days(today, now.hour)
        )
        out["allow_lag_days"] = allow
        if lag <= allow:
            out["ok"] = True
            out["level"] = "ok"
            out["repair"] = None
        else:
            out["reason"] = f"kline_max_date_lag_{lag}d_allow_{allow}"
    except Exception as e:
        out["reason"] = f"read_error:{e}"
    return out


def check_chip_asof_vs_kline() -> dict:
    """筹码快照日应与 K 线最新日一致（推演依赖 K 线）。"""
    out = {
        "path": "chip_data_all.json",
        "critical": True,
        "ok": False,
        "level": "fail",
        "chip_date": None,
        "kline_date": None,
        "reason": None,
        "repair": "chip",
    }
    chip_p = ROOT / "chip_data_all.json"
    if not chip_p.exists():
        chip_p = ROOT / "data" / "chip_data_all.json"
    kline_p = ROOT / "data/kline_cache/kline_all.parquet"
    if not chip_p.exists():
        out["reason"] = "chip_missing"
        return out
    if not kline_p.exists():
        out["reason"] = "kline_missing"
        out["repair"] = "kline"
        return out
    try:
        import pandas as pd

        raw = json.loads(chip_p.read_text(encoding="utf-8", errors="ignore"))
        dates = [
            str(v.get("date"))[:10]
            for v in raw.values()
            if isinstance(v, dict) and v.get("date")
        ]
        if not dates:
            out["reason"] = "chip_no_dates"
            return out
        # 众数日（多数票的最新交易日）
        from collections import Counter

        chip_d = Counter(dates).most_common(1)[0][0]
        kdf = pd.read_parquet(kline_p, columns=["date"])
        kline_d = str(kdf["date"].astype(str).str[:10].max())
        out["chip_date"] = chip_d
        out["kline_date"] = kline_d
        if chip_d == kline_d:
            out["ok"] = True
            out["level"] = "ok"
            out["repair"] = None
        else:
            out["reason"] = f"chip_asof_{chip_d}_ne_kline_{kline_d}"
    except Exception as e:
        out["reason"] = f"read_error:{e}"
    return out


def check_fund_flow_depth(min_median: int = 40) -> dict:
    p = ROOT / "data/fund_flow_history.json"
    out = {
        "path": "data/fund_flow_history.json",
        "critical": True,
        "ok": False,
        "level": "fail",
        "n_symbols": 0,
        "median_depth": 0,
        "reason": None,
        "repair": "fund_flow",
    }
    if not p.exists() or p.stat().st_size < 1000:
        out["reason"] = "missing_or_tiny"
        return out
    try:
        raw = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
        depths = [len(v) for v in raw.values() if isinstance(v, dict) and v]
        out["n_symbols"] = len(depths)
        if not depths:
            out["reason"] = "empty"
            return out
        import statistics

        med = float(statistics.median(depths))
        out["median_depth"] = round(med, 1)
        if len(depths) >= 1000 and med >= min_median:
            out["ok"] = True
            out["level"] = "ok"
            out["repair"] = None
        else:
            out["reason"] = f"shallow_or_few med={med} n={len(depths)}"
    except Exception as e:
        out["reason"] = f"read_error:{e}"
    return out


REPAIR_CMDS = {
    "fund_flow": f"{sys.executable} build_fund_flow_history.py",
    "kline": "python3 cache_kline.py update",
    "fundamentals": f"{sys.executable} scripts/build_fundamental_data.py",
    "chip": f"{sys.executable} -u scripts/pull_chip_from_kline.py --workers 1",
    "margin_event": f"{sys.executable} pull_margin_event_data.py",
    "lhb": f"{sys.executable} scripts/pull_lhb_history.py",
}


def build_report() -> dict:
    slack = _weekday_slack_hours()
    checks = {
        "models_meta": check_file(
            "models/v25_meta.json", critical=True, max_age_h=None, min_bytes=50
        ),
        "models_opt1": check_file(
            "models/v25_opt_ensemble_1.ubj", critical=True, max_age_h=None, min_bytes=1000
        ),
        "fund_flow_file": check_file(
            "data/fund_flow_history.json",
            critical=True,
            max_age_h=slack,
            min_bytes=10000,
        ),
        "fund_flow_depth": check_fund_flow_depth(),
        "kline_file": check_file(
            "data/kline_cache/kline_all.parquet",
            critical=True,
            max_age_h=slack + 24,
            min_bytes=100000,
        ),
        "kline_max_date": check_kline_max_date(),
        "chip": check_file(
            "chip_data_all.json",
            critical=True,
            max_age_h=72,
            min_bytes=10000,
            alt="data/chip_data_all.json",
        ),
        "chip_asof": check_chip_asof_vs_kline(),
        "fundamentals": check_file(
            "fundamental_data.json",
            critical=True,
            max_age_h=336,
            min_bytes=10000,
            alt="data/fundamental_data.json",
        ),
        "margin": check_file(
            "data/margin_data.json", critical=False, max_age_h=120, min_bytes=1000
        ),
        "event_forecast": check_file(
            "data/event_forecast.json", critical=False, max_age_h=168, min_bytes=100
        ),
        "lhb_history": check_file(
            "data/lhb_history.json", critical=False, max_age_h=120, min_bytes=100
        ),
    }
    # attach repair hints
    if checks["fund_flow_file"]["level"] != "ok" or checks["fund_flow_depth"]["level"] != "ok":
        checks["fund_flow_file"]["repair"] = "fund_flow"
        checks["fund_flow_depth"]["repair"] = "fund_flow"
    if checks["kline_file"]["level"] != "ok":
        checks["kline_file"]["repair"] = "kline"
    if checks["kline_max_date"]["level"] != "ok":
        checks["kline_max_date"]["repair"] = "kline"
    if checks["chip"]["level"] != "ok":
        checks["chip"]["repair"] = "chip"
    if checks["chip_asof"]["level"] != "ok":
        # 若 K 线也旧，先修 K 线
        if checks["kline_max_date"]["level"] != "ok":
            checks["chip_asof"]["repair"] = "kline"
        else:
            checks["chip_asof"]["repair"] = "chip"
    if checks["fundamentals"]["level"] != "ok":
        checks["fundamentals"]["repair"] = "fundamentals"
    if checks["margin"]["level"] != "ok":
        checks["margin"]["repair"] = "margin_event"
    if checks["event_forecast"]["level"] != "ok":
        checks["event_forecast"]["repair"] = "margin_event"
    if checks["lhb_history"]["level"] != "ok":
        checks["lhb_history"]["repair"] = "lhb"

    tmp = Path("/tmp/refresh_all_data.status")
    if tmp.exists():
        try:
            st = json.loads(tmp.read_text(encoding="utf-8"))
            age = _age_hours(tmp)
            ok_r = st.get("progress") == 100
            checks["refresh_status"] = {
                "path": str(tmp),
                "critical": False,
                "ok": ok_r,
                "level": "ok" if ok_r else "warn",
                "detail": st,
                "age_hours": None if age is None else round(age, 2),
                "reason": None if ok_r else (st.get("detail") or "refresh_not_ok"),
                "repair": None if ok_r else "full_refresh",
            }
        except Exception as e:
            checks["refresh_status"] = {
                "path": str(tmp),
                "critical": False,
                "ok": False,
                "level": "warn",
                "reason": f"parse_error:{e}",
                "repair": "full_refresh",
            }
    else:
        checks["refresh_status"] = {
            "path": "/tmp/refresh_all_data.status",
            "critical": False,
            "ok": False,
            "level": "warn",
            "reason": "missing",
            "repair": "full_refresh",
        }

    fails = [k for k, v in checks.items() if v.get("level") == "fail"]
    warns = [k for k, v in checks.items() if v.get("level") == "warn"]
    ready = len(fails) == 0
    return {
        "asof": _now().strftime("%Y-%m-%d %H:%M:%S"),
        "ready_for_trade": ready,
        "fail_count": len(fails),
        "warn_count": len(warns),
        "fails": fails,
        "warns": warns,
        "checks": checks,
        "policy": {
            "default": "alert + auto-repair; do NOT block trading unless --block-on-fail",
            "prefer": "server disk cache; live fetch only as supplement",
        },
    }


def emit_alert(report: dict, repaired: dict | None = None) -> None:
    """有问题才写预警；全绿则写 clear。"""
    ALERT_LOG.parent.mkdir(parents=True, exist_ok=True)
    issues = []
    for k in report.get("fails") or []:
        c = report["checks"][k]
        issues.append(
            {
                "key": k,
                "severity": "fail",
                "reason": c.get("reason"),
                "repair": c.get("repair"),
                "path": c.get("path"),
            }
        )
    for k in report.get("warns") or []:
        c = report["checks"][k]
        issues.append(
            {
                "key": k,
                "severity": "warn",
                "reason": c.get("reason") or str(c.get("detail") or "")[:120],
                "repair": c.get("repair"),
                "path": c.get("path"),
            }
        )
    alert = {
        "asof": report["asof"],
        "status": "ok" if not issues else ("critical" if report["fails"] else "warning"),
        "message": (
            "数据就绪"
            if not issues
            else f"数据异常 fail={len(report['fails'])} warn={len(report['warns'])}，请查看 issues"
        ),
        "issues": issues,
        "repaired": repaired or {},
        "readiness_file": str(OUT_PATH),
    }
    ALERT_PATH.write_text(json.dumps(alert, ensure_ascii=False, indent=2), encoding="utf-8")
    line = (
        f"{alert['asof']} [{alert['status']}] {alert['message']}"
        + (f" repaired={repaired}" if repaired else "")
        + "\n"
    )
    with ALERT_LOG.open("a", encoding="utf-8") as f:
        f.write(line)
    # 醒目打印
    if alert["status"] != "ok":
        print("=" * 60, flush=True)
        print(f"⚠️ 数据预警: {alert['message']}", flush=True)
        for it in issues:
            print(
                f"  - [{it['severity']}] {it['key']}: {it['reason']} → 修复动作={it['repair']}",
                flush=True,
            )
        print(f"详情: {ALERT_PATH}", flush=True)
        print("=" * 60, flush=True)
    else:
        print(f"✅ 数据预警清除: {ALERT_PATH}", flush=True)


def try_repair(report: dict) -> dict:
    """对失败/告警项执行对应修复命令（去重）。"""
    actions = []
    for k, v in report["checks"].items():
        if v.get("level") in ("fail", "warn") and v.get("repair"):
            actions.append(v["repair"])
    # 保序去重
    seen = set()
    ordered = []
    for a in actions:
        if a not in seen and a in REPAIR_CMDS:
            seen.add(a)
            ordered.append(a)
    # K 线修好后必须重算筹码（推演依赖最新日）
    if "kline" in ordered and "chip" not in ordered:
        ordered.append("chip")

    results = {}
    for a in ordered:
        cmd = REPAIR_CMDS[a]
        print(f"🔧 自动修复 {a}: {cmd}", flush=True)
        t0 = time.time()
        try:
            r = subprocess.run(
                cmd,
                shell=True,
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=45 * 60,
            )
            ok = r.returncode == 0
            results[a] = {
                "ok": ok,
                "elapsed_s": int(time.time() - t0),
                "stderr_tail": (r.stderr or r.stdout or "")[-300:],
            }
            print(
                f"  {'OK' if ok else 'FAIL'} {a} ({results[a]['elapsed_s']}s)",
                flush=True,
            )
        except Exception as e:
            results[a] = {"ok": False, "error": str(e)}
            print(f"  FAIL {a}: {e}", flush=True)
    return results


def write_block_picks(report: dict) -> None:
    picks = {
        "asof": report["asof"],
        "position_exposure": 0,
        "trade_top_n": 0,
        "picks": [],
        "empty_reason": "data_not_ready",
        "mode": "data_readiness_block",
        "readiness_fails": report.get("fails"),
    }
    PICKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PICKS_PATH.write_text(json.dumps(picks, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fail", action="store_true", help="关键失败 → exit 2（运维）")
    ap.add_argument("--repair", action="store_true", help="失败则自动重拉对应数据")
    ap.add_argument(
        "--block-on-fail",
        action="store_true",
        help="可选：关键失败时阻断早盘（默认不阻断，只预警）",
    )
    args = ap.parse_args()

    report = build_report()
    repaired = None
    if args.repair and (report["fails"] or report["warns"]):
        repaired = try_repair(report)
        report = build_report()  # 修复后再检
        report["repaired"] = repaired

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    emit_alert(report, repaired)

    print(
        f"data_readiness ready={report['ready_for_trade']} "
        f"fail={report['fail_count']} warn={report['warn_count']}",
        flush=True,
    )
    print(f"saved {OUT_PATH}", flush=True)

    if not report["ready_for_trade"] and args.block_on_fail:
        write_block_picks(report)
        print("BLOCKED morning picks (explicit --block-on-fail)", flush=True)

    if not report["ready_for_trade"] and args.fail:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
