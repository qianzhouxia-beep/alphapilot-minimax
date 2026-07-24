#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""宇宙入口门控：启动|旁路 vs 扫漏臂 B 软回流。

P1（2026-07-23 核准）:
  ENABLE_SURGE_ARM_B=1     默认开 — 非启动且非旁路 → arm=B，分数×SURGE_ARM_B_MULT
  SURGE_ARM_B_MULT=0.85    B 臂降权
  回滚: ENABLE_SURGE_ARM_B=0 且 ENABLE_SOFT_UNIVERSE=0 → 硬删

兼容旧实验:
  ENABLE_SOFT_UNIVERSE=1 + SURGE 关 → 旧 soft_universe 标签（mult=SOFT_UNIVERSE_MULT）
"""
from __future__ import annotations

import os
from typing import Any, Callable


def _env_on(name: str, default: bool = True) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def surge_arm_b_enabled() -> bool:
    """P1 正式开关：默认开。"""
    return _env_on("ENABLE_SURGE_ARM_B", True)


def soft_universe_enabled() -> bool:
    """旧实验开关；SURGE 开时由 SURGE 路径主导。"""
    return _env_on("ENABLE_SOFT_UNIVERSE", True)


def soft_mode_enabled() -> bool:
    return surge_arm_b_enabled() or soft_universe_enabled()


def surge_arm_b_mult() -> float:
    try:
        return float(os.environ.get("SURGE_ARM_B_MULT", "0.85") or 0.85)
    except (TypeError, ValueError):
        return 0.85


def soft_universe_mult() -> float:
    try:
        return float(os.environ.get("SOFT_UNIVERSE_MULT", "1.0") or 1.0)
    except (TypeError, ValueError):
        return 1.0


def _bare(sym: str) -> str:
    s = str(sym or "").lower().replace("sh", "").replace("sz", "").replace("bj", "")
    return s[-6:] if len(s) >= 6 else s


def apply_universe_gate(
    items: list[dict],
    *,
    gc_bare: set[str],
    gc_set: set,
    bypass_bare: set[str],
    launch_patterns: dict | None = None,
    log: Callable[..., Any] = print,
) -> tuple[list[dict], dict]:
    """对 recommend 缓存池做宇宙门控。

    Returns:
      (items, meta)
    """
    launch_patterns = launch_patterns or {}
    before = len(items)
    surge = surge_arm_b_enabled()
    soft_legacy = soft_universe_enabled() and not surge
    soft = surge or soft_universe_enabled()
    if surge:
        mult = surge_arm_b_mult()
        soft_label = "B"
    else:
        mult = soft_universe_mult()
        soft_label = "soft_universe"

    filtered: list[dict] = []
    n_soft = 0
    n_launch = 0
    n_bypass = 0
    dropped_top: list[dict] = []

    ranked_src = sorted(
        items,
        key=lambda x: -float(x.get("score") or 0),
    )

    for it in items:
        sym = str(it.get("symbol", "") or "")
        bare = _bare(sym)
        in_launch = bare in gc_bare or sym in gc_set
        in_bypass = bare in bypass_bare
        in_universe = in_launch or in_bypass

        if not soft and not in_universe:
            continue

        pats = launch_patterns.get(bare) or launch_patterns.get(sym) or []
        nr = dict(it)
        nr["launch_patterns"] = pats
        raw = float(nr.get("score") or 0)

        if in_bypass and not in_launch:
            nr["launch_bypass"] = True
            nr["selection_arm"] = "A_hot_sector_bypass"
            nr["arm"] = "A"
            nr["universe_soft"] = False
            n_bypass += 1
        elif in_launch:
            nr["launch_bypass"] = False
            nr["selection_arm"] = nr.get("selection_arm") or "A_launch"
            nr["arm"] = "A"
            nr["universe_soft"] = False
            n_launch += 1
        else:
            # 扫漏臂 B / 旧 soft_universe 回流
            nr["launch_bypass"] = False
            nr["selection_arm"] = soft_label if soft_label == "soft_universe" else "B"
            nr["arm"] = "B" if surge else "soft"
            nr["universe_soft"] = True
            nr["score_before_universe"] = raw
            nr["score"] = round(raw * mult, 6)
            nr["surge_arm_b_mult"] = mult if surge else None
            n_soft += 1

        filtered.append(nr)

    if soft:
        filtered.sort(key=lambda x: -float(x.get("score") or 0))
        for it in ranked_src[:100]:
            bare = _bare(it.get("symbol"))
            sym = str(it.get("symbol") or "")
            if bare in gc_bare or sym in gc_set or bare in bypass_bare:
                continue
            dropped_top.append(
                {
                    "symbol": sym,
                    "name": it.get("name"),
                    "score": it.get("score"),
                }
            )
            if len(dropped_top) >= 10:
                break
        mode = "SURGE_ARM_B" if surge else "SOFT_UNIVERSE"
        log(
            f"  {mode} 入口: {before} → {len(filtered)} 只 "
            f"(armA_launch={n_launch} armA_bypass={n_bypass} armB={n_soft} mult={mult})"
        )
        if dropped_top:
            preview = ", ".join(
                f"{x.get('symbol')}:{x.get('name') or ''}@{float(x.get('score') or 0):.3f}"
                for x in dropped_top[:5]
            )
            log(f"  [AUDIT] 若硬删会丢掉的高分样例: {preview}")
    else:
        log(
            f"  启动形态|旁路硬过滤: {before} → {len(filtered)} 只 "
            f"(launch={n_launch} bypass={n_bypass})"
        )
        if not filtered:
            log("⛔ 启动/旁路过滤后无候选股 — 不回退全量推荐（硬宇宙）")

    meta = {
        "surge_arm_b": surge,
        "soft_universe": soft and not surge,
        "soft_legacy": soft_legacy,
        "soft_mult": mult,
        "before": before,
        "after": len(filtered),
        "n_launch": n_launch,
        "n_bypass": n_bypass,
        "n_soft": n_soft,
        "n_arm_b": n_soft if surge else 0,
        "audit_would_drop_top": dropped_top,
    }
    return filtered, meta
