#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一板块资金门控 — 合并「快门控」(趋势) + 「延爆门控」(资金轮动)。

输入:
  - 行业/概念 1日+3日资金流（sector_rotation_gate.build_snapshot）
  - 板块 5/10 日动量趋势（原 sector_gate.compute_sector_score）
  - 美股板块映射加分（原 sector_gate）

联合决策:
  趋势强 + allow   → strong_allow (+0.03)
  趋势强 + neutral → soft_allow   (0)
  趋势弱 + allow   → cautious     (-0.02)
  趋势弱 + deny    → hard_deny    (剔除；soft 模式则 -0.08)
  趋势弱 + neutral → soft_deny    (-0.08)
  趋势强 + deny   → 看概念层是否救；概念 allow 则 cautious，否则 soft_deny

生产默认 mode=soft_dual：deny 只降分不删（与现网一致）。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
SNAP_LAST = OUT / "sector_flow_gate_last.json"

# 复用轮动快照与行业/概念映射
from sector_rotation_gate import (
    apply_sector_rotation_gate,
    build_snapshot,
    industry_aliases,
    load_stock_concept_map,
    load_stock_industry_map,
    resolve_industry,
    _bare,
    _status_from_names,
)


def _trend_bucket(trend_score: float) -> str:
    """趋势分 → strong / weak / neutral。"""
    if trend_score >= 0.6:
        return "strong"
    if trend_score <= -0.6:
        return "weak"
    return "neutral"


def _compute_trend_for_industry(industry: str, sector_fund: dict | None = None) -> dict:
    """尽量用 sector_gate 的趋势分；失败则中性。"""
    if not industry:
        return {"trend_score": 0.0, "bucket": "neutral", "detail": {}}
    try:
        from sector_gate import compute_sector_score

        res = compute_sector_score(industry, sector_fund)
        score = float(res.get("trend_score") or 0)
        return {
            "trend_score": score,
            "bucket": _trend_bucket(score),
            "detail": res.get("detail") or {},
            "adjust_factor": res.get("adjust_factor"),
        }
    except Exception as e:
        return {"trend_score": 0.0, "bucket": "neutral", "detail": {}, "error": str(e)}


def _us_sector_bonus(item: dict) -> float:
    """美股板块映射加分（原 sector_gate 逻辑精简版）。"""
    try:
        us_path = ROOT / "output" / "us_enhanced_factors.json"
        if not us_path.exists():
            return 0.0
        us_data = json.loads(us_path.read_text(encoding="utf-8"))
    except Exception:
        return 0.0

    sector = str(item.get("sector") or item.get("industry") or "")
    name = str(item.get("name") or "")
    impacts = us_data.get("sector_impacts") or {}
    bonus = 0.0
    for sec_key, impact in impacts.items():
        if str(sec_key).startswith("_"):
            continue
        if sec_key in sector or sector in sec_key:
            try:
                bonus = float(impact) * 0.05
            except (TypeError, ValueError):
                bonus = 0.0
            break
    if not bonus:
        try:
            bonus = float(impacts.get("__overall__", 0) or 0) * 0.03
        except (TypeError, ValueError):
            bonus = 0.0

    overnight = us_data.get("overnight_stocks") or {}
    apple_chg = 0.0
    for k, v in overnight.items():
        if "苹果" in str(k):
            try:
                apple_chg = float(v)
            except (TypeError, ValueError):
                apple_chg = 0.0
            break
    ai_boost = max(0.0, apple_chg * 0.008)
    ai_kw = ("AI", "智能", "人工", "大模型", "机器视觉", "语音识别", "算法", "软件")
    if ai_boost and (any(k in name for k in ai_kw) or any(k in sector for k in ai_kw)):
        bonus += ai_boost
    return max(-0.1, min(0.1, round(bonus, 4)))


def _joint_decide(
    trend_bucket: str,
    ind_status: str,
    concept_status: str,
) -> tuple[str, float, str]:
    """返回 (action, score_delta, reason)。

    action: allow | demote | deny
    """
    # 行业骨架优先
    if ind_status == "deny":
        if trend_bucket == "strong" and concept_status == "allow":
            return "demote", -0.02, "行业流出但趋势强+概念流入→谨慎保留"
        if trend_bucket == "strong":
            return "demote", -0.06, "行业流出+趋势强→软降权"
        return "deny", -0.08, "行业流出拒绝"

    if ind_status == "allow":
        if trend_bucket == "strong":
            return "allow", 0.03, "行业流入+趋势强"
        if trend_bucket == "weak":
            return "demote", -0.02, "行业流入但趋势弱→谨慎"
        return "allow", 0.01, "行业流入"

    # industry neutral → 看概念
    if concept_status == "deny":
        if trend_bucket == "strong":
            return "demote", -0.05, "概念流出+趋势强→软降权"
        return "deny", -0.08, "概念流出拒绝"

    if concept_status == "allow":
        if trend_bucket == "weak":
            return "demote", -0.02, "概念流入但趋势弱→谨慎"
        if trend_bucket == "strong":
            return "allow", 0.025, "概念流入+趋势强(轮动锋面)"
        return "allow", 0.01, "概念流入(轮动锋面)"

    # 双中性
    if trend_bucket == "strong":
        return "demote", -0.01, "双中性但趋势强→轻降权观察"
    if trend_bucket == "weak":
        return "deny", -0.08, "双中性+趋势弱"
    return "deny", -0.04, "行业与概念均无资金锋面"


