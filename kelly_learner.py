#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Online Incremental Learner for Kelly Position Sizing
=====================================================
每次平仓 → 记录结果 → 在线更新模型 → 次日预测胜率+盈亏比。

架构：
  1. OnlineLogisticRegression — 纯 numpy，partial_fit 在线学习
  2. KellyLearner — trade 管理 / 训练 / 预测 / 持久化
  3. record_trade() — trade_executor 平仓时调用

特征 (8 维)：
  - score_pct (0~1)：当日候选池内百分位
  - vol_norm (0~1)：年化波动率归一化
  - expo (0~3)：市场环境编码（0=normal 1=weak 2=severe 3=crash_day）
  - gap_pct_norm (0~1)：集合竞价缺口归一化（0=gap≤0%, 1=gap≥10%）
  - money_phase (0~1)：资金阶段编码（bear_trap=0.1 / accumulation=0.3 /
    rightside_ambush=0.6 / markup=0.7 / distribution=0.05 / sideways=0.4）
  - channel_reject (0/1)：是否为下跌通道
  - sector_heat (0~1)：板块热度
  - main_net_norm (0~1)：主力净流入归一化（-1亿→0, 0→0.5, +1亿→1）

持久化路径：
  data/kelly_learner_trades.json — trade 原始记录
  data/kelly_learner_model.json — 模型权重 + 分桶统计

用法：
  # trade_executor.py 中平仓时调用
  from kelly_learner import record_trade
  record_trade(pt, pos, sell_row)

  # paper_trading_signals.py 中训练 + 取 hist_stats
  from kelly_learner import KellyLearner
  learner = KellyLearner()
  learner.train()
  hist_stats = learner.get_hist_stats()
  apply_kelly(top, equity, kline_df, hist_stats)
