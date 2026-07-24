#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""热门板块优先：对资金 allow 行业/概念成分软加分，提升进 Top1–3 概率。

不硬删、不改宇宙定义。目标：少选「冷板块慢票」，多让当日主线票参与排序。

Env:
  ENABLE_HOT_SECTOR_PREFER=1     默认开
  HOT_SECTOR_INDUSTRY_BOOST=0.08 行业 allow 分数乘数增量（score *= 1+b）
  HOT_SECTOR_CONCEPT_BOOST=0.04  仅概念 allow（行业非 allow）时增量
"""
from __future__ import annotations

import os
from typing import Any, Callable


def _env_on(name: str, default: bool = True) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def enabled() -> bool:
    return _env_on("ENABLE_HOT_SECTOR_PREFER", True)


def _f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)) or default)
    except (TypeError, ValueError):
        return default


def _bare(sym: str) -> str:
    s = str(sym or "").lower().replace("sh", "").replace("sz", "").replace("bj", "")
    return s[-6:] if len(s) >= 6 else s


def _name_hit(aliases: list[str], allow_name: str) -> bool:
    """热门优先用更松的匹配（≥2 字子串），提高主线召回。"""
    a = (allow_name or "").strip()
    if not a:
        return False
    for al in aliases:
        b = (al or "").strip()
        if not b:
            continue
        if a == b:
            return True
        short, long = (a, b) if len(a) <= len(b) else (b, a)
        if len(short) >= 2 and short in long:
            return True
    return False


def apply_hot_sector_prefer_boost(
    items: list[dict],
    snap: dict | None = None,
    log: Callable[..., Any] = print,
) -> list[dict]:
    if not enabled() or not items:
        return items

    if snap is None:
        try:
            from sector_rotation_gate import build_snapshot

            snap = build_snapshot()
        except Exception as e:
            log(f"  ⚠️ 热门板块加分跳过(无快照): {e}")
            return items

    ind_boost = _f("HOT_SECTOR_INDUSTRY_BOOST", 0.08)
    cpt_boost = _f("HOT_SECTOR_CONCEPT_BOOST", 0.04)
    allow_ind = [r.get("name") for r in ((snap.get("classes") or {}).get("allow") or []) if r.get("name")]
    allow_cpt = [
        r.get("name") for r in ((snap.get("concept_classes") or {}).get("allow") or []) if r.get("name")
    ]

    try:
        from sector_rotation_gate import industry_aliases, load_stock_concept_map, load_stock_industry_map

        imap = load_stock_industry_map() or {}
        cmap = load_stock_concept_map() or {}
    except Exception:
        imap, cmap = {}, {}

        def industry_aliases(meta):  # type: ignore
            if isinstance(meta, str):
                return [meta] if meta else []
            if isinstance(meta, dict):
                return [str(meta.get("industry_l1") or meta.get("industry") or "")]
            return []

    n_ind = n_cpt = 0
    out = []
    for it in items:
        nr = dict(it)
        bare = _bare(nr.get("symbol"))
        raw = float(nr.get("score") or 0)
        meta = imap.get(bare) or imap.get(str(nr.get("symbol") or "")) or {}
        aliases = industry_aliases(meta) if meta else []
        ind_name = ""
        if isinstance(meta, dict):
            ind_name = str(meta.get("industry_l1") or meta.get("industry") or "")
        elif isinstance(meta, str):
            ind_name = meta
            aliases = industry_aliases(ind_name)

        hit_ind = any(_name_hit(aliases or ([ind_name] if ind_name else []), a) for a in allow_ind[:12])
        concepts = cmap.get(bare) or cmap.get(str(nr.get("symbol") or "")) or []
        if isinstance(concepts, dict):
            concepts = concepts.get("concepts") or []
        if not isinstance(concepts, list):
            concepts = []
        hit_cpt = any(_name_hit([str(c) for c in concepts], a) for a in allow_cpt[:15])

        boost = 0.0
        if hit_ind:
            boost = ind_boost
            n_ind += 1
            nr["hot_sector_prefer"] = "industry_allow"
        elif hit_cpt:
            boost = cpt_boost
            n_cpt += 1
            nr["hot_sector_prefer"] = "concept_allow"
        else:
            nr["hot_sector_prefer"] = None

        if boost > 0:
            nr["score_before_hot_prefer"] = raw
            nr["score"] = round(raw * (1.0 + boost), 6)
            nr["hot_sector_boost"] = boost
        out.append(nr)

    out.sort(key=lambda x: -float(x.get("score") or 0))
    log(f"  热门板块优先加分: industry_hit={n_ind} concept_hit={n_cpt} ind_b={ind_boost} cpt_b={cpt_boost}")
    return out