def apply_sector_flow_gate(
    items: list[dict[str, Any]],
    snap: dict | None = None,
    mode: str | None = None,
) -> list[dict[str, Any]]:
    """统一板块门控入口。

    mode:
      soft_dual — 生产默认：deny 降分不删
      dual      — deny 硬删
      legacy_rotation — 完全转发旧 sector_rotation_gate
    """
    mode = (mode or os.environ.get("SECTOR_FLOW_GATE_MODE", "soft_dual")).strip().lower()
    if not items:
        return items

    if mode == "legacy_rotation":
        return apply_sector_rotation_gate(items, snap=snap, mode="soft_dual")

    if snap is None:
        snap = build_snapshot()

    classes = (snap or {}).get("classes") or {}
    allow_rows = classes.get("allow") or []
    deny_rows = classes.get("deny") or []
    allow_names = {x["name"] for x in allow_rows}
    deny_names = {x["name"] for x in deny_rows}

    c_classes = (snap or {}).get("concept_classes") or {}
    c_allow_rows = c_classes.get("allow") or []
    c_deny_rows = c_classes.get("deny") or []
    c_allow_names = {x["name"] for x in c_allow_rows}
    c_deny_names = {x["name"] for x in c_deny_rows}

    ind_map = load_stock_industry_map()
    concept_map = load_stock_concept_map()
    soft = mode in ("soft_dual", "soft")

    kept: list[dict] = []
    dropped: list[tuple] = []
    demoted = 0
    boosted = 0

    for it in items:
        code = _bare(it.get("symbol") or it.get("code") or "")
        meta = ind_map.get(code) or {}
        industry = resolve_industry(it, ind_map)
        aliases = industry_aliases(meta) if meta else ([industry] if industry else [])
        concepts = concept_map.get(code) or []

        ind_status, ind_reason, ind_hits = _status_from_names(
            aliases or [industry], allow_names, deny_names, allow_rows, deny_rows
        )
        concept_status, concept_reason, concept_hits = "neutral", "", []
        if concepts and (c_allow_rows or c_deny_rows):
            concept_status, concept_reason, concept_hits = _status_from_names(
                concepts,
                c_allow_names,
                c_deny_names,
                c_allow_rows,
                c_deny_rows,
                fuzzy=False,
            )

        trend = _compute_trend_for_industry(industry)
        action, delta, reason = _joint_decide(
            trend.get("bucket") or "neutral", ind_status, concept_status
        )
        if ind_status == "deny" and ind_reason:
            reason = f"{reason}|{ind_reason}"
        elif concept_status == "deny" and concept_reason:
            reason = f"{reason}|{concept_reason}"

        us_bonus = _us_sector_bonus(it)
        total_delta = float(delta) + float(us_bonus)

        if action == "deny" and not soft:
            dropped.append((code, industry, reason))
            continue

        row = dict(it)
        base = float(row.get("score", 0) or 0)
        row["sector_name_resolved"] = industry
        row["industry_status"] = ind_status
        row["concept_status"] = concept_status
        row["sector_trend_score"] = trend.get("trend_score")
        row["sector_trend_bucket"] = trend.get("bucket")
        row["hit_industry"] = ind_hits[:5]
        row["hit_concepts"] = concept_hits[:5]
        row["concepts"] = concepts[:12]
        row["us_sector_bonus"] = us_bonus
        row["sector_flow_action"] = action
        row["sector_flow_reason"] = reason

        if action == "deny" and soft:
            total_delta = min(total_delta, -0.08)
            row["sector_gate"] = "soft_demote"
            demoted += 1
        elif abs(total_delta) > 1e-12:
            row["sector_gate"] = "adjust"
            if total_delta > 0:
                boosted += 1
            else:
                demoted += 1
        else:
            row["sector_gate"] = "pass"

        row["score_raw_pre_sector"] = round(base, 4)
        row["sector_gate_delta"] = round(total_delta, 4)
        row["score"] = round(max(0.01, base + total_delta), 4)
        row["sector_rotation"] = (
            "allow" if action == "allow" else ("deny" if action == "deny" else "neutral")
        )
        kept.append(row)

    kept.sort(key=lambda x: -float(x.get("score", 0) or 0))
    print(
        f"  sector_flow_gate[{mode}]: keep={len(kept)} drop={len(dropped)} "
        f"demote/adjust={demoted} boost={boosted} "
        f"ind_allow={len(allow_names)} ind_deny={len(deny_names)} "
        f"c_allow={len(c_allow_names)} c_deny={len(c_deny_names)}",
        flush=True,
    )

    OUT.mkdir(parents=True, exist_ok=True)
    SNAP_LAST.write_text(
        json.dumps(
            {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "mode": mode,
                "kept": len(kept),
                "dropped": len(dropped),
                "demoted": demoted,
                "boosted": boosted,
                "drop_samples": [
                    {"code": c, "industry": i, "reason": r} for c, i, r in dropped[:30]
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return kept


# 管线兼容别名
def apply_sector_rotation(items: list) -> list:
    return apply_sector_flow_gate(items)


if __name__ == "__main__":
    snap = build_snapshot()
    demo = [
        {"symbol": "300750", "score": 0.99, "name": "宁德时代", "sector": "电池"},
        {"symbol": "601988", "score": 0.55, "name": "中国银行", "sector": "银行"},
        {"symbol": "688981", "score": 0.95, "name": "中芯国际", "sector": "半导体"},
    ]
    out = apply_sector_flow_gate(demo, snap=snap, mode="soft_dual")
    for x in out:
        print(
            x["symbol"],
            x["score"],
            x.get("sector_flow_action"),
            x.get("sector_trend_bucket"),
            x.get("sector_flow_reason"),
        )
