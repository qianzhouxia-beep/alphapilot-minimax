#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Top2 可交易闭环 — 样本外验收包装器。

读取 models/v25_meta.json 的 trained_at，在训练截止日之后的交易日窗口
跑 backtest_v3_tradable_gated.py（默认 Top2），对照 playbook 门槛写报告。

若 OOS 交易日不足（周末/数据未更新/刚训练完），额外跑一段「参考窗」
（最近 N 个交易日）供观察，但标注 in-sample 风险，不可据此加杠杆。

用法:
  python3 scripts/run_oos_tradable_top2.py
  python3 scripts/run_oos_tradable_top2.py --end 2026-07-17
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
META = ROOT / "models" / "v25_meta.json"
GATED_OUT = ROOT / "output" / "v3_tradable_gated_sleeve_backtest.json"
REPORT = ROOT / "output" / "oos_tradable_top2.json"

MIN_DAYS = 40
MIN_FILL = 0.70
MIN_HIT3 = 0.35
PRODUCTION_ARM = "A1_permission"
REF_DAYS = 40


def _parse_day(s: str) -> str:
    return (s or "").strip()[:10]


def load_trained_at() -> str:
    if not META.exists():
        raise SystemExit(f"missing {META}")
    meta = json.loads(META.read_text(encoding="utf-8"))
    day = _parse_day(str(meta.get("trained_at") or ""))
    if not day:
        raise SystemExit(f"trained_at missing in {META}")
    return day


def next_day(day: str) -> str:
    d = datetime.strptime(day, "%Y-%m-%d") + timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def load_calendar() -> list[str]:
    try:
        import pandas as pd
    except Exception as e:
        raise SystemExit(f"pandas required: {e}")
    kpath = ROOT / "data/kline_cache/kline_all.parquet"
    if not kpath.exists():
        kpath = ROOT / "kline_all.parquet"
    if not kpath.exists():
        raise SystemExit(f"missing kline parquet under {ROOT}")
    df = pd.read_parquet(kpath, columns=["date", "symbol"])
    df["date"] = df["date"].astype(str).str[:10]
    df["symbol"] = df["symbol"].astype(str)
    bare = df["symbol"].str.replace(r"\D", "", regex=True).str[-6:]
    cal_sym = "600519"
    days = sorted(df.loc[bare == cal_sym, "date"].unique())
    if not days:
        days = sorted(df["date"].unique())
    return list(days)


def clamp_window(start: str, end: str, calendar: list[str]) -> tuple[str, str, list[str]]:
    """Return (start, end, trading_days) snapped to available bars.

    If start is after the last bar (e.g. weekend right after train day),
    returns empty days with end=last_available.
    """
    last_le = [d for d in calendar if d <= end]
    if not last_le:
        return start, end, []
    end2 = last_le[-1]
    days = [d for d in calendar if start <= d <= end2]
    if not days:
        # 无 OOS bar（刚训练完 / 周末）：end 记最后有数据日，start 保持请求日
        return start, end2, []
    return days[0], days[-1], days


def pick_arm(kpis: list[dict], prefer: str) -> dict | None:
    by = {k.get("arm"): k for k in kpis}
    if prefer in by:
        return by[prefer]
    # 兼容旧名
    if prefer in ("A1_gated_exposure", "A1_ladder") and "A1_permission" in by:
        return by["A1_permission"]
    if "A1_permission" in by:
        return by["A1_permission"]
    if "A1_ladder" in by:
        return by["A1_ladder"]
    for k, v in by.items():
        if k and "A1" in k:
            return v
    return kpis[0] if kpis else None


