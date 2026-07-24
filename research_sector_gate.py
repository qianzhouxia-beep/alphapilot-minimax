#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""板块研报 → 晨间选股偏好门控。

设计（刻意不与 sector_rotation_gate 的短周期资金硬门重复）：
  - 输入：output/sector_research_bias.json（由研报生成或盘前刷新写出）
  - prefer：研报第一/二梯队（强势+改善）→ 排名时优先
  - avoid：多周期弱势 + 恶化 + API avoid → 硬剔除
  - 若 prefer 过滤后池子为空 → 回退到仅 avoid 后的池（不空仓）

用法:
  from research_sector_gate import apply_research_sector_gate
  items = apply_research_sector_gate(items)
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
BIAS_PATH = ROOT / "output" / "sector_research_bias.json"
DATA = ROOT / "data"
IND_MAP = DATA / "stock_industry_map.json"
CONCEPT_MAP = DATA / "stock_concept_map.json"

# 研报常用名 → 通达信/东财行业别名（扩充匹配面）
NAME_ALIASES: dict[str, list[str]] = {
    "电力": ["电力", "公用事业", "火电", "水电", "绿电"],
    "公用事业": ["公用事业", "电力", "水务", "燃气"],
    "医药生物": ["医药生物", "化学制药", "中药", "生物制品", "医疗服务", "医药"],
    "银行": ["银行", "国有大行", "股份制银行"],
    "白酒": ["白酒", "白酒Ⅱ", "食品饮料"],
    "食品饮料": ["食品饮料", "白酒", "饮料制造"],
    "石油石化": ["石油石化", "油气开采", "油服工程", "炼化"],
    "煤炭": ["煤炭", "煤炭开采", "焦炭"],
    "煤炭采选": ["煤炭采选", "煤炭", "煤炭开采"],
    "保险": ["保险", "保险Ⅱ"],
    "半导体": ["半导体", "半导体材料", "集成电路", "电子"],
    "电子": ["电子", "半导体", "消费电子", "元件", "光学光电子"],
    "白色家电": ["白色家电", "家电Ⅱ", "家用电器"],
    "养殖业": ["养殖业", "畜禽养殖", "饲料"],
    "IT服务": ["IT服务", "软件开发", "计算机"],
}


def _bare(sym: str) -> str:
    s = str(sym or "").lower().replace("sh", "").replace("sz", "").replace("bj", "")
    return s[-6:] if len(s) >= 6 else s


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_bias(path: Path | None = None) -> dict | None:
    p = path or BIAS_PATH
    d = _load_json(p)
    if not isinstance(d, dict):
        return None
    if not (d.get("prefer") or d.get("avoid")):
        return None
    return d


def _expand_names(names: list[str]) -> set[str]:
    out: set[str] = set()
    for n in names:
        n = str(n or "").strip()
        if not n:
            continue
        out.add(n)
        for a in NAME_ALIASES.get(n, []):
            out.add(a)
        # 去罗马数字后缀
        base = re.sub(r"[ⅡIIIⅢ123]+$", "", n).strip()
        if base:
            out.add(base)
            for a in NAME_ALIASES.get(base, []):
                out.add(a)
    return out


def _names_match(a: str, b: str) -> bool:
    a, b = (a or "").strip(), (b or "").strip()
    if not a or not b:
        return False
    if a == b:
        return True
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    if len(short) >= 4 and short in long:
        return True
    return False


def _item_labels(item: dict, ind_map: dict, concept_map: dict) -> list[str]:
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
    concepts = concept_map.get(code) or []
    if isinstance(concepts, dict):
        concepts = concepts.get("concepts") or concepts.get("tags") or []
    for c in concepts[:12]:
        if isinstance(c, dict):
            c = c.get("name") or c.get("concept")
        c = str(c or "").strip()
        if c and c not in labels:
            labels.append(c)
    return labels


def _hit_set(labels: list[str], name_set: set[str]) -> str | None:
    for lab in labels:
        for n in name_set:
            if _names_match(lab, n):
                return n
    return None


