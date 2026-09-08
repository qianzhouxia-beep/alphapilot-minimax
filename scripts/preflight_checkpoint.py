#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""凌晨数据预检门 — 05:00 主管线前的数据就绪 checkpoint。

00:30 cron（工作日）逐条验证关键数据（存在 / 新鲜 / 对齐 / 结构契约），
失败 → 企微告警 + 自动重拉；写 output/preflight_checkpoint.json 供主管线消费。

与 data_readiness_gate 是同一套契约（复用其全部检查/修复/告警逻辑）：
  preflight_checkpoint.py  00:30   # 提前 5 小时第一道门（发现问题有充足时间修复）
  data_readiness_gate.py   04:50 --repair  # 二次确认（04:40/04:45/04:52 拉取任务链之后）
  05:00 alphapilot_pipeline_v3.py  # 读取本文件打印预检门状态（不阻断）
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import data_readiness_gate as dg

OUT_PATH = dg.ROOT / "output" / "preflight_checkpoint.json"


def _print_check(name: str, v: dict) -> None:
    lv = v.get("level", "?")
    mark = {"ok": "✅", "warn": "⚠️", "fail": "❌"}.get(lv, "?")
    reason = v.get("reason") or ""
    print(f"  {mark} {name:<26} [{lv}] {reason}", flush=True)


def _alignment_summary() -> None:
    """K线 / 筹码最新日展示（供人一眼确认数据是否对齐到同一交易日）。"""
    print("\n── 数据对齐 ──", flush=True)
    kdf = dg.ROOT / "data/kline_cache/kline_all.parquet"
    if kdf.exists():
        try:
            import pandas as pd

            kd = str(pd.read_parquet(kdf, columns=["date"])["date"].astype(str).str[:10].max())
            print(f"  K线最新日       : {kd}", flush=True)
        except Exception as e:
            print(f"  K线读取失败     : {e}", flush=True)
    chip_p = dg.ROOT / "chip_data_all.json"
    if not chip_p.exists():
        chip_p = dg.ROOT / "data" / "chip_data_all.json"
    if chip_p.exists():
        try:
            raw = json.loads(chip_p.read_text(encoding="utf-8", errors="ignore"))
            recs = dg._chip_records(raw)
            from collections import Counter

            dates = [
                str(v.get("date"))[:10]
                for v in recs.values()
                if isinstance(v, dict) and v.get("date")
            ]
            if dates:
                cd = Counter(dates).most_common(1)[0][0]
                print(f"  筹码最新日(众数) : {cd}", flush=True)
        except Exception as e:
            print(f"  筹码读取失败   : {e}", flush=True)
    ff = dg.ROOT / "data/fund_flow_history.json"
    if ff.exists():
        try:
            raw = json.loads(ff.read_text(encoding="utf-8", errors="ignore"))
            dates = []
            for v in raw.values():
                if isinstance(v, dict) and v:
                    ds = [str(k)[:10] for k in v.keys()]
                    dates += ds
            if dates:
                print(f"  资金流最新日     : {max(dates)}", flush=True)
        except Exception as e:
            print(f"  资金流读取失败 : {e}", flush=True)
    lhb = dg.ROOT / "data/lhb_history.json"
    if lhb.exists():
        try:
            raw = json.loads(lhb.read_text(encoding="utf-8", errors="ignore"))
            all_dates = set()
            for code, v in raw.items():
                if isinstance(v, dict):
                    for dk in (v.get("dates") or {}):
                        all_dates.add(str(dk)[:10])
            if all_dates:
                print(f"  龙虎榜最新日     : {max(all_dates)}", flush=True)
        except Exception as e:
            print(f"  龙虎榜读取失败 : {e}", flush=True)


