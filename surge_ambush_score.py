#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""涨停埋伏分 — 仅 B 臂软加权（P2b）。

依据 WorkBuddy surge_multi_factor_report §五：

  资金埋伏(0-5): 连续净流入≥4→3 / ≥3→2；机构净买→+2；机构+大户→+1
  板块共振(0-3): Wind prefer(fresh_inflow)→+2；涨停行业Top10→+1（有缓存才加）
  动量(0-2):     近 N 日涨停命中→+2

  总分 0-10:
    ≥7 → score × SURGE_AMBUSH_STRONG_MULT (1.15)
    4-6 → × SURGE_AMBUSH_MID_MULT (1.05)
    <4  → 不再乘（保持底座 SURGE_ARM_B_MULT）

Env:
  ENABLE_SURGE_AMBUSH=0     默认关（Watch：只写字段不改分）
  SURGE_AMBUSH_STRONG_MULT=1.15
  SURGE_AMBUSH_MID_MULT=1.05
  SURGE_AMBUSH_ZT_LOOKBACK=10

与 wind_sector_prefer_boost：ambush 开且 apply 时 prefer 乘子应关掉（见该模块）。
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable

from consec_inflow import _bare, consec_for_symbol, load_fund_hist

ROOT = Path(__file__).resolve().parent
FLOW = ROOT / "data" / "wind_board_flow.json"
WIND_STOCK = ROOT / "data" / "wind_candidate_flow.json"
IND_MAP = ROOT / "data" / "stock_industry_map.json"
ZT_RECENT = ROOT / "data" / "zt_recent_codes.json"
ZT_SECTOR_TOP = ROOT / "data" / "zt_sector_top.json"

NAME_ALIASES: dict[str, list[str]] = {
    "电力": ["电力", "公用事业", "火电", "水电", "绿电"],
    "公用事业": ["公用事业", "电力"],
    "医药生物": ["医药生物", "化学制药", "中药", "生物制品", "医药"],
    "半导体": ["半导体", "集成电路", "电子"],
    "电子": ["电子", "半导体", "消费电子"],
    "电力设备": ["电力设备", "电网设备", "电池", "光伏设备", "风电设备"],
    "电网设备": ["电网设备", "电力设备"],
    "电池": ["电池", "电力设备"],
    "计算机": ["计算机", "软件开发", "IT服务"],
    "汽车": ["汽车", "汽车零部件"],
    "汽车零部件": ["汽车零部件", "汽车"],
    "机械设备": ["机械设备", "通用设备", "专用设备", "自动化设备"],
    "有色金属": ["有色金属", "工业金属", "贵金属"],
    "工业金属": ["工业金属", "有色金属"],
    "房地产": ["房地产", "房地产开发"],
}


def _env_on(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _fenv(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)) or default)
    except (TypeError, ValueError):
        return default


def _ienv(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)) or default)
    except (TypeError, ValueError):
        return default


def enabled() -> bool:
    """True = 写字段且改分；False = Watch 只写字段。"""
    return _env_on("ENABLE_SURGE_AMBUSH", False)


def annotate_only() -> bool:
    """始终可注解；enabled 决定是否乘分。"""
    return True


def _clean_name(n: str) -> str:
    return re.sub(r"\(申万\)$", "", str(n or "")).strip()


def _names_match(a: str, b: str) -> bool:
    a, b = _clean_name(a), _clean_name(b)
    if not a or not b:
        return False
    if a == b:
        return True
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    if len(short) >= 2 and short in long:
        return True
    return False


def _expand(names: list[str]) -> set[str]:
    out: set[str] = set()
    for n in names:
        n = _clean_name(n)
        if not n:
            continue
        out.add(n)
        for a in NAME_ALIASES.get(n, []):
            out.add(a)
    return out


def _hit(labels: list[str], name_set: set[str]) -> str | None:
    for lab in labels:
        for n in name_set:
            if _names_match(lab, n):
                return n
    return None


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_ind_map() -> dict[str, dict]:
    raw = _load_json(IND_MAP)
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict] = {}
    for k, v in raw.items():
        code = _bare(k)
        if isinstance(v, str):
            out[code] = {"industry": v}
        elif isinstance(v, dict):
            out[code] = v
    return out


def _item_labels(item: dict, ind_map: dict) -> list[str]:
    labels: list[str] = []
    for k in ("sector", "industry", "industry_name", "所属行业"):
        v = str(item.get(k) or "").strip()
        if v and v not in labels:
            labels.append(v)
    code = _bare(item.get("symbol") or item.get("code") or "")
    meta = ind_map.get(code) or {}
    for k in ("industry", "industry_l3", "industry_l2", "industry_l1"):
        v = str(meta.get(k) or "").strip()
        if v and v not in labels:
            labels.append(v)
    return labels


def _load_prefer_set() -> set[str]:
    flow = _load_json(FLOW)
    if not isinstance(flow, dict):
        return set()
    consult = flow.get("consult") or {}
    return _expand(list(consult.get("prefer") or []))


def _load_wind_stock() -> dict[str, dict]:
    raw = _load_json(WIND_STOCK)
    if not isinstance(raw, dict):
        return {}
    items = raw.get("items") or {}
    if not isinstance(items, dict):
        return {}
    out = {}
    for k, v in items.items():
        if isinstance(v, dict):
            out[_bare(k)] = v
    return out


