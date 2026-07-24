#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""执行前分时资金确认 — 买入前再验一遍盘中资金面。

设计:
  - 09:35 morning picks 已过资金门；开盘/盘中真正下单前再确认一次
  - 不硬拦全部弱势，而是返回 weight_adjust（0~1）供仓位缩放
  - weight < 0.3 → 视为不通过，跳过买入
  - 若 data/wind_candidate_flow.json 有该票且较新，叠加 Wind 机构/主力/散户分档软调
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
WIND_FLOW = ROOT / "data" / "wind_candidate_flow.json"
# 盘前可用昨收；盘中希望 session 刷新后不太旧（默认 18h 覆盖隔夜→开盘）
WIND_MAX_AGE_HOURS = float(os.environ.get("WIND_PRECHECK_MAX_AGE_H", "18") or 18)


def _detect_period(now: datetime | None = None) -> str:
    now = now or datetime.now()
    hm = (now.hour, now.minute)
    if hm < (9, 45):
        return "open"
    if hm >= (14, 30):
        return "close"
    return "mid"


def _bare(sym: str) -> str:
    s = str(sym or "").lower().replace("sh", "").replace("sz", "").replace("bj", "")
    digits = "".join(ch for ch in s if ch.isdigit())
    return digits[-6:] if len(digits) >= 6 else digits


