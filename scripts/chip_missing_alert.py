#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chip 缺失告警（2026-08-24 根治）：生产 chip 由 WorkBuddy 本地拉东财真实 CYQ
筹码合并上传，服务器侧无真实数据源。当 chip 最新日覆盖率不足时，本脚本负责：
  1. 写出明确的缺失清单（缺哪些股票、截至哪天）
  2. 追加到 output/data_alerts.json 供 cron 巡检与告警
  3. 返回退出码 1，让 data_readiness_gate 能感知修复失败

绝不尝试用 pull_chip_from_kline 覆盖真实筹码（那是 K 线推演口径，会污染数据）。
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHIP_CANDIDATES = [ROOT / "chip_data_all.json", ROOT / "data" / "chip_data_all.json"]
ALERT_PATH = ROOT / "output" / "data_alerts.json"


def _load_chip():
    for p in CHIP_CANDIDATES:
        if p.exists():
            try:
                raw = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
                return raw.get("data", raw) if isinstance(raw, dict) else raw
            except Exception:
                continue
    return None


def main() -> int:
    data = _load_chip()
    if not data:
        print("[chip_missing_alert] chip_data_all.json 缺失或不可读", flush=True)
        return 1

    cnt = Counter()
    for v in data.values():
        if isinstance(v, dict) and v.get("date"):
            cnt[str(v["date"])[:10]] += 1
    if not cnt:
        print("[chip_missing_alert] chip 无日期数据", flush=True)
        return 1

    latest = max(cnt)
    n_latest = cnt[latest]
    total = len(data)
    cover = n_latest / total if total else 0.0
    missing = sorted(
        code for code, v in data.items()
        if not (isinstance(v, dict) and str(v.get("date"))[:10] == latest)
    )

    print(f"[chip_missing_alert] 最新 {latest}: {n_latest}/{total} ({cover:.1%})", flush=True)
    if cover >= 0.95:
        print("[chip_missing_alert] OK: 覆盖率达标", flush=True)
        return 0

    msg = (
        f"chip 覆盖率不足 {latest}: {n_latest}/{total} ({cover:.1%}) < 95%。"
        f"缺失 {len(missing)} 只，需要 WorkBuddy 补拉批次后重新 _upload_chip。"
    )
    print(f"[chip_missing_alert] ❌ {msg}", flush=True)
    print(f"[chip_missing_alert] 缺失样例: {missing[:10]}", flush=True)

    # 写入 data_alerts.json（与 data_readiness_gate 共用告警文件）
    try:
        alert = {}
        if ALERT_PATH.exists():
            try:
                alert = json.loads(ALERT_PATH.read_text(encoding="utf-8"))
            except Exception:
                alert = {}
        issue = {
            "key": "chip_missing",
            "severity": "fail",
            "reason": msg,
            "repair": "WorkBuddy 补拉批次 → 重新 _upload_chip_*.py",
            "path": str(CHIP_CANDIDATES[0]),
            "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "missing_n": len(missing),
            "missing_sample": missing[:50],
        }
        issues = alert.get("issues") or []
        issues = [x for x in issues if x.get("key") != "chip_missing"]
        issues.append(issue)
        alert["issues"] = issues
        alert["status"] = "critical"
        alert["message"] = f"chip 数据异常: {msg}"
        ALERT_PATH.write_text(json.dumps(alert, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[chip_missing_alert] 已写入 {ALERT_PATH}", flush=True)
    except Exception as e:
        print(f"[chip_missing_alert] 写告警失败: {e}", flush=True)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
