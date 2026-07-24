#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""万得板块 prefer/avoid → 仅 B 臂软加权（不硬删）。

读 data/wind_board_flow.json consult 视图：
  prefer (fresh_inflow 连续1–2日) → score × WIND_B_PREFER_MULT (默认 1.05)
  rotation_watch (连续≥3日)       → score × WIND_B_WATCH_MULT  (默认 1.00)
  avoid (当日净流出)               → score × WIND_B_AVOID_MULT  (默认 0.90)

当 ENABLE_SURGE_AMBUSH=1（埋伏分已开）时：prefer 乘子强制 1.0（防双重计分），
avoid / rotation_watch 仍生效。

Env:
  ENABLE_WIND_B_SECTOR_BOOST=1   默认开（需同时有 arm=B）
  WIND_B_PREFER_MULT=1.05
  WIND_B_WATCH_MULT=1.0
  WIND_B_AVOID_MULT=0.9
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent
FLOW = ROOT / "data" / "wind_board_flow.json"
IND_MAP = ROOT / "data" / "stock_industry_map.json"

# 与 research_sector_gate 对齐的别名（精简版）
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
    "房地产": ["房地产", "房地产开发"],
}


def _env_on(name: str, default: bool = True) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _fenv(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)) or default)
    except (TypeError, ValueError):
        return default


def enabled() -> bool:
    return _env_on("ENABLE_WIND_B_SECTOR_BOOST", True)


def _bare(sym: str) -> str:
    s = str(sym or "").lower().replace("sh", "").replace("sz", "").replace("bj", "")
    return s[-6:] if len(s) >= 6 else s


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


def _load_flow() -> dict:
    if not FLOW.exists():
        return {}
    try:
        return json.loads(FLOW.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_ind_map() -> dict[str, dict]:
    if not IND_MAP.exists():
        return {}
    try:
        raw = json.loads(IND_MAP.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, dict] = {}
    for k, v in (raw or {}).items():
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


def apply_wind_b_sector_boost(
    items: list[dict[str, Any]],
    log: Callable[..., Any] = print,
) -> list[dict[str, Any]]:
    if not enabled() or not items:
        return items

    flow = _load_flow()
    consult = (flow.get("consult") or {}) if isinstance(flow, dict) else {}
    prefer = _expand(list(consult.get("prefer") or []))
    avoid = _expand(list(consult.get("avoid") or []))
    watch = _expand(list(consult.get("rotation_watch") or []))
    if not (prefer or avoid or watch):
        log("  wind_b_sector_boost: no consult prefer/avoid, skip")
        return items

    # 埋伏分开时 prefer 已计入 surge_ambush，避免 ×1.05 双计
    ambush_on = False
    try:
        from surge_ambush_score import enabled as _ambush_on

        ambush_on = bool(_ambush_on())
    except Exception:
        ambush_on = _env_on("ENABLE_SURGE_AMBUSH", False)

    prefer_m = 1.0 if ambush_on else _fenv("WIND_B_PREFER_MULT", 1.05)
    watch_m = _fenv("WIND_B_WATCH_MULT", 1.0)
    avoid_m = _fenv("WIND_B_AVOID_MULT", 0.9)
    ind_map = _load_ind_map()

    n_pref = n_watch = n_avoid = n_b = 0
    out: list[dict] = []
    for it in items:
        row = dict(it)
        if str(row.get("arm") or "") != "B":
            out.append(row)
            continue
        n_b += 1
        labels = _item_labels(row, ind_map)
        try:
            base = float(row.get("score") or 0)
        except (TypeError, ValueError):
            base = 0.0
        mult = 1.0
        tag = None
        hit = _hit(labels, prefer)
        if hit and not ambush_on:
            mult = prefer_m
            tag = "prefer"
            n_pref += 1
        elif hit and ambush_on:
            # 只打标签，不改分
            row["wind_b_sector_tag"] = "prefer_deferred_to_ambush"
            row["wind_b_sector_hit"] = hit
            row["wind_b_sector_mult"] = 1.0
            n_pref += 1
            out.append(row)
            continue
        else:
            hit = _hit(labels, avoid)
            if hit:
                mult = avoid_m
                tag = "avoid"
                n_avoid += 1
            else:
                hit = _hit(labels, watch)
                if hit:
                    mult = watch_m
                    tag = "rotation_watch"
                    n_watch += 1
        if tag:
            row["score_before_wind_b_sector"] = round(base, 4)
            row["score"] = round(base * mult, 4)
            row["wind_b_sector_tag"] = tag
            row["wind_b_sector_hit"] = hit
            row["wind_b_sector_mult"] = mult
        out.append(row)

    out.sort(key=lambda x: -float(x.get("score") or 0))
    log(
        f"  wind_b_sector_boost: B={n_b} prefer×{prefer_m}={n_pref} "
        f"watch×{watch_m}={n_watch} avoid×{avoid_m}={n_avoid} "
        f"ambush_prefer_off={int(ambush_on)} "
        f"asof={flow.get('asof')} session={flow.get('session')}"
    )
    return out
