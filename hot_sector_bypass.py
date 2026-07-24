#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主线行业旁路池 — 缓解启动形态硬门误杀资金主线票。

用盘前板块资金流入 TopK 行业的成分股，与启动形态池合并进评分宇宙。
非主线行业仍须命中启动形态。

Env:
  ENABLE_HOT_SECTOR_BYPASS=1   默认开
  HOT_SECTOR_TOP_K=8           allow 行业取前 K
  HOT_SECTOR_MAX_N=600         旁路池上限
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
POOL_PATH = OUT / "hot_sector_bypass_pool.json"


def _env_on(name: str, default: bool = True) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _bare(sym: str) -> str:
    s = str(sym or "").lower().replace("sh", "").replace("sz", "").replace("bj", "")
    return s[-6:] if len(s) >= 6 else s


def enabled() -> bool:
    return _env_on("ENABLE_HOT_SECTOR_BYPASS", True)


def _hits_allow(aliases: list[str], allow_name: str) -> bool:
    """旁路匹配：精确优先；子串要求 ≥3 字，避免「通信」误伤「通信网络设备及器件」。"""
    a = (allow_name or "").strip()
    if not a:
        return False
    for al in aliases:
        b = (al or "").strip()
        if not b:
            continue
        if a == b:
            return True
        if len(a) >= 3 and a in b:
            return True
        if len(b) >= 3 and b in a:
            return True
    return False


