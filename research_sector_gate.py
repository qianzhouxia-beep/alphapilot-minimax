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
AUCTION_HEAT_PATH = ROOT / "output" / "call_auction_sector_heat.json"
BYPASS_POOL_PATH = ROOT / "output" / "hot_sector_bypass_pool.json"
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


def _load_auction_hot_sectors(min_heat: float | None = None) -> set[str]:
    """读取 09:25 集合竞价板块热度，返回 heat_score 达标的板块名集合（L1）。"""
    if min_heat is None:
        try:
            min_heat = float(os.environ.get("AUCTION_SECTOR_HEAT_MIN", "0.15") or 0.15)
        except (TypeError, ValueError):
            min_heat = 0.15
    d = _load_json(AUCTION_HEAT_PATH)
    if not isinstance(d, dict):
        return set()
    hot = set()
    for r in d.get("hot_sectors") or []:
        try:
            hs = float(r.get("heat_score") or 0)
        except (TypeError, ValueError):
            hs = 0.0
        if hs >= min_heat:
            sec = str(r.get("sector") or "").strip()
            if sec:
                hot.add(sec)
    return hot


def _load_bypass_industries() -> set[str]:
    """读取 05:00 收盘资金流主线旁路池的强势行业（L2），返回名称集合。"""
    d = _load_json(BYPASS_POOL_PATH)
    if not isinstance(d, dict) or not d.get("enabled", True):
        return set()
    inds = set()
    for r in d.get("industries") or []:
        name = str(r.get("name") or "").strip()
        if name:
            inds.add(name)
    return inds