def gate_check(kpi: dict, n_days: int) -> dict:
    fill = float(kpi.get("fill_rate") or 0)
    hit3 = float(kpi.get("hit_3pct_rate") or 0)
    maxdd = float(kpi.get("max_drawdown") or 0)
    enough = n_days >= MIN_DAYS
    checks = {
        "enough_days": enough,
        "fill_rate_ok": (fill >= MIN_FILL) if enough else None,
        "hit_3pct_ok": (hit3 >= MIN_HIT3) if enough else None,
        "maxdd_note": "monitor only (no hard threshold in playbook)",
        "max_drawdown": maxdd,
    }
    if not enough:
        verdict = "INSUFFICIENT_OOS"
        reason = f"OOS trading days={n_days} < {MIN_DAYS}; keep accumulating, do not leverage"
    elif checks["fill_rate_ok"] and checks["hit_3pct_ok"]:
        verdict = "PASS"
        reason = "fill & hit≥3% meet playbook; still monitor maxDD"
    else:
        verdict = "FAIL"
        reason = "fill or hit≥3% below playbook; do not add leverage; consider lower exposure"
    return {"verdict": verdict, "reason": reason, "checks": checks}


def run_gated(start: str, end: str, top_n: int) -> dict:
    cmd = [
        sys.executable,
        "-u",
        str(ROOT / "backtest_v3_tradable_gated.py"),
        "--start",
        start,
        "--end",
        end,
        "--top-n",
        str(top_n),
        "--sleeve-top-n",
        str(top_n),
    ]
    print("RUN:", " ".join(cmd), flush=True)
    rc = subprocess.call(cmd, cwd=str(ROOT))
    if rc != 0:
        raise SystemExit(f"gated backtest failed rc={rc}")
    if not GATED_OUT.exists():
        raise SystemExit(f"missing gated output {GATED_OUT}")
    return json.loads(GATED_OUT.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="", help="override OOS start (default trained_at+1)")
    ap.add_argument("--end", default="", help="override end (default today)")
    ap.add_argument("--top-n", type=int, default=2)
    ap.add_argument("--skip-run", action="store_true")
    ap.add_argument("--arm", default=PRODUCTION_ARM)
    ap.add_argument("--ref-days", type=int, default=REF_DAYS)
    ap.add_argument("--no-ref", action="store_true", help="skip reference window when OOS short")
    args = ap.parse_args()

    trained = load_trained_at()
    calendar = load_calendar()
    req_end = args.end or datetime.now().strftime("%Y-%m-%d")
    req_start = args.start or next_day(trained)

    start, end, oos_days = clamp_window(req_start, req_end, calendar)
    print(
        f"trained_at={trained} requested={req_start}~{req_end} "
        f"resolved_OOS={start}~{end} n_days={len(oos_days)} top_n={args.top_n}",
        flush=True,
    )

    oos_gated = None
    arm = {
        "arm": args.arm,
        "n_days": 0,
        "n_filled": 0,
        "n_signals": 0,
        "fill_rate": 0.0,
        "hit_3pct_rate": 0.0,
        "win_rate": 0.0,
        "max_drawdown": 0.0,
    }
    if oos_days and not args.skip_run:
        oos_gated = run_gated(start, end, args.top_n)
        arm = pick_arm(oos_gated.get("kpi") or [], args.arm) or arm
    elif args.skip_run and GATED_OUT.exists():
        oos_gated = json.loads(GATED_OUT.read_text(encoding="utf-8"))
        arm = pick_arm(oos_gated.get("kpi") or [], args.arm) or arm

    n_days = int(arm.get("n_days") or len(oos_days))
    gate = gate_check(arm, n_days)

    # Reference window when OOS insufficient
    ref = None
    if (not args.no_ref) and n_days < MIN_DAYS:
        last = [d for d in calendar if d <= req_end]
        if len(last) >= 5:
            ref_days_list = last[-args.ref_days :]
            ref_start, ref_end = ref_days_list[0], ref_days_list[-1]
            print(f"REF window (observe only)={ref_start}~{ref_end} n={len(ref_days_list)}", flush=True)
            ref_gated = run_gated(ref_start, ref_end, args.top_n)
            ref_arm = pick_arm(ref_gated.get("kpi") or [], args.arm)
            overlap = [d for d in ref_days_list if d <= trained]
            ref = {
                "window": {"start": ref_start, "end": ref_end, "n_days": len(ref_days_list)},
                "in_sample_days": len(overlap),
                "in_sample_risk": len(overlap) > 0,
                "kpi": ref_arm,
                "note": "REFERENCE ONLY — may overlap training; not for leverage decision",
            }

    all_kpi = (oos_gated or {}).get("kpi") or []
    by_arm = {k.get("arm"): k for k in all_kpi}
    lad_k = by_arm.get("A1_ladder") or {}
    perm_k = by_arm.get("A1_permission") or arm
    ladder_vs_cur = None
    if lad_k and perm_k:
        ladder_vs_cur = {
            "label": "A1_permission_vs_A1_ladder",
            "total_return_pp": (
                float(perm_k.get("total_return") or 0) - float(lad_k.get("total_return") or 0)
            )
            * 100,
            "maxDD_pp": (
                float(perm_k.get("max_drawdown") or 0) - float(lad_k.get("max_drawdown") or 0)
            )
            * 100,
            "empty_days_ladder": lad_k.get("empty_days"),
            "empty_days_permission": perm_k.get("empty_days"),
            "pass_maxdd": (
                float(perm_k.get("max_drawdown") or 0)
                <= float(lad_k.get("max_drawdown") or 0) + 0.02
            ),
        }

    report = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "trained_at": trained,
        "oos_window": {
            "requested_start": req_start,
            "requested_end": req_end,
            "start": start,
            "end": end,
            "n_days": n_days,
            "trading_days": oos_days,
        },
        "top_n": args.top_n,
        "production_arm": arm.get("arm"),
        "kpi": arm,
        "all_kpi": all_kpi,
        "ladder_vs_cur": ladder_vs_cur,
        "gate": gate,
        "reference_window": ref,
        "playbook": {
            "min_days": MIN_DAYS,
            "min_fill": MIN_FILL,
            "min_hit_3pct": MIN_HIT3,
            "protocol": "T+1 open (skip limit) / T+2 close / cost 15bp / Top2 × exposure",
        },
        "source_file": str(GATED_OUT),
        "next_actions": (
            [
                "paper Top2 keeps running with expo/limit/T+2",
                "re-run weekly: python3 scripts/run_oos_tradable_top2.py",
                "use reference_window only for smoke, not leverage",
            ]
            if gate["verdict"] == "INSUFFICIENT_OOS"
            else (
                ["OK to keep current exposure", "monitor maxDD + paper audit daily"]
                if gate["verdict"] == "PASS"
                else ["cut exposure to 0.5 or pause buys", "python3 scripts/audit_paper_tradable.py"]
            )
        ),
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n======== OOS Top2 验收 ========")
    print(f"arm={arm.get('arm')} days={n_days} filled={arm.get('n_filled')}/{arm.get('n_signals')}")
    print(
        f"fill={float(arm.get('fill_rate') or 0)*100:.0f}% "
        f"hit3%={float(arm.get('hit_3pct_rate') or 0)*100:.1f}% "
        f"win={float(arm.get('win_rate') or 0)*100:.1f}% "
        f"maxDD={float(arm.get('max_drawdown') or 0)*100:.1f}%"
    )
    if ladder_vs_cur:
        print(
            f"A1_permission vs A1_ladder: total {ladder_vs_cur['total_return_pp']:+.2f}pp "
            f"maxDD {ladder_vs_cur['maxDD_pp']:+.2f}pp "
            f"empty {ladder_vs_cur['empty_days_ladder']}→{ladder_vs_cur['empty_days_permission']} "
            f"maxDD_ok={ladder_vs_cur['pass_maxdd']}"
        )
    print(f"VERDICT: {gate['verdict']} — {gate['reason']}")
    if ref and ref.get("kpi"):
        rk = ref["kpi"]
        print(
            f"REF[{ref['window']['start']}~{ref['window']['end']}] "
            f"in_sample_days={ref['in_sample_days']} "
            f"fill={float(rk.get('fill_rate') or 0)*100:.0f}% "
            f"hit3%={float(rk.get('hit_3pct_rate') or 0)*100:.1f}% "
            f"maxDD={float(rk.get('max_drawdown') or 0)*100:.1f}%  (observe only)"
        )
    print("saved", REPORT)
    return 0 if gate["verdict"] != "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