"""
from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

# ── 路径 ────────────────────────────────────────────────
ROOT = Path(os.environ.get("ALPHAPILOT_ROOT") or "/home/ubuntu/alphapilot")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent

TRADES_PATH = ROOT / "data" / "kelly_learner_trades.json"
MODEL_PATH = ROOT / "data" / "kelly_learner_model.json"

MAX_TRADES = 2000  # 滚动窗口上限
MIN_TRADES_TO_TRAIN = 30  # 最少样本数才开始 ML 预测
N_FEATURES = 8  # score_pct, vol_norm, expo, gap_pct_norm, money_phase, channel_reject, sector_heat, main_net_norm


# ── 资金阶段编码 ─────────────────────────────────────
_MONEY_PHASE_MAP: dict[str, float] = {
    "bear_trap": 0.10,       # 诱空陷阱
    "accumulation": 0.30,    # 吸筹
    "accumulation_end": 0.35, # 吸筹末期
    "sideways": 0.40,        # 震荡
    "rightside_ambush": 0.60, # 右侧潜伏
    "markup": 0.70,          # 拉升
    "pullback": 0.20,        # 回调
    "distribution": 0.05,    # 出货
    "suspicious": 0.15,      # 诱多嫌疑
    "markup_strong": 0.85,   # 强拉升
}


def _encode_money_phase(phase: str) -> float:
    """资金阶段字符串 → 0~1 数值编码。"""
    return _MONEY_PHASE_MAP.get(str(phase).strip().lower(), 0.40)


def _main_net_norm(main_net: float) -> float:
    """主力净流入归一化：±1亿映射到 0~1。"""
    clipped = max(-100_000_000, min(100_000_000, float(main_net)))
    return (clipped + 100_000_000) / 200_000_000


def _gap_pct_norm(gap_pct: float) -> float:
    """缺口归一化：0%~10% → 0~1。"""
    g = max(0.0, min(0.10, float(gap_pct)))
    return g / 0.10


# ═══════════════════════════════════════════════════════════
# 1. 纯 NumPy 在线逻辑回归
# ═══════════════════════════════════════════════════════════


class OnlineLogisticRegression:
    """Logistic regression with online SGD — numpy only, no sklearn dependency.

    支持 partial_fit：每来一条/一批样本即可增量更新。
    权重可序列化为 JSON，跨进程/跨日持久化。
    """

    def __init__(self, n_features: int = N_FEATURES, lr: float = 0.01, l2: float = 0.001):
        self.w = np.zeros(n_features, dtype=np.float64)
        self.b = 0.0
        self.lr = lr
        self.l2 = l2
        self.steps = 0
        self.n_features = n_features

    def partial_fit(self, X: np.ndarray, y: np.ndarray) -> None:
        """在线增量训练。

        Args:
            X: shape (n, n_features), float64
            y: shape (n,), int64, values 0/1
        """
        for i in range(len(X)):
            self.steps += 1
            # 学习率衰减
            lr = self.lr / (1.0 + 0.002 * self.steps)
            x = X[i]
            y_true = float(y[i])
            logit = float(np.dot(self.w, x)) + self.b
            logit = np.clip(logit, -20, 20)
            prob = 1.0 / (1.0 + np.exp(-logit))
            error = prob - y_true
            self.w -= lr * (error * x + self.l2 * self.w)
            self.b -= lr * error

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """返回正类概率，shape (n,)."""
        logit = np.dot(X, self.w.astype(X.dtype)) + self.b
        logit = np.clip(logit, -20, 20)
        return 1.0 / (1.0 + np.exp(-logit))

    def get_params(self) -> dict:
        return {
            "w": self.w.tolist(),
            "b": round(self.b, 6),
            "steps": self.steps,
            "lr": self.lr,
            "l2": self.l2,
        }

    def set_params(self, params: dict) -> None:
        w = params.get("w", [0.0] * self.n_features)
        if len(w) != self.n_features:
            return  # 维度不匹配不恢复，让 train() 重置
        self.w = np.array(w, dtype=np.float64)
        self.b = float(params.get("b", 0.0))
        self.steps = int(params.get("steps", 0))
        self.lr = float(params.get("lr", self.lr))
        self.l2 = float(params.get("l2", self.l2))


# ═══════════════════════════════════════════════════════════
# 2. KellyLearner — 管理 trade 集 + 训练 + 预测
# ═══════════════════════════════════════════════════════════


class KellyLearner:
    """在线增量学习器：管理 closed trades、训练 LR 模型、输出 hist_stats。

    每次平仓 -> record_trade() -> 追加到 self.trades & 持久化。
    每次运行信号 -> train() -> 更新 LR + payoff 分桶 -> get_hist_stats()。
    """

    def __init__(self):
        self.trades: list[dict] = []
        self.model = OnlineLogisticRegression(n_features=N_FEATURES)
        self._loaded = False
        self._load()

    # ── 持久化 ────────────────────────────────────────────

    def _load(self) -> None:
        """从 JSON 恢复 trades 和模型权重。"""
        if TRADES_PATH.exists():
            try:
                data = json.loads(TRADES_PATH.read_text(encoding="utf-8"))
                self.trades = data.get("trades", [])
            except Exception:
                self.trades = []
        if MODEL_PATH.exists():
            try:
                state = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
                self.model.set_params(state.get("model", {}))
            except Exception:
                pass
        self._loaded = True

    def save(self) -> None:
        """持久化 trades + 模型权重。"""
        TRADES_PATH.parent.mkdir(parents=True, exist_ok=True)
        TRADES_PATH.write_text(
            json.dumps({"trades": self.trades[-MAX_TRADES:]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        MODEL_PATH.write_text(
            json.dumps(
                {
                    "model": self.model.get_params(),
                    "n_trades": len(self.trades),
                    "updated_at": time.strftime("%Y-%m-%d %H:%M"),
                    "n_features": N_FEATURES,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def add_trade(
        self,
        symbol: str,
        entry_score: float,
        entry_score_pct: float,
        entry_vol: float,
        expo: int,
        pnl: float,
        held_days: int,
        sell_action: str,
        buy_date: str = "",
        sell_date: str = "",
        entry_gap_pct: float = 0.0,
        entry_money_phase: float = 0.4,
        entry_channel_reject: int = 0,
        entry_sector_heat: float = 0.5,
        entry_main_net: float = 0.0,
        fusion_scores: dict | None = None,
    ) -> None:
        """追加一条已平仓记录，包含增强特征，立即持久化。"""
        trade = {
            "symbol": symbol,
            "entry_score": round(entry_score, 4),
            "entry_score_pct": round(entry_score_pct, 4),
            "entry_vol": round(entry_vol, 4),
            "expo": expo,
            "pnl": round(pnl, 2),
            "win": int(pnl > 0),
            "held_days": held_days,
            "sell_action": sell_action[:20],
            "buy_date": str(buy_date)[:10],
            "sell_date": str(sell_date)[:10],
            "ts": time.time(),
            # 增强特征
            "entry_gap_pct": entry_gap_pct,
            "entry_money_phase": min(1.0, max(0.0, float(entry_money_phase))),
            "entry_channel_reject": int(entry_channel_reject),
            "entry_sector_heat": min(1.0, max(0.0, float(entry_sector_heat))),
            "entry_main_net": float(entry_main_net),
            # 三路融合评分
            "_fusion_scores": fusion_scores or {},
        }
        self.trades.append(trade)
        # 在线更新 LR —— 只用最近 MAX_TRADES 条
        recent = self.trades[-MAX_TRADES:]
        feats = self._trades_to_X(recent)
        if feats.shape[1] != N_FEATURES:
            return  # 维度异常跳过在线更新，等 train() 重建
        labels = np.array([t["win"] for t in recent], dtype=np.int64)
        self.model.partial_fit(feats, labels)
        self.save()

    # ── 特征工程 ──────────────────────────────────────────

    @staticmethod
    def _trades_to_X(trades: list[dict]) -> np.ndarray:
        """从 trade 记录构建特征矩阵 (n, 8)。

        旧数据缺失增强特征时自动用默认值补齐（兼容 3→8 迁移）。
        """
        rows = []
        for t in trades:
            sp = float(t.get("entry_score_pct") or 0.5)
            sp = max(0.0, min(1.0, sp))
            ev = float(t.get("entry_vol") or 0.3)
            ev_norm = max(0.0, min(1.0, (ev - 0.1) / 0.9)) if ev > 0.1 else 0.0
            ex = int(t.get("expo") or 0)
            ex_norm = min(1.0, ex / 3.0)
            gp = _gap_pct_norm(float(t.get("entry_gap_pct") or 0.0))
            mp = float(t.get("entry_money_phase") or 0.40)
            mp = max(0.0, min(1.0, mp))
            cr = float(int(t.get("entry_channel_reject") or 0))
            sh = float(t.get("entry_sector_heat") or 0.5)
            sh = max(0.0, min(1.0, sh))
            mn = _main_net_norm(float(t.get("entry_main_net") or 0.0))
            rows.append([sp, ev_norm, ex_norm, gp, mp, cr, sh, mn])
        nf = N_FEATURES
        return np.array(rows, dtype=np.float64) if rows else np.empty((0, nf), dtype=np.float64)

    # ── 训练（在已有 trades 上 full-batch 重训 LR）───────

    def train(self) -> None:
        """在全部 trades（滚动窗口）上重置并重训 LR。

        每次信号生成前调用，确保模型始终反映最新数据分布。
        自动检测旧模型维度并重建。
        """
        recent = self.trades[-MAX_TRADES:]
        if len(recent) < MIN_TRADES_TO_TRAIN:
            return
        feats = self._trades_to_X(recent)
        if feats.shape[1] != N_FEATURES:
            return
        labels = np.array([t["win"] for t in recent], dtype=np.int64)
        # 重置并多 epoch 训练
        self.model = OnlineLogisticRegression(n_features=N_FEATURES)
        for _epoch in range(5):
            idx = np.random.permutation(len(feats))
            self.model.partial_fit(feats[idx], labels[idx])

    # ── 预测接口 ──────────────────────────────────────────

    @staticmethod
    def _build_feature_row(
        score_pct: float, vol: float, expo: int = 0,
        gap_pct: float = 0.0, money_phase: float = 0.4,
        channel_reject: int = 0, sector_heat: float = 0.5,
        main_net: float = 0.0,
    ) -> np.ndarray:
        """单候选 → 特征向量 (1, 8)。"""
        sp = max(0.0, min(1.0, float(score_pct)))
        ev = max(0.0, min(1.0, (float(vol) - 0.1) / 0.9)) if vol else 0.3
        ex = min(1.0, int(expo) / 3.0)
        gp = _gap_pct_norm(float(gap_pct))
        mp = max(0.0, min(1.0, float(money_phase)))
        cr = float(int(channel_reject))
        sh = max(0.0, min(1.0, float(sector_heat)))
        mn = _main_net_norm(float(main_net))
        return np.array([[sp, ev, ex, gp, mp, cr, sh, mn]], dtype=np.float64)

    def predict_win_rate(
        self, score_pct: float, vol: float, expo: int = 0,
        gap_pct: float = 0.0, money_phase: float = 0.4,
        channel_reject: int = 0, sector_heat: float = 0.5,
        main_net: float = 0.0,
    ) -> float:
        """ML 预测胜率，返回 0~1。"""
        if not self._loaded or len(self.trades) < MIN_TRADES_TO_TRAIN:
            return 0.5
        X = self._build_feature_row(score_pct, vol, expo, gap_pct, money_phase, channel_reject, sector_heat, main_net)
        if X.shape[1] != self.model.n_features:
            return 0.5
        return float(self.model.predict_proba(X)[0])

    # ── 生成 hist_stats ──────────────────────────────────

    def get_hist_stats(self) -> dict:
        """生成 apply_kelly 兼容的 hist_stats 字典。

        输出格式：
          {
            "map": {score_pct_thr: (win_rate, payoff), ...},
            "overall_win_rate": ...,
            "overall_payoff": ...,
            "ml_ready": bool,
            "n_trades": ...,
          }
        """
        recent = self.trades[-MAX_TRADES:]
        n = len(recent)
        if n < 10:
            return {"map": {}, "overall_win_rate": 0.50, "overall_payoff": 1.8, "ml_ready": False, "n_trades": n}

        # 按 entry_score_pct 排序并分桶（最多 5 桶）
        arr = np.array(
            [[t.get("entry_score_pct", 0.5), t["win"], t.get("pnl", 0)] for t in recent],
            dtype=np.float64,
        )
        arr = arr[arr[:, 0].argsort()]
        n_bins = min(5, n // 5)
        if n_bins < 1:
            n_bins = 1
        bins = [(i, min(i + n // n_bins, n)) for i in range(0, n, max(n // n_bins, 1))]
        if bins[-1][1] < n:
            bins[-1] = (bins[-1][0], n)

        score_map = {}
        for lo, hi in bins:
            segment = arr[lo:hi]
            p = float((segment[:, 1] > 0).mean())
            pos_vals = segment[:, 2][segment[:, 2] > 0]
            neg_vals = segment[:, 2][segment[:, 2] < 0]
            avg_win = float(pos_vals.mean()) if len(pos_vals) > 0 else 0.01
            avg_loss = float(abs(neg_vals.mean())) if len(neg_vals) > 0 else 0.01
            b = avg_win / avg_loss if avg_loss > 0 else 1.8
            pct_thr = min(float(hi) / n, 0.99)
            score_map[round(pct_thr, 2)] = (round(p, 4), round(b, 2))

        overall_win = float(np.mean([t["win"] for t in recent]))
        pos_pnls = [t["pnl"] for t in recent if t["pnl"] > 0]
        neg_pnls = [t["pnl"] for t in recent if t["pnl"] < 0]
        overall_payoff = (
            (np.mean(pos_pnls) / abs(np.mean(neg_pnls)))
            if neg_pnls and pos_pnls
            else 1.8
        )

        return {
            "map": dict(sorted(score_map.items())),
            "overall_win_rate": round(float(overall_win), 4),
            "overall_payoff": round(float(overall_payoff), 2),
            "ml_ready": n >= MIN_TRADES_TO_TRAIN,
            "n_trades": n,
            "source": "kelly_learner_live",
        }


# ═══════════════════════════════════════════════════════════
# 3. 模块级快捷接口 — trade_executor 平仓时直接调用
# ═══════════════════════════════════════════════════════════

_LEARNER: KellyLearner | None = None


def _get_learner() -> KellyLearner:
    global _LEARNER
    if _LEARNER is None:
        _LEARNER = KellyLearner()
    return _LEARNER


def record_trade(
    pt: dict,
    pos: dict,
    sell_row: dict,
) -> None:
    """trade_executor 平仓时调用，自动提取增强特征并持久化。

    Args:
        pt:   paper_trading.json 完整 dict（需含 position_exposure）
        pos:  被平仓的 position dict（含 entry_gap_pct / entry_money_phase 等增强字段）
        sell_row: append_sell 返回的 trade_log row
    """
    try:
        pnl = float(sell_row.get("pnl") or 0)
        if abs(pnl) < 0.01:
            return  # 零盈亏不记录
        learner = _get_learner()
        expo = int(pt.get("position_exposure") or pt.get("account", {}).get("position_exposure") or 0)
        # 提取增强特征（旧数据缺失时默认值）
        gap_pct = float(pos.get("entry_gap_pct") or 0.0)
        money_phase = _encode_money_phase(str(pos.get("entry_money_phase") or ""))
        channel_reject = int(pos.get("entry_channel_reject") or 0)
        sector_heat = float(pos.get("entry_sector_heat") or 0.5)
        main_net = float(pos.get("entry_main_net") or 0.0)
        fusion_scores = pos.get("_fusion_scores") or {}
        learner.add_trade(
            symbol=str(pos.get("symbol", "")),
            entry_score=float(pos.get("entry_score") or 0),
            entry_score_pct=float(pos.get("entry_score_pct") or 0.5),
            entry_vol=float(pos.get("entry_vol") or 0.3),
            expo=expo,
            pnl=pnl,
            held_days=int(sell_row.get("trading_days_held") or 0),
            sell_action=str(sell_row.get("action", "")),
            buy_date=str(pos.get("buy_date") or ""),
            sell_date=str(sell_row.get("time", "")),
            entry_gap_pct=gap_pct,
            entry_money_phase=money_phase,
            entry_channel_reject=channel_reject,
            entry_sector_heat=sector_heat,
            entry_main_net=main_net,
            fusion_scores=fusion_scores,
        )
    except Exception as e:
        print(f"  KellyLearner record_trade skip: {e}")
