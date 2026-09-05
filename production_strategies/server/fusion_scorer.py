#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
三路模型加权融合评分器
======================
将 VM2.5 评分、资金流评分、板块热度评分融合为一个最终评分，
按近期 IC（信息系数）动态调整三路权重。

用法：
    from fusion_scorer import fusion_rerank
    top = fusion_rerank(top)        # 注入 _fusion_weight 并按此降序排序

    from fusion_scorer import update_ic_weights
    update_ic_weights(trade_history)  # 16:15 反馈闭环更新权重
"""
from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("ALPHAPILOT_ROOT") or "/home/ubuntu/alphapilot")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent

WEIGHTS_PATH = ROOT / "output" / "feedback" / "model_weights.json"

# ── 默认权重（冷启动） ──
DEFAULT_WEIGHTS = {
    "vm25": 0.50,
    "fund_flow": 0.30,
    "sector_heat": 0.20,
}
WEIGHT_EMA_ALPHA = 0.10  # 新 IC 贡献 10%，旧权重保留 90%
IC_WINDOW = 20           # 滚动 IC 窗口

# ── 资金流归一化参数 ──
FUND_TANH_SCALE = 10_000_000  # 1 亿 → tanh(1) = 0.76

# ── 板块温度归一化参数 ──
SECTOR_CLAMP_LOW = -0.05
SECTOR_CLAMP_HIGH = 0.05


# ====================================================================
#  权重持久化
# ====================================================================

def _load_weights() -> dict[str, float]:
    """加载当前权重。若文件不存在或损坏，返回默认权重。"""
    if WEIGHTS_PATH.exists():
        try:
            d = json.loads(WEIGHTS_PATH.read_text(encoding="utf-8"))
            w = d.get("weights", {})
            # 保证三大键都存在
            return {
                "vm25": float(w.get("vm25", DEFAULT_WEIGHTS["vm25"])),
                "fund_flow": float(w.get("fund_flow", DEFAULT_WEIGHTS["fund_flow"])),
                "sector_heat": float(w.get("sector_heat", DEFAULT_WEIGHTS["sector_heat"])),
            }
        except Exception:
            pass
    return dict(DEFAULT_WEIGHTS)


def _save_weights(
    weights: dict[str, float],
    ics: dict[str, float] | None = None,
    n_samples: int = 0,
) -> None:
    """持久化权重 + IC 记录。"""
    WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "weights": {k: round(v, 4) for k, v in weights.items()},
        "rolling_ic": {k: round(v, 4) for k, v in (ics or {}).items()},
        "n_samples": n_samples,
        "mode": "ema_active" if n_samples >= IC_WINDOW else "ema_warm",
        "defaults": DEFAULT_WEIGHTS,
    }
    WEIGHTS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


# ====================================================================
#  三路信号归一化
# ====================================================================

def _vm25_score(item: dict) -> float:
    """VM2.5 模型评分（已归一化 0~1）。"""
    score = item.get("score") or item.get("ml_score") or 0.5
    try:
        return max(0.0, min(1.0, float(score)))
    except (TypeError, ValueError):
        return 0.5


def _fund_flow_score(item: dict) -> float:
    """主力净流入归一化评分（tanh 映射到 0~1）。
    
    计算：score = (tanh(main_net / 10_000_000) + 1) / 2
      +1 亿 → 0.88    +1000 万 → 0.55    0 → 0.50
      -1000 万 → 0.45  -1 亿 → 0.24
    """
    raw = item.get("live_main_net") or item.get("main_net") or 0
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return 0.5
    if val == 0:
        return 0.5  # 中性
    norm = math.tanh(val / FUND_TANH_SCALE)
    return max(0.0, min(1.0, (norm + 1.0) / 2.0))


def _sector_heat_score(item: dict) -> float:
    """板块热度归一化评分。
    
    输入：sector_change_pct（板块日涨幅，如 0.03 = +3%）
    计算：clamp(-5% ~ +5%) → 线性映射 0~1
      +5% → 1.0   0% → 0.5   -5% → 0.0
    """
    raw = item.get("sector_change_pct") or item.get("sector_pct") or 0
    try:
        pct = float(raw)
    except (TypeError, ValueError):
        return 0.5
    clamped = max(SECTOR_CLAMP_LOW, min(SECTOR_CLAMP_HIGH, pct))
    return max(0.0, min(1.0, (clamped - SECTOR_CLAMP_LOW) / (SECTOR_CLAMP_HIGH - SECTOR_CLAMP_LOW)))


# ====================================================================
#  融合排序（主入口）
# ====================================================================

def fusion_rerank(top: list[dict]) -> list[dict]:
    """三路融合评分 + 按融合分降序重排 top 列表。

    注入字段：
      _fusion_scores: dict {vm25, fund_flow, sector_heat}
      _fusion_weight: float  最终融合评分

    不影响已有字段（score, entry_weight 等保持不变）。
    无数据时不报错，回退到原始顺序。
    """
    if not top:
        return top

    weights = _load_weights()
    w_vm25 = weights["vm25"]
    w_fund = weights["fund_flow"]
    w_sector = weights["sector_heat"]

    for item in top:
        vm25 = _vm25_score(item)
        fund = _fund_flow_score(item)
        sector = _sector_heat_score(item)
        item["_fusion_scores"] = {
            "vm25": round(vm25, 4),
            "fund_flow": round(fund, 4),
            "sector_heat": round(sector, 4),
        }
        item["_fusion_weight"] = round(
            w_vm25 * vm25 + w_fund * fund + w_sector * sector,
            4,
        )

    return sorted(top, key=lambda x: float(x.get("_fusion_weight", 0)), reverse=True)


# ====================================================================
#  IC 计算 + EMA 权重更新（反馈闭环）
# ====================================================================

def _spearman_rank(x: list[float], y: list[float]) -> float:
    """计算 Spearman 秩相关系数。n < 3 时返回 0。"""
    n = len(x)
    if n < 3 or n != len(y):
        return 0.0
    # 排名
    rx = [sorted(x).index(v) + 1 for v in x]
    ry = [sorted(y).index(v) + 1 for v in y]
    # Pearson on ranks = Spearman
    mean_rx = sum(rx) / n
    mean_ry = sum(ry) / n
    num = sum((rx[i] - mean_rx) * (ry[i] - mean_ry) for i in range(n))
    den = math.sqrt(sum((rx[i] - mean_rx) ** 2 for i in range(n))) * math.sqrt(
        sum((ry[i] - mean_ry) ** 2 for i in range(n))
    )
    if den == 0:
        return 0.0
    return num / den


def update_ic_weights(trades: list[dict]) -> dict[str, Any]:
    """根据最近 trade_log 计算三路信号与 pnl 的 IC，更新 EMA 权重。

    输入：
      trades: kelly_learner_trades 格式，每笔需含：
        - _fusion_scores (dict): {vm25, fund_flow, sector_heat}
        - pnl: 平仓盈亏（正=赢，负=亏）

    输出：
      {
        "ok": bool,
        "weights": {...},         # 更新后的权重
        "rolling_ic": {...},      # 各信号 IC
        "n_used": int,            # 用于计算的交易笔数
      }

    流程：
      1. 取最近 IC_WINDOW 笔含 fusion_scores 的交易
      2. 对每个信号计算信号分与 pnl 的 Spearman 秩相关系数 (IC)
      3. EMA 更新权重：w_new = w_old + alpha * (IC - 0.5*w_old)
      4. 持久化到 output/feedback/model_weights.json
    """
    result: dict[str, Any] = {"ok": False, "n_used": 0}

    # 筛选含 fusion 评分的交易
    # 2026-08-29: 排除 backfill=True 的回填样本——学习引擎只能用真实平仓盈亏更新权重，
    # 回填样本（手工/历史导入的带分平仓）不是实盘盈亏，混入会污染 IC 与 EMA 权重。
    scored = []
    for t in trades:
        if t.get("backfill"):
            continue
        fs = t.get("_fusion_scores")
        if not isinstance(fs, dict) or fs.get("vm25") is None:
            continue
        try:
            if abs(float(t.get("pnl") or 0)) <= 1e-6:
                continue
        except (TypeError, ValueError):
            continue
        scored.append(t)
    recent = scored[-IC_WINDOW:] if len(scored) > IC_WINDOW else scored
    n = len(recent)
    result["n_used"] = n

    if n < 5:
        # 样本不足，不更新权重
        result["weights"] = _load_weights()
        result["rolling_ic"] = {}
        result["note"] = f"insufficient_samples ({n}<5)"
        _save_weights(result["weights"], {}, n)
        return result

    # 提取信号向量和 pnl 向量
    signal_dim = ["vm25", "fund_flow", "sector_heat"]
    vectors: dict[str, list[float]] = {d: [] for d in signal_dim}
    pnls: list[float] = [float(t.get("pnl", 0)) for t in recent]

    for t in recent:
        scores = t["_fusion_scores"]
        for d in signal_dim:
            vectors[d].append(float(scores.get(d, 0.5)))

    # 计算各信号 IC
    ics: dict[str, float] = {}
    for d in signal_dim:
        ics[d] = round(_spearman_rank(vectors[d], pnls), 4)

    # EMA 更新权重
    old_w = _load_weights()
    new_w: dict[str, float] = {}
    for d in signal_dim:
        ic = ics[d]
        # IC 范围为 -1~1，移位到 0~1 作为更新信号
        ic_signal = (ic + 1.0) / 2.0  # 0~1
        # EMA: w_new = (1-alpha) * w_old + alpha * ic_signal
        ema = (1.0 - WEIGHT_EMA_ALPHA) * old_w[d] + WEIGHT_EMA_ALPHA * ic_signal
        new_w[d] = max(0.05, min(0.85, ema))  # 约束在 [0.05, 0.85]

    # 归一化使权重之和 = 1
    total = sum(new_w.values())
    if total > 0:
        for d in signal_dim:
            new_w[d] /= total

    _save_weights(new_w, ics, n)
    result["ok"] = True
    result["weights"] = new_w
    result["rolling_ic"] = ics
    result["note"] = f"ema_updated ({n} samples)"
    return result
