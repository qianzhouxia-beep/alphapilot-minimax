#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""筹码推演交叉验证 — 用资金流/换手率对照本地筹码质量。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent


def cross_validate_chip(
    symbol: str,
    chip: dict | None = None,
    *,
    turnover: float | None = None,
    main_net: float | None = None,
    big_order_ratio: float | None = None,
) -> dict[str, Any]:
    """交叉验证单票筹码推演可信度。

    Returns:
      {confidence: 0~1, warnings: [...], symbol}
    """
    warnings: list[str] = []
    chip = chip or {}
    concentration = chip.get("concentration") or chip.get("chip_concentration")
    peak_shift = chip.get("peak_shift") or chip.get("chip_peak_shift") or 0
    try:
        concentration = float(concentration) if concentration is not None else None
    except (TypeError, ValueError):
        concentration = None
    try:
        peak_shift = float(peak_shift or 0)
    except (TypeError, ValueError):
        peak_shift = 0.0

    if big_order_ratio is not None and concentration is not None:
        if big_order_ratio > 0.3 and concentration < 0.1:
            warnings.append("大单活跃但筹码分散，推演可能不准")

    if turnover is not None and turnover < 1.0 and abs(peak_shift) > 0.05:
        warnings.append("低换手但筹码峰大幅移动，推演可能滞后")

    if main_net is not None and concentration is not None:
        # 主力大幅流入但集中度下降 → 可疑
        if main_net > 5e6 and peak_shift < -0.03:
            warnings.append("主力流入与筹码峰下移背离")

    conf = 1.0 - 0.25 * len(warnings)
    return {
        "symbol": symbol,
        "confidence": round(max(0.0, min(1.0, conf)), 3),
        "warnings": warnings,
        "ok": len(warnings) == 0,
    }


def validate_chip_file(
    chip_path: Path | None = None,
    fund_path: Path | None = None,
    limit: int = 200,
) -> dict:
    chip_path = chip_path or ROOT / "chip_data_all.json"
    fund_path = fund_path or ROOT / "data" / "fund_flow_history.json"
    chips = {}
    if chip_path.exists():
        try:
            chips = json.loads(chip_path.read_text(encoding="utf-8"))
        except Exception:
            chips = {}
    fund = {}
    if fund_path.exists():
        try:
            fund = json.loads(fund_path.read_text(encoding="utf-8"))
        except Exception:
            fund = {}

    rows = []
    n_warn = 0
    for i, (sym, chip) in enumerate(chips.items()):
        if i >= limit:
            break
        code = str(sym)[-6:]
        series = fund.get(code) or fund.get(sym) or {}
        if isinstance(series, dict) and "data" in series:
            series = series["data"]
        main_net = None
        if isinstance(series, dict) and series:
            last = sorted(series.keys())[-1]
            v = series[last]
            try:
                main_net = float(v.get("main_net") if isinstance(v, dict) else v)
            except Exception:
                main_net = None
        r = cross_validate_chip(code, chip if isinstance(chip, dict) else {}, main_net=main_net)
        if not r["ok"]:
            n_warn += 1
            rows.append(r)

    out = {
        "checked": min(limit, len(chips)),
        "warned": n_warn,
        "samples": rows[:30],
    }
    out_path = ROOT / "output" / "chip_cross_validate.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


if __name__ == "__main__":
    print(json.dumps(validate_chip_file(), ensure_ascii=False, indent=2))