def build_hot_sector_bypass_pool(
    snap: dict | None = None,
    top_k: int | None = None,
    max_n: int | None = None,
    log=print,
) -> dict[str, Any]:
    """构建主线旁路池并写入 output/hot_sector_bypass_pool.json。"""
    top_k = int(top_k if top_k is not None else os.environ.get("HOT_SECTOR_TOP_K", "8"))
    max_n = int(max_n if max_n is not None else os.environ.get("HOT_SECTOR_MAX_N", "600"))

    if not enabled():
        out = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "enabled": False,
            "industries": [],
            "symbols": [],
            "items": [],
            "n": 0,
            "note": "ENABLE_HOT_SECTOR_BYPASS=0",
        }
        OUT.mkdir(parents=True, exist_ok=True)
        POOL_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        log("  ⏭ 主线旁路关闭（ENABLE_HOT_SECTOR_BYPASS=0）")
        return out

    from sector_rotation_gate import (
        build_snapshot,
        industry_aliases,
        load_stock_concept_map,
        load_stock_industry_map,
    )

    snap = snap or build_snapshot()
    allow_rows = list((snap.get("classes") or {}).get("allow") or [])[: max(1, top_k)]
    industries = [
        {
            "name": r.get("name"),
            "net_yi": float(r.get("net_yi") or 0),
            "change_pct": r.get("change_pct"),
            "rank": r.get("rank") or (i + 1),
        }
        for i, r in enumerate(allow_rows)
        if r.get("name")
    ]
    allow_names = [x["name"] for x in industries]
    weights = {x["name"]: max(float(x["net_yi"] or 0), 0.01) for x in industries}

    c_allow_rows = list((snap.get("concept_classes") or {}).get("allow") or [])[:12]
    c_weights = {
        str(r.get("name")): max(float(r.get("net_yi") or 0), 0.01)
        for r in c_allow_rows
        if r.get("name")
    }
    # 科技向概念额外加权（主线旁路目标）
    for kw in ("科技", "芯片", "半导体", "通信", "电子", "算力", "AI", "光模块"):
        for cn in list(c_weights.keys()):
            if kw in cn:
                c_weights[cn] = c_weights[cn] * 1.15

    ind_map = load_stock_industry_map()
    try:
        concept_map = load_stock_concept_map()
    except Exception:
        concept_map = {}

    scored: dict[str, dict[str, Any]] = {}
    per_industry: dict[str, int] = {n: 0 for n in allow_names}
    hot_kw = ("芯片", "半导体", "CPO", "算力", "光模块", "AI", "存储", "PCB", "消费电子")

    for code, meta in ind_map.items():
        bare = _bare(code)
        if len(bare) != 6 or bare.startswith(("4", "8", "9")):
            continue
        aliases = industry_aliases(meta)
        hits = [an for an in allow_names if _hits_allow(aliases, an)]
        concepts = []
        raw_c = concept_map.get(bare) or concept_map.get(code) or []
        if isinstance(raw_c, dict):
            concepts = list(raw_c.get("concepts") or raw_c.get("names") or [])
        elif isinstance(raw_c, list):
            concepts = [str(x) for x in raw_c]
        c_hits = [cn for cn in c_weights if any(_hits_allow([str(c)], cn) for c in concepts)]
        if not hits and not c_hits:
            continue
        if not hits and c_hits:
            primary = c_hits[0]
            ind_hits: list[str] = []
        else:
            ind_hits = list(hits)
            primary = max(ind_hits, key=lambda h: weights.get(h, 0.0))
        score = sum(weights.get(h, 0) for h in ind_hits)
        score += sum(c_weights[h] * 0.35 for h in c_hits)
        for h in ind_hits:
            if any(al == h for al in aliases):
                score += weights.get(h, 0) * 0.25
        tech_concept = any(any(k in str(c) for k in hot_kw) for c in concepts)
        if tech_concept:
            score += max((weights.get(h, 0) for h in ind_hits), default=0) * 0.5
        scored[bare] = {
            "symbol": bare,
            "name": str(meta.get("name") or ""),
            "industry": primary or (c_hits[0] if c_hits else ""),
            "industries_hit": ind_hits,
            "concept_hits": c_hits[:5],
            "tech_concept": tech_concept,
            "score": score,
            "reason": "hot_sector_bypass",
            "selection_arm": "hot_sector_bypass",
        }
        for h in ind_hits:
            per_industry[h] = per_industry.get(h, 0) + 1

    # 按「命中的每个 allow 行业」分层（不是只按 primary），保证半导体/通信设备都有名额
    by_allow: dict[str, list[dict]] = {n: [] for n in allow_names}
    concept_only: list[dict] = []
    for row in scored.values():
        placed = False
        for h in row.get("industries_hit") or []:
            if h in by_allow:
                by_allow[h].append(row)
                placed = True
        if not placed:
            concept_only.append(row)
    for k in by_allow:
        # 去重保序：同一票可进多行业桶，取样时用 picked 去重
        uniq = {}
        for row in sorted(by_allow[k], key=lambda x: (-float(x["score"]), x["symbol"])):
            uniq[row["symbol"]] = row
        by_allow[k] = list(uniq.values())
        by_allow[k].sort(key=lambda x: (-float(x["score"]), x["symbol"]))
    concept_only.sort(key=lambda x: (-float(x["score"]), x["symbol"]))

    def _take_bucket(bucket: list[dict], n: int) -> list[dict]:
        """头部高分 + 全桶按代码均匀抽样，确保 603xxx 等也能进旁路。"""
        if n <= 0 or not bucket:
            return []
        if len(bucket) <= n:
            return list(bucket)
        head_n = max(1, int(n * 0.4))
        head = bucket[:head_n]
        head_syms = {x["symbol"] for x in head}
        need = n - len(head)
        by_code = [x for x in sorted(bucket, key=lambda r: r["symbol"]) if x["symbol"] not in head_syms]
        if need <= 0 or not by_code:
            return head
        step = max(1, len(by_code) // need)
        tail = [by_code[i] for i in range(0, len(by_code), step)][:need]
        # 若 stride 取不满，从尾部代码补
        if len(tail) < need:
            for row in reversed(by_code):
                if row["symbol"] in head_syms or any(t["symbol"] == row["symbol"] for t in tail):
                    continue
                tail.append(row)
                if len(tail) >= need:
                    break
        return head + tail

    min_per = max(25, max_n // max(len(allow_names) * 2, 1))
    w_sum = sum(weights.values()) or 1.0
    picked: dict[str, dict] = {}
    for name in allow_names:
        # 净流入大的行业多拿名额（电子可到 ~40%），stride 才能盖到 603xxx
        quota = max(min_per, int(round(max_n * (weights.get(name, 0.01) / w_sum))))
        quota = min(quota, max(80, max_n // 2))
        for row in _take_bucket(by_allow.get(name) or [], quota):
            if len(picked) >= max_n:
                break
            picked[row["symbol"]] = row
        if len(picked) >= max_n:
            break

    # 名额未满：按行业轮询补齐，避免全局高分把「电子」大类再次灌满
    if len(picked) < max_n:
        cursors = {n: 0 for n in allow_names}
        while len(picked) < max_n:
            progressed = False
            for name in allow_names:
                bucket = by_allow.get(name) or []
                while cursors[name] < len(bucket):
                    row = bucket[cursors[name]]
                    cursors[name] += 1
                    if row["symbol"] not in picked:
                        picked[row["symbol"]] = row
                        progressed = True
                        break
                if len(picked) >= max_n:
                    break
            if not progressed:
                break
    if len(picked) < max_n:
        for row in _take_bucket(concept_only, 80):
            if row["symbol"] not in picked:
                picked[row["symbol"]] = row
            if len(picked) >= max_n:
                break

    # 强制纳入：每个主线行业内，科技概念票 stride 保送；大类行业多拿
    tech_keep: dict[str, dict] = {}
    for name in allow_names:
        cand = [r for r in (by_allow.get(name) or []) if r.get("tech_concept")]
        n_take = min(len(cand), max(50, max_n // max(len(allow_names), 1)))
        if name in ("电子", "半导体", "电力设备"):
            n_take = min(len(cand), max(n_take, max_n // 3))
        for row in _take_bucket(cand, n_take):
            tech_keep[row["symbol"]] = row
            picked[row["symbol"]] = row
    if len(picked) > max_n:
        if len(tech_keep) >= max_n:
            # 按代码均匀保留科技保送，不按分裁切
            by_code = sorted(tech_keep.values(), key=lambda x: x["symbol"])
            step = max(1, len(by_code) // max_n)
            kept = [by_code[i] for i in range(0, len(by_code), step)][:max_n]
            if len(kept) < max_n:
                for row in by_code:
                    if row["symbol"] not in {x["symbol"] for x in kept}:
                        kept.append(row)
                    if len(kept) >= max_n:
                        break
            picked = {r["symbol"]: r for r in kept}
        else:
            rest = [picked[s] for s in list(picked) if s not in tech_keep]
            rest.sort(key=lambda x: (-float(x["score"]), x["symbol"]))
            need = max_n - len(tech_keep)
            picked = dict(tech_keep)
            for row in rest[:need]:
                picked[row["symbol"]] = row

    items = []
    for row in sorted(picked.values(), key=lambda x: (-float(x["score"]), x["symbol"])):
        items.append(
            {
                "symbol": row["symbol"],
                "name": row["name"],
                "industry": row["industry"],
                "reason": "hot_sector_bypass",
                "selection_arm": "hot_sector_bypass",
            }
        )

    symbols = [x["symbol"] for x in items]
    out = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "enabled": True,
        "top_k": top_k,
        "max_n": max_n,
        "industries": industries,
        "concept_allow": list(c_weights.keys())[:12],
        "symbols": symbols,
        "items": items,
        "n": len(symbols),
        "map_size": len(ind_map),
        "per_industry": per_industry,
        "matched_universe": len(scored),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    POOL_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    log(
        f"  ✅ 主线旁路: {len(symbols)} 只 / 匹配宇宙 {len(scored)} | 行业={allow_names} | "
        f"分行业命中={per_industry}"
    )
    if len(symbols) < 10:
        log("  ⚠️ 主线旁路池过瘦（行业映射可能不全），不阻断启动形态 A 臂")
    return out


def load_bypass_symbols() -> set[str]:
    """读取旁路池代码（6 位 bare）。文件缺失或关闭时返回空集。"""
    if not POOL_PATH.exists():
        return set()
    try:
        raw = json.loads(POOL_PATH.read_text(encoding="utf-8"))
    except Exception:
        return set()
    if not isinstance(raw, dict) or not raw.get("enabled", True):
        return set()
    syms = raw.get("symbols") or []
    return {_bare(s) for s in syms if s}


def reject_bypass_distribution(items: list) -> tuple[list, int]:
    """旁路票若资金阶段为出货则硬拒。返回 (kept, dropped_n)。"""
    kept = []
    dropped = 0
    for it in items:
        arm = str(it.get("selection_arm") or "")
        bypass = bool(it.get("launch_bypass")) or arm == "hot_sector_bypass"
        if bypass:
            phase = str(it.get("money_phase") or "").lower()
            label = str(it.get("money_phase_label") or "")
            if phase == "distribution" or "出货" in label:
                dropped += 1
                continue
        kept.append(it)
    return kept, dropped


if __name__ == "__main__":
    build_hot_sector_bypass_pool()