def _load_zt_codes() -> set[str]:
    """近 N 日涨停码集合。支持 list 或 {codes:[...]} / {items:[{symbol}]}。"""
    raw = _load_json(ZT_RECENT)
    if raw is None:
        return set()
    codes: set[str] = set()
    if isinstance(raw, list):
        for x in raw:
            if isinstance(x, str):
                codes.add(_bare(x))
            elif isinstance(x, dict):
                codes.add(_bare(x.get("symbol") or x.get("code") or ""))
    elif isinstance(raw, dict):
        for x in raw.get("codes") or raw.get("symbols") or []:
            codes.add(_bare(x if isinstance(x, str) else (x.get("symbol") or x.get("code") or "")))
        for x in raw.get("items") or []:
            if isinstance(x, dict):
                codes.add(_bare(x.get("symbol") or x.get("code") or ""))
            elif isinstance(x, str):
                codes.add(_bare(x))
    codes.discard("")
    return codes


def _load_zt_sector_top() -> set[str]:
    raw = _load_json(ZT_SECTOR_TOP)
    if raw is None:
        return set()
    names: list[str] = []
    if isinstance(raw, list):
        names = [str(x) for x in raw]
    elif isinstance(raw, dict):
        names = [str(x) for x in (raw.get("sectors") or raw.get("top") or [])]
    return _expand(names)


def score_ambush(
    item: dict,
    *,
    consec: int,
    wind_row: dict | None,
    prefer: set[str],
    zt_sectors: set[str],
    zt_codes: set[str],
    labels: list[str],
) -> dict[str, Any]:
    fund_pts = 0
    sector_pts = 0
    mom_pts = 0
    details: list[str] = []

    if consec >= 4:
        fund_pts += 3
        details.append(f"consec>={consec}:+3")
    elif consec >= 3:
        fund_pts += 2
        details.append(f"consec>={consec}:+2")

    inst = large = None
    if isinstance(wind_row, dict):
        try:
            if wind_row.get("inst_net") is not None:
                inst = float(wind_row["inst_net"])
        except (TypeError, ValueError):
            inst = None
        try:
            if wind_row.get("large_net") is not None:
                large = float(wind_row["large_net"])
        except (TypeError, ValueError):
            large = None
    if inst is not None and inst > 0:
        fund_pts += 2
        details.append("inst_in:+2")
        if large is not None and large > 0:
            fund_pts += 1
            details.append("inst+large:+1")
    fund_pts = min(5, fund_pts)

    prefer_hit = _hit(labels, prefer) if prefer else None
    if prefer_hit:
        sector_pts += 2
        details.append(f"prefer:{prefer_hit}:+2")
    zt_hit = _hit(labels, zt_sectors) if zt_sectors else None
    if zt_hit:
        sector_pts += 1
        details.append(f"zt_sector:{zt_hit}:+1")
    sector_pts = min(3, sector_pts)

    code = _bare(item.get("symbol") or item.get("code") or "")
    if code and code in zt_codes:
        mom_pts = 2
        details.append("recent_zt:+2")
    mom_pts = min(2, mom_pts)

    total = fund_pts + sector_pts + mom_pts
    if total >= 7:
        tier = "strong"
    elif total >= 4:
        tier = "mid"
    else:
        tier = "plain"

    return {
        "surge_ambush_score": total,
        "surge_ambush_fund": fund_pts,
        "surge_ambush_sector": sector_pts,
        "surge_ambush_momentum": mom_pts,
        "surge_ambush_tier": tier,
        "surge_ambush_detail": ";".join(details),
        "consec_inflow_days": consec,
        "surge_ambush_prefer_hit": prefer_hit,
        "wind_inst_net": inst,
        "wind_large_net": large,
    }


def apply_surge_ambush_score(
    items: list[dict[str, Any]],
    log: Callable[..., Any] = print,
) -> list[dict[str, Any]]:
    if not items:
        return items

    apply_mult = enabled()
    strong_m = _fenv("SURGE_AMBUSH_STRONG_MULT", 1.15)
    mid_m = _fenv("SURGE_AMBUSH_MID_MULT", 1.05)

    fund_hist = load_fund_hist()
    prefer = _load_prefer_set()
    wind_stocks = _load_wind_stock()
    zt_codes = _load_zt_codes()
    zt_sectors = _load_zt_sector_top()
    ind_map = _load_ind_map()

    n_b = n_strong = n_mid = n_plain = 0
    out: list[dict] = []
    for it in items:
        row = dict(it)
        code = _bare(row.get("symbol") or row.get("code") or "")
        consec = consec_for_symbol(code, fund_hist) if code else 0
        labels = _item_labels(row, ind_map)
        scored = score_ambush(
            row,
            consec=consec,
            wind_row=wind_stocks.get(code),
            prefer=prefer,
            zt_sectors=zt_sectors,
            zt_codes=zt_codes,
            labels=labels,
        )
        row.update(scored)

        if str(row.get("arm") or "") != "B":
            out.append(row)
            continue

        n_b += 1
        tier = scored["surge_ambush_tier"]
        if tier == "strong":
            n_strong += 1
            mult = strong_m
        elif tier == "mid":
            n_mid += 1
            mult = mid_m
        else:
            n_plain += 1
            mult = 1.0

        row["surge_ambush_mult"] = mult
        row["surge_ambush_apply"] = bool(apply_mult and mult != 1.0)
        if apply_mult and mult != 1.0:
            try:
                base = float(row.get("score") or 0)
            except (TypeError, ValueError):
                base = 0.0
            row["score_before_surge_ambush"] = round(base, 4)
            row["score"] = round(base * mult, 4)

        out.append(row)

    out.sort(key=lambda x: -float(x.get("score") or 0))
    log(
        f"  surge_ambush: apply={int(apply_mult)} B={n_b} "
        f"strong(≥7)={n_strong} mid(4-6)={n_mid} plain(<4)={n_plain} "
        f"prefer_n={len(prefer)} zt_codes={len(zt_codes)} zt_sectors={len(zt_sectors)} "
        f"fund_hist={len(fund_hist)}"
    )
    return out