def apply_research_sector_gate(
    items: list[dict[str, Any]],
    bias: dict | None = None,
    mode: str | None = None,
    prefer_boost: float | None = None,
) -> list[dict[str, Any]]:
    """对候选池应用研报偏好 + 竞价/资金主线加权。

    定位（与行业硬门分轨）：
      - avoid 不再硬剔除（软降权），prefer 加分，避免把池子挤进冷票
      - 竞价热点（call_auction_sector_heat，09:25）→ 硬加权
      - 资金主线（hot_sector_bypass_pool，05:00 收盘）→ 硬加权
      - 竞价 + 资金双命中 → 更高加权

    mode:
      off         — 不处理
      avoid_only  — 只硬剔除 avoid（旧兼容）
      prefer_soft — avoid 不删；prefer 加分（旧兼容，无竞价/主线加权）
      hybrid      — avoid 硬剔除 + prefer 加分（旧默认，兼容）
      soft_hybrid — avoid 软降权 + prefer 加分 + 竞价/主线硬加权（新默认）
    """
    mode = (mode or os.environ.get("RESEARCH_GATE_MODE", "soft_hybrid")).strip().lower()
    if prefer_boost is None:
        try:
            prefer_boost = float(os.environ.get("RESEARCH_PREFER_BOOST", "0.08") or 0.08)
        except (TypeError, ValueError):
            prefer_boost = 0.08
    try:
        auction_boost = float(os.environ.get("AUCTION_SECTOR_BOOST", "0.18") or 0.18)
    except (TypeError, ValueError):
        auction_boost = 0.18
    try:
        bypass_boost = float(os.environ.get("BYPASS_SECTOR_BOOST", "0.18") or 0.18)
    except (TypeError, ValueError):
        bypass_boost = 0.18
    try:
        double_boost = float(os.environ.get("DOUBLE_SECTOR_BOOST", "0.25") or 0.25)
    except (TypeError, ValueError):
        double_boost = 0.25
    try:
        avoid_penalty = float(os.environ.get("RESEARCH_AVOID_PENALTY", "0.06") or 0.06)
    except (TypeError, ValueError):
        avoid_penalty = 0.06
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

    # 竞价热点 + 资金主线（soft_hybrid 才启用）
    auction_hot_set: set[str] = set()
    bypass_hot_set: set[str] = set()
    conflict_set: set[str] = set()
    if mode == "soft_hybrid":
        auction_hot_set = _load_auction_hot_sectors()
        bypass_hot_set = _load_bypass_industries()
        if auction_hot_set:
            print(
                f"  research_sector_gate: 竞价热点 {len(auction_hot_set)} 个: {sorted(auction_hot_set)}",
                flush=True,
            )
        if bypass_hot_set:
            print(
                f"  research_sector_gate: 资金主线 {len(bypass_hot_set)} 个: {sorted(bypass_hot_set)}",
                flush=True,
            )
        # 信号源冲突板块（研报 vs 资金主线 vs 竞价）→ 自动降权
        try:
            from signal_conflict_detector import conflict_sectors

            conflict_set = conflict_sectors()
            if conflict_set:
                print(
                    f"  research_sector_gate: ⚠️ 信号矛盾板块 {len(conflict_set)} 个: {sorted(conflict_set)} → 降权",
                    flush=True,
                )
        except Exception as e:
            print(f"  research_sector_gate: 冲突检测跳过: {e}", flush=True)

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
    soft_avoid = 0
    prefer_hits = 0
    auction_hits = 0
    bypass_hits = 0
    double_hits = 0
    dropped_rows: list[dict] = []

    for it in items:
        row = dict(it)
        labels = _item_labels(row, ind_map, concept_map)
        hit_avoid = _hit_set(labels, avoid_set) if mode in ("avoid_only", "hybrid") else None
        hit_prefer = _hit_set(labels, prefer_set) if mode in ("prefer_soft", "hybrid", "soft_hybrid") else None

        if hit_avoid:
            # 旧模式：硬剔除
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

        base = 0.0
        try:
            base = float(row.get("score") or 0)
        except (TypeError, ValueError):
            base = 0.0

        mult = 1.0

        if mode == "soft_hybrid":
            # avoid → 软降权（不剔除）
            hit_avoid_soft = _hit_set(labels, avoid_set)
            if hit_avoid_soft:
                soft_avoid += 1
                row["research_avoid_hit"] = hit_avoid_soft
                mult *= (1.0 - avoid_penalty)

            # prefer → 加分
            if hit_prefer:
                prefer_hits += 1
                row["research_prefer_hit"] = hit_prefer
                row["research_tier"] = "prefer"
                mult *= (1.0 + prefer_boost)
            else:
                row["research_tier"] = "other"

            # 竞价热点 → 硬加权
            hit_auction = _hit_set(labels, auction_hot_set) if auction_hot_set else None
            # 资金主线 → 硬加权
            hit_bypass = _hit_set(labels, bypass_hot_set) if bypass_hot_set else None
            # 信号矛盾板块 → 降权
            hit_conflict = _hit_set(labels, conflict_set) if conflict_set else None
            if hit_conflict:
                row["signal_conflict_hit"] = hit_conflict
                mult *= 0.90

            if hit_auction and hit_bypass:
                double_hits += 1
                row["auction_sector_hit"] = hit_auction
                row["bypass_sector_hit"] = hit_bypass
                mult *= (1.0 + double_boost)
                row["sector_hard_boost"] = "auction+bypass"
            elif hit_auction:
                auction_hits += 1
                row["auction_sector_hit"] = hit_auction
                mult *= (1.0 + auction_boost)
                row["sector_hard_boost"] = "auction"
            elif hit_bypass:
                bypass_hits += 1
                row["bypass_sector_hit"] = hit_bypass
                mult *= (1.0 + bypass_boost)
                row["sector_hard_boost"] = "bypass"

            if wind_prefer_set and _hit_set(labels, wind_prefer_set):
                row["wind_prefer_hit"] = _hit_set(labels, wind_prefer_set)
            if rotation_watch_set and _hit_set(labels, rotation_watch_set):
                row["wind_rotation_watch"] = _hit_set(labels, rotation_watch_set)

            if mult != 1.0:
                row["score_before_research_prefer"] = round(base, 4)
                row["score"] = round(base * mult, 4)
                row["research_mult"] = round(mult, 4)

            kept.append(row)
            continue

        # ── 旧模式（avoid_only / prefer_soft / hybrid）原逻辑 ──
        if hit_prefer:
            prefer_hits += 1
            row["research_prefer_hit"] = hit_prefer
            row["research_tier"] = "prefer"
            if wind_prefer_set and _hit_set(labels, wind_prefer_set):
                row["wind_prefer_hit"] = _hit_set(labels, wind_prefer_set)
            if rotation_watch_set and _hit_set(labels, rotation_watch_set):
                row["wind_rotation_watch"] = _hit_set(labels, rotation_watch_set)
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

    # prefer/加权股排在同档前面（soft_hybrid 已直接用 score 排序）
    if mode == "soft_hybrid":
        final = sorted(final, key=lambda x: -float(x.get("score") or 0))
    else:
        final = sorted(
            final,
            key=lambda x: (
                0 if x.get("research_tier") == "prefer" else 1,
                -float(x.get("score") or 0),
            ),
        )

    conflict_hits = sum(1 for x in kept if x.get("signal_conflict_hit"))
    print(
        f"  research_sector_gate[{mode}]: in={len(items)} avoid_drop={dropped_avoid} "
        f"soft_avoid={soft_avoid} prefer_hits={prefer_hits} "
        f"auction_hits={auction_hits} bypass_hits={bypass_hits} double_hits={double_hits} "
        f"conflict_hits={conflict_hits} out={len(final)} narrowed={narrowed} boost={prefer_boost}",
        flush=True,
    )
    # 附加元数据供晨间脚本写淘汰清单
    for row in final:
        row.setdefault("_research_drop_log", dropped_rows)
    if final:
        final[0]["_research_gate_meta"] = {
            "avoid_drop": dropped_avoid,
            "soft_avoid": soft_avoid,
            "prefer_hits": prefer_hits,
            "auction_hits": auction_hits,
            "bypass_hits": bypass_hits,
            "double_hits": double_hits,
            "conflict_hits": conflict_hits,
            "narrowed": narrowed,
            "prefer_boost": prefer_boost,
            "dropped": dropped_rows,
        }
    elif dropped_rows:
        # 空池时也把原因挂在 items 原引用上无意义；返回空
        pass
    return final