def _aux_asof_checks() -> dict:
    """辅助数据对齐增强检查（margin/lhb 的 T+1 特性 + 连续失败检测）。

    背景：margin(两融) 与 lhb(龙虎榜) 都是 T+1 公布的，且凌晨 04:40/04:45
    才拉取。因此 00:30 预检时这两者**天然是 T-1 数据**——不能按"今天最新"
    判 fail（会每天误报）。但必须检测真正的异常：
      - margin: mtime 距今 > 7 天（连续 5+ 个交易日拉取失败，文件滞留）
      - lhb: 最新日落后 K线 >= 2 个交易日（拉取任务连续失败）
    返回 {name: {level, reason, repair}}。
    """
    out = {}
    # K线最新日作参照（辅助数据对齐到同一个"最近收盘日"）
    kline_latest = None
    kdf = dg.ROOT / "data/kline_cache/kline_all.parquet"
    if kdf.exists():
        try:
            import pandas as pd

            kline_latest = str(pd.read_parquet(kdf, columns=["date"])["date"].astype(str).str[:10].max())
        except Exception:
            kline_latest = None

    # ── margin：mtime 滞留检测 ──
    mp = dg.ROOT / "data/margin_data.json"
    if not mp.exists():
        out["margin_stale"] = {"level": "fail", "reason": "margin_data.json missing", "repair": "margin_event"}
    else:
        age_days = (datetime.now().timestamp() - mp.stat().st_mtime) / 86400.0
        if age_days > 7:
            out["margin_stale"] = {
                "level": "fail",
                "reason": f"margin mtime {age_days:.0f}d 前未更新（连续拉取失败？）",
                "repair": "margin_event",
            }
        else:
            out["margin_stale"] = {"level": "ok", "reason": None, "repair": None}

    # ── lhb：最新日落后 K线检测（允许 1 个交易日滞后，T+1 正常）──
    lp = dg.ROOT / "data/lhb_history.json"
    if not lp.exists():
        out["lhb_stale"] = {"level": "fail", "reason": "lhb_history.json missing", "repair": "lhb"}
    else:
        latest = None
        try:
            raw = json.loads(lp.read_text(encoding="utf-8", errors="ignore"))
            for code, v in raw.items():
                if isinstance(v, dict):
                    ds = (v.get("dates") or {})
                    if ds:
                        m = max(str(d)[:10] for d in ds)
                        latest = max(latest, m) if latest else m
        except Exception:
            latest = None
        if latest is None:
            out["lhb_stale"] = {"level": "fail", "reason": "lhb 无可解析日期", "repair": "lhb"}
        elif kline_latest is None:
            out["lhb_stale"] = {"level": "warn", "reason": f"lhb={latest} kline未知", "repair": None}
        else:
            from datetime import date as _date

            try:
                lag = (_date.fromisoformat(kline_latest) - _date.fromisoformat(latest)).days
            except Exception:
                lag = 999
            if lag >= 2:
                out["lhb_stale"] = {
                    "level": "fail",
                    "reason": f"lhb最新日 {latest} 落后 K线 {kline_latest} {lag}天（连续拉取失败？）",
                    "repair": "lhb",
                }
            else:
                out["lhb_stale"] = {"level": "ok", "reason": f"lhb={latest} kline={kline_latest}", "repair": None}
    return out


def run_preflight() -> dict:
    t0 = time.time()
    print("=" * 66, flush=True)
    print(f"🛡 AlphaPilot 凌晨预检门 {datetime.now():%Y-%m-%d %H:%M:%S}", flush=True)
    print("=" * 66, flush=True)

    report = dg.build_report()

    # 辅助数据对齐增强检查（margin/lhb T+1 特性 + 连续失败检测）
    aux = _aux_asof_checks()
    for k, v in aux.items():
        report["checks"][k] = {
            "critical": v.get("level") == "fail",
            "ok": v.get("level") == "ok",
            "level": v.get("level"),
            "reason": v.get("reason"),
            "repair": v.get("repair"),
        }
        if v.get("level") == "fail":
            report["fails"].append(k)
        elif v.get("level") == "warn":
            report["warns"].append(k)
    report["fail_count"] = len(report["fails"])
    report["warn_count"] = len(report["warns"])
    report["ready_for_trade"] = report["fail_count"] == 0

    print("\n── 逐条 checkpoint ──", flush=True)
    for k, v in report["checks"].items():
        _print_check(k, v)

    # 失败/告警 → 自动重拉 → 复检
    repaired = {}
    if report.get("fails") or report.get("warns"):
        print(
            f"\n🔧 发现 {len(report['fails'])} 项失败 / {len(report['warns'])} 项告警，自动重拉...",
            flush=True,
        )
        repaired = dg.try_repair(report)
        report = dg.build_report()

        # 重拉后辅助检查也要复检
        aux2 = _aux_asof_checks()
        for k, v in aux2.items():
            report["checks"][k] = {
                "critical": v.get("level") == "fail",
                "ok": v.get("level") == "ok",
                "level": v.get("level"),
                "reason": v.get("reason"),
                "repair": v.get("repair"),
            }
            if v.get("level") == "fail":
                report["fails"].append(k)
            elif v.get("level") == "warn":
                report["warns"].append(k)
        report["fail_count"] = len(report["fails"])
        report["warn_count"] = len(report["warns"])
        report["ready_for_trade"] = report["fail_count"] == 0
        report["repaired"] = repaired
        print("\n── 复检后 ──", flush=True)
        for k, v in report["checks"].items():
            _print_check(k, v)

    _alignment_summary()

    elapsed = int(time.time() - t0)
    result = {
        "asof": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ready_for_pipeline": report["ready_for_trade"],
        "fail_count": report["fail_count"],
        "warn_count": report["warn_count"],
        "fails": report["fails"],
        "warns": report["warns"],
        "checks": {
            k: {
                "level": v.get("level"),
                "reason": v.get("reason"),
                "repair": v.get("repair"),
            }
            for k, v in report["checks"].items()
        },
        "repaired": repaired,
        "elapsed_s": elapsed,
        "note": "05:00 主管线读取本文件；04:50 data_readiness_gate --repair 为二次确认",
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ preflight checkpoint 写入 {OUT_PATH}", flush=True)

    # 企微：fail-only（复用去重）
    dg.maybe_wecom_push_fail(report)
    if report["ready_for_trade"]:
        print("✅ 数据就绪，主管线可以安全运行", flush=True)
    else:
        print(f"❌ 数据未就绪 fail={report['fail_count']}，已企微告警。", flush=True)
    return result


if __name__ == "__main__":
    raise SystemExit(0 if run_preflight()["ready_for_pipeline"] else 2)