def apply_research_sector_gate(
    items: list[dict[str, Any]],
    bias: dict | None = None,
    mode: str | None = None,
    prefer_boost: float | None = None,
) -> list[dict[str, Any]]:
    """对候选池应用研报偏好。

    定位（与外盘隔夜分工）：
      - 收盘/盘前研报：用 1/2/3/5 日资金结构判断板块趋势梯队（prefer/avoid）
      - 不声称能预测「明天瞬时净流入」；avoid 硬剔，prefer 做分数加权 + 优先排序

    mode:
      off         — 不处理
      avoid_only  — 只硬剔除 avoid
      prefer_soft — avoid 不删；prefer 加分（不缩池）
      hybrid      — avoid 硬剔除 + prefer 加分；若 prefer 命中≥1 则优先缩到 prefer
                    （可用 RESEARCH_PREFER_NARROW=0 关闭缩池，只保留加分）
    """
    mode = (mode or os.environ.get("RESEARCH_GATE_MODE", "hybrid")).strip().lower()
    if prefer_boost is None:
        try:
            prefer_boost = float(os.environ.get("RESEARCH_PREFER_BOOST", "0.08") or 0.08)
        except (TypeError, ValueError):
            prefer_boost = 0.08
    narrow_prefer = os.environ.get("RESEARCH_PREFER_NARROW", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )

    if mode in ("off", "0", "false", "none"):
        return items
    if not items:
        return items

    if bias is None:
        bias = load_bias()
    if not bias:
        print("  research_sector_gate: no bias file, skip", flush=True)
        return items

    prefer_set = _expand_names(list(bias.get("prefer") or []))
    avoid_set = _expand_names(list(bias.get("avoid") or []))
    # 万得轮动观察：只标注，不硬剔（与交易资金门分轨）
    wind_prefer_set = _expand_names(list(bias.get("wind_prefer") or []))
    rotation_watch_set = _expand_names(list(bias.get("rotation_watch") or []))
    # prefer 优先：同时出现在两边时不算 avoid
    avoid_set -= prefer_set

    ind_raw = _load_json(IND_MAP) or {}
    ind_map: dict[str, dict] = {}
    for k, v in ind_raw.items():
        code = _bare(k)
        if isinstance(v, str):
            ind_map[code] = {"industry": v}
        elif isinstance(v, dict):
            ind_map[code] = v

    concept_raw = _load_json(CONCEPT_MAP) or {}
    concept_map: dict[str, Any] = {_bare(k): v for k, v in concept_raw.items()}

    kept: list[dict] = []
    dropped_avoid = 0
    prefer_hits = 0
    dropped_rows: list[dict] = []

    for it in items:
        row = dict(it)
        labels = _item_labels(row, ind_map, concept_map)
        hit_avoid = _hit_set(labels, avoid_set) if mode in ("avoid_only", "hybrid") else None
        hit_prefer = _hit_set(labels, prefer_set) if mode in ("prefer_soft", "hybrid") else None

        if hit_avoid:
            dropped_avoid += 1
            dropped_rows.append(
                {
                    "symbol": row.get("symbol"),
                    "name": row.get("name"),
                    "reason": "research_avoid",
                    "hit": hit_avoid,
                    "score": row.get("score"),
                }
            )
            continue
        if hit_prefer:
            prefer_hits += 1
            row["research_prefer_hit"] = hit_prefer
            row["research_tier"] = "prefer"
            if wind_prefer_set and _hit_set(labels, wind_prefer_set):
                row["wind_prefer_hit"] = _hit_set(labels, wind_prefer_set)
            if rotation_watch_set and _hit_set(labels, rotation_watch_set):
                row["wind_rotation_watch"] = _hit_set(labels, rotation_watch_set)
            try:
                base = float(row.get("score") or 0)
            except (TypeError, ValueError):
                base = 0.0
            row["score_before_research_prefer"] = round(base, 4)
            row["score"] = round(base * (1.0 + float(prefer_boost)), 4)
            row["research_prefer_boost"] = float(prefer_boost)
        else:
            row["research_tier"] = "other"
            if wind_prefer_set and _hit_set(labels, wind_prefer_set):
                row["wind_prefer_hit"] = _hit_set(labels, wind_prefer_set)
            if rotation_watch_set and _hit_set(labels, rotation_watch_set):
                row["wind_rotation_watch"] = _hit_set(labels, rotation_watch_set)
        kept.append(row)

    if mode in ("prefer_soft", "hybrid") and prefer_hits > 0 and narrow_prefer:
        preferred = [x for x in kept if x.get("research_tier") == "prefer"]
        # 缩池时把被挤出的 other 记入淘汰原因
        for x in kept:
            if x.get("research_tier") != "prefer":
                dropped_rows.append(
                    {
                        "symbol": x.get("symbol"),
                        "name": x.get("name"),
                        "reason": "not_in_prefer_narrow",
                        "score": x.get("score"),
                    }
                )
        final = preferred
        narrowed = True
    else:
        final = kept
        narrowed = False

    # prefer 股排在同档前面（即便未缩池）
    final = sorted(
        final,
        key=lambda x: (
            0 if x.get("research_tier") == "prefer" else 1,
            -float(x.get("score") or 0),
        ),
    )

    print(
        f"  research_sector_gate[{mode}]: in={len(items)} avoid_drop={dropped_avoid} "
        f"prefer_hits={prefer_hits} out={len(final)} "
        f"narrowed={narrowed} boost={prefer_boost} "
        f"bias_date={bias.get('date')} session={bias.get('session')}",
        flush=True,
    )
    # 附加元数据供晨间脚本写淘汰清单
    for row in final:
        row.setdefault("_research_drop_log", dropped_rows)
    if final:
        final[0]["_research_gate_meta"] = {
            "avoid_drop": dropped_avoid,
            "prefer_hits": prefer_hits,
            "narrowed": narrowed,
            "prefer_boost": prefer_boost,
            "dropped": dropped_rows,
        }
    elif dropped_rows:
        # 空池时也把原因挂在 items 原引用上无意义；返回空
        pass
    return final