def _load_wind_item(symbol: str, now: datetime | None = None) -> dict[str, Any] | None:
    """读 wind_candidate_flow 中该票；过期或缺文件则返回 None。"""
    if not WIND_FLOW.exists():
        return None
    try:
        raw = json.loads(WIND_FLOW.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None

    now = now or datetime.now()
    updated = str(raw.get("updated_at") or "").strip()
    age_h = None
    if updated:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                ts = datetime.strptime(updated[:19] if len(updated) >= 19 else updated, fmt)
                age_h = (now - ts).total_seconds() / 3600.0
                break
            except ValueError:
                continue
    if age_h is not None and age_h > WIND_MAX_AGE_HOURS:
        return None

    code = _bare(symbol)
    items = raw.get("items") or {}
    if not isinstance(items, dict):
        return None
    row = items.get(code) or items.get(symbol)
    if not isinstance(row, dict):
        return None
    out = dict(row)
    out["_wind_session"] = raw.get("session")
    out["_wind_updated_at"] = updated
    out["_wind_age_h"] = round(age_h, 2) if age_h is not None else None
    return out


def _apply_wind_b_prime(
    weight: float,
    reasons: list[str],
    wind: dict[str, Any],
) -> tuple[float, float | None, float | None, float | None, str | None]:
    """机构/主力/散户分档软调。返回 (weight, inst, main, retail, bias)."""
    inst = main = retail = None
    try:
        if wind.get("inst_net") is not None:
            inst = float(wind["inst_net"])
    except (TypeError, ValueError):
        inst = None
    try:
        v = wind.get("main_net_today")
        if v is not None:
            main = float(v)
    except (TypeError, ValueError):
        main = None
    try:
        if wind.get("retail_net") is not None:
            retail = float(wind["retail_net"])
    except (TypeError, ValueError):
        retail = None

    bias = None
    if inst is not None and main is not None and inst > 0 and main > 0:
        weight = min(1.0, weight * 1.12)
        reasons.append(f"Wind机构+主力同向流入")
        bias = "inst_in"
    elif (
        retail is not None
        and main is not None
        and retail > 0
        and main < 0
        and (inst is None or inst <= 0)
    ):
        weight *= 0.72
        reasons.append("Wind散户追涨/机构未跟")
        bias = "retail_chase"
    elif inst is not None and inst < -5e6:
        weight *= 0.70
        reasons.append(f"Wind机构净流出{inst/1e4:.0f}万")
        bias = "inst_out"
    elif main is not None and main < -1e7:
        weight *= 0.80
        reasons.append(f"Wind主力净流出{main/1e4:.0f}万")
        bias = "main_out"
    elif inst is not None and main is not None and inst > 0 and main <= 0:
        # 机构进、主力平/弱：轻度加分
        weight = min(1.0, weight * 1.05)
        reasons.append("Wind机构净流入")
        bias = "inst_soft"

    sess = wind.get("_wind_session")
    if sess:
        reasons.append(f"wind_session={sess}")
    return weight, inst, main, retail, bias


def intraday_fund_confirm(
    symbol: str,
    *,
    live: dict | None = None,
    quote: dict | None = None,
    now: datetime | None = None,
    wind: dict | None = None,
) -> dict[str, Any]:
    """执行前确认：当前资金面是否支持买入。

    Args:
      symbol: 股票代码
      live: 可选，已取好的 live_fund_flow 行
      quote: 可选，{last, prev_close, open, change_pct, ...}
      wind: 可选，已取好的 wind_candidate_flow 行；None 则自动读缓存

    Returns:
      {
        "pass": bool,
        "weight": float,          # 0~1 仓位缩放
        "reasons": list[str],
        "abr": float|None,
        "change_pct": float|None,
        "main_net": float|None,
        "period": str,
        "wind_inst_net": float|None,
        "wind_main_net": float|None,
        "wind_tier_bias": str|None,
      }
    """
    reasons: list[str] = []
    weight = 1.0
    period = _detect_period(now)

    # ── 拉取实时资金（东财）──
    abr = None
    main_net = None
    live_chg = None
    if live is None:
        try:
            from live_fund_flow import fetch_fund_flow

            live = fetch_fund_flow(symbol)
        except Exception as e:
            reasons.append(f"live_fund_skip:{e}")
            live = {}
    if live:
        try:
            abr = float(live.get("active_buy_ratio")) if live.get("active_buy_ratio") is not None else None
        except (TypeError, ValueError):
            abr = None
        try:
            main_net = float(live.get("main_net")) if live.get("main_net") is not None else None
        except (TypeError, ValueError):
            main_net = None
        try:
            live_chg = float(live.get("change_pct")) if live.get("change_pct") is not None else None
        except (TypeError, ValueError):
            live_chg = None

    # ── 涨跌幅（优先 quote，其次 live）──
    chg = live_chg
    if quote:
        try:
            if quote.get("change_pct") is not None:
                chg = float(quote["change_pct"])
            elif quote.get("last") and quote.get("prev_close"):
                last = float(quote["last"])
                prev = float(quote["prev_close"])
                if prev > 0:
                    chg = (last / prev - 1.0) * 100.0
        except (TypeError, ValueError):
            pass

    # ── 规则（东财 live）──
    if abr is not None:
        if abr < 0.45:
            reasons.append(f"主动买比{abr:.2f}<0.45")
            weight *= 0.35
        elif abr < 0.48:
            reasons.append(f"主动买比{abr:.2f}<0.48")
            weight *= 0.60
        elif abr < 0.52:
            weight *= 0.85

    if main_net is not None and main_net < -5e6:
        reasons.append(f"主力净流出{main_net/1e4:.0f}万")
        weight *= 0.55

    if chg is not None:
        if chg > 7.0:
            reasons.append(f"涨幅{chg:.1f}%>7%,追高风险")
            weight *= 0.40
        elif chg > 5.0:
            reasons.append(f"涨幅{chg:.1f}%>5%")
            weight *= 0.55
        elif chg < -4.0:
            reasons.append(f"跌幅{chg:.1f}%<-4%,弱势不追")
            weight *= 0.25
        elif chg < -2.5:
            reasons.append(f"跌幅{chg:.1f}%<-2.5%")
            weight *= 0.55

    # 开盘/尾盘额外谨慎
    if period == "open" and chg is not None and chg > 3.0:
        reasons.append("开盘跳涨谨慎")
        weight *= 0.85
    if period == "close" and main_net is not None and main_net < 0:
        reasons.append("尾盘资金净流出")
        weight *= 0.80

    # ── Wind B′ 叠加（只读缓存，不额外耗积分）──
    wind_inst = wind_main = wind_retail = None
    wind_bias = None
    if wind is None:
        wind = _load_wind_item(symbol, now=now)
    if isinstance(wind, dict) and wind:
        weight, wind_inst, wind_main, wind_retail, wind_bias = _apply_wind_b_prime(
            weight, reasons, wind
        )
        # 东财 main_net 缺失时用 Wind 主力兜底展示
        if main_net is None and wind_main is not None:
            main_net = wind_main

    weight = max(0.0, min(1.0, round(weight, 3)))
    passed = weight >= 0.30
    if not passed and not reasons:
        reasons.append("综合权重过低")

    return {
        "pass": passed,
        "weight": weight,
        "reasons": reasons,
        "abr": abr,
        "change_pct": chg,
        "main_net": main_net,
        "period": period,
        "symbol": symbol,
        "wind_inst_net": wind_inst,
        "wind_main_net": wind_main,
        "wind_retail_net": wind_retail,
        "wind_tier_bias": wind_bias,
    }


def batch_fund_confirm(symbols: list[str]) -> dict[str, dict]:
    """批量确认（共享 live_fund_flow 缓存）。"""
    live_map: dict = {}
    try:
        from live_fund_flow import batch_fund_flow

        live_map = batch_fund_flow(symbols) or {}
    except Exception:
        live_map = {}
    out = {}
    for sym in symbols:
        live = live_map.get(sym) or live_map.get(str(sym)[-6:]) or {}
        out[sym] = intraday_fund_confirm(sym, live=live)
    return out


if __name__ == "__main__":
    # 无网络冒烟：用假 Wind 行验证分档
    demo_wind = {
        "inst_net": 2e7,
        "main_net_today": 3e7,
        "retail_net": -1e6,
        "_wind_session": "open",
    }
    r = intraday_fund_confirm(
        "600519",
        live={"active_buy_ratio": 0.55, "main_net": 1e6, "change_pct": 1.2},
        wind=demo_wind,
        now=datetime(2026, 7, 23, 9, 40),
    )
    print("inst_in", r["weight"], r["wind_tier_bias"], r["reasons"])
    r2 = intraday_fund_confirm(
        "000858",
        live={"active_buy_ratio": 0.55, "main_net": 1e6, "change_pct": 1.2},
        wind={
            "inst_net": -1e6,
            "main_net_today": -2e7,
            "retail_net": 3e7,
            "_wind_session": "open",
        },
        now=datetime(2026, 7, 23, 9, 40),
    )
    print("retail_chase", r2["weight"], r2["wind_tier_bias"], r2["reasons"])
