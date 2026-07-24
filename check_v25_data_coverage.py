#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VM2.5 / V3 训练前数据通道体检。

用法:
  python3 check_v25_data_coverage.py
  python3 check_v25_data_coverage.py --min-flow-depth 40 --fail

退出码: 0=可训, 2=未达门槛(仅 --fail 时)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path("/home/ubuntu/alphapilot")


def load_json_safe(path, default=None):
    if default is None:
        default = {}
    p = Path(path)
    if not p.exists():
        return default
    raw = p.read_text(encoding="utf-8", errors="ignore")
    if not raw.strip():
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        i = raw.rfind("},")
        if i > 0:
            try:
                return json.loads(raw[: i + 1] + "}")
            except json.JSONDecodeError:
                pass
        return default


def bare(sym: str) -> str:
    s = str(sym).strip()
    if "." in s:
        s = s.split(".")[0]
    return s.zfill(6)[-6:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-flow-cov", type=float, default=0.5)
    ap.add_argument("--min-flow-depth", type=float, default=40.0)
    ap.add_argument("--min-margin-cov", type=float, default=0.3)
    ap.add_argument("--require-event", action="store_true",
                    help="要求业绩预告非空才算通过")
    ap.add_argument("--fail", action="store_true",
                    help="未达标时以退出码 2 结束")
    args = ap.parse_args()

    os_chdir = ROOT
    import os
    os.chdir(os_chdir)

    fund_flow = {bare(k): v for k, v in load_json_safe("data/fund_flow_history.json", {}).items()
                 if isinstance(v, dict)}
    margin = {bare(k): v for k, v in load_json_safe("data/margin_data.json", {}).items()
              if isinstance(v, dict)}
    event = {bare(k): v for k, v in load_json_safe("data/event_forecast.json", {}).items()
             if isinstance(v, dict)}
    fundamentals = {}
    for fp in ("fundamental_data.json", "data/fundamental_data.json"):
        if Path(fp).exists():
            fundamentals = {bare(k): v for k, v in load_json_safe(fp, {}).items()
                            if isinstance(v, dict)}
            break

    chip = {}
    for cp in ("chip_data_all.json", "data/chip_data_all.json"):
        if Path(cp).exists():
            chip = load_json_safe(cp, {})
            break

    try:
        from data_fetcher import get_stock_list
        symbols = [bare(s) for s in get_stock_list()["symbol"].tolist()]
    except Exception:
        # fallback: union of known keys
        symbols = sorted(set(fund_flow) | set(margin) | set(chip))

    n = len(symbols) or 1
    depths = [len(fund_flow[s]) for s in symbols if s in fund_flow and fund_flow[s]]
    flow_hits = sum(1 for s in symbols if s in fund_flow and fund_flow[s])
    margin_hits = sum(1 for s in symbols if s in margin)
    event_hits = sum(1 for s in symbols if s in event)
    fund_hits = sum(1 for s in symbols if s in fundamentals)
    chip_hits = sum(1 for s in symbols if s in chip or bare(s) in {bare(k) for k in chip})

    mean_depth = float(np.mean(depths)) if depths else 0.0
    med_depth = float(np.median(depths)) if depths else 0.0
    sh_margin = sum(1 for s in margin if s.startswith("6"))
    sz_margin = sum(1 for s in margin if s.startswith(("0", "3")))

    report = {
        "n_symbols": len(symbols),
        "fund_flow": {
            "coverage": round(flow_hits / n, 4),
            "mean_depth": round(mean_depth, 2),
            "median_depth": round(med_depth, 2),
            "n_keys": len(fund_flow),
        },
        "margin": {
            "coverage": round(margin_hits / n, 4),
            "n_keys": len(margin),
            "sh_keys": sh_margin,
            "sz_keys": sz_margin,
        },
        "event_forecast": {
            "coverage": round(event_hits / n, 4),
            "n_keys": len(event),
        },
        "fundamentals": {
            "coverage": round(fund_hits / n, 4),
            "n_keys": len(fundamentals),
        },
        "chip": {
            "coverage": round(chip_hits / n, 4),
            "n_keys": len(chip),
        },
    }

    print("=== VM2.5 / V3 数据通道体检 ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    fails = []
    if report["fund_flow"]["coverage"] < args.min_flow_cov:
        fails.append(f"资金流覆盖 {report['fund_flow']['coverage']:.1%} < {args.min_flow_cov:.0%}")
    if report["fund_flow"]["mean_depth"] < args.min_flow_depth:
        fails.append(
            f"资金流深度 mean={report['fund_flow']['mean_depth']:.0f} < {args.min_flow_depth:.0f}"
        )
    if report["margin"]["coverage"] < args.min_margin_cov:
        fails.append(f"两融覆盖 {report['margin']['coverage']:.1%} < {args.min_margin_cov:.0%}")
    if args.require_event and report["event_forecast"]["n_keys"] == 0:
        fails.append("业绩预告为空")
    if report["margin"]["sz_keys"] == 0:
        fails.append("两融缺少深市(00/30) — 建议重跑 pull_margin_event_data.py")

    if fails:
        print("\n未达标:")
        for f in fails:
            print(f"  - {f}")
        print("\n建议顺序:")
        print("  1) python3 pull_margin_event_data.py   # 补两融+业绩预告")
        print("  2) 等待/续拉东财 120 日资金流 (pull_fundflow_120d.py)")
        print("  3) 再跑 python3 train_v25.py")
        if args.fail:
            sys.exit(2)
        sys.exit(0)

    print("\n✅ 通道体检通过，可以启动 train_v25.py")
    Path("output").mkdir(exist_ok=True)
    Path("output/v25_data_coverage.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
