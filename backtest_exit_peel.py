#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""动态 peel 止盈 vs T+2 收盘 — 可交易口径对照回测

入场（各臂相同）:
  T 信号收盘 → T+1 开盘买（涨停附近跳过）

选股:
  --rank vm25     正式验收：严格量价金叉 + VM2.5 TopN + 资金硬门控（对齐可交易 A 臂）
  --rank momentum 快速对照：5 日动量代理（非正式）

出场对照:
  A_t2_close         : T+2 收盘全清（现网日频协议）
  B_peel_15          : ≥+3% 仅激活；峰值回撤≥1.5% 剩余减半；须创新高后再触发；
                       第 3 刀清仓；最迟 max_hold 个交易日收盘强平
  C_full_trail1      : ≥+3% 且回撤≥1% 全清（旧全仓动态止盈）
  D_t1_stop10_peel   : 买入后第 1 个可卖日：成本硬止损 -10%；浮盈≥3% 走 peel；
                       当日收盘无论盈亏强平（对照「低开下杀再翻红」）

日 K 近似盘中高低：用当日 high 更新峰值、low 判断止损、close 判断回撤。

用法:
  python3 -u backtest_exit_peel.py --rank vm25 --start 2026-04-01 --end 2026-07-17
  python3 -u backtest_exit_peel.py --suite antidump --rank vm25 --start 2026-04-01 --end 2026-07-20
"""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/ubuntu/alphapilot")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent


def _bare(s: str) -> str:
    x = str(s or "")
    for p in ("sh", "sz", "bj", "SH", "SZ", "BJ"):
        if x.lower().startswith(p.lower()) and len(x) > 6:
            x = x[len(p) :]
            break
    return x[-6:] if len(x) >= 6 else x


def limit_pct(sym: str) -> float:
    s = _bare(sym)
    if s.startswith(("300", "301", "688")):
        return 0.20
    return 0.10


def fund_gate_ok(fund_hist: dict, date: str, lookback: int = 5) -> bool:
    if not fund_hist:
        return False
    days = sorted([d for d in fund_hist if d <= date], reverse=True)[:lookback]
    if len(days) < 3:
        return True
    s = 0.0
    for d in days:
        try:
            s += float((fund_hist[d] or {}).get("main_net") or 0)
        except Exception:
            pass
    return s > 0


def settle_t2(g: pd.DataFrame, signal_ai: int, cost_rt: float, limit_frac: float = 0.97):
    """T+1 开盘买 → T+2 收盘卖。"""
    if signal_ai + 2 >= len(g):
        return None
    bi, si = signal_ai + 1, signal_ai + 2
    prev_close = float(g.loc[signal_ai, "close"])
    buy_open = float(g.loc[bi, "open"])
    if prev_close <= 0 or buy_open <= 0:
        return {"skip": "bad_price"}
    gap = buy_open / prev_close - 1
    lim = limit_pct(str(g.loc[bi, "symbol"]) if "symbol" in g.columns else "")
    # symbol may be in index level — pass separately
    sell_close = float(g.loc[si, "close"])
    gross = sell_close / buy_open - 1
    return {
        "skip": None,
        "buy_date": str(g.loc[bi, "date"])[:10],
        "sell_date": str(g.loc[si, "date"])[:10],
        "buy": buy_open,
        "sell": sell_close,
        "open_gap": gap,
        "gross_ret": gross,
        "ret": gross - cost_rt,
        "limit_gap": lim * limit_frac,
    }


def settle_t2_with_sym(g, signal_ai, cost_rt, sym, limit_frac=0.97):
    if signal_ai + 2 >= len(g):
        return None
    bi, si = signal_ai + 1, signal_ai + 2
    prev_close = float(g.loc[signal_ai, "close"])
    buy_open = float(g.loc[bi, "open"])
    if prev_close <= 0 or buy_open <= 0:
        return {"skip": "bad_price"}
    gap = buy_open / prev_close - 1.0
    lim = limit_pct(sym)
    if gap >= lim * limit_frac:
        return {
            "skip": "open_limit",
            "buy_date": str(g.loc[bi, "date"])[:10],
            "open_gap": gap,
        }
    sell_close = float(g.loc[si, "close"])
    gross = sell_close / buy_open - 1.0
    return {
        "skip": None,
        "buy_date": str(g.loc[bi, "date"])[:10],
        "sell_date": str(g.loc[si, "date"])[:10],
        "buy": buy_open,
        "sell": sell_close,
        "open_gap": gap,
        "gross_ret": gross,
        "ret": gross - cost_rt,
        "legs": 1,
        "exit": "t2_close",
    }


def _fund_sum_asof(fh_all, sym, asof, lookback=3):
    """近 lookback 日主力净流入合计；无数据返回 0。"""
    if not fh_all:
        return 0.0
    bare = "".join(ch for ch in str(sym or "") if ch.isdigit())[-6:]
    series = fh_all.get(bare) or fh_all.get("sh" + bare) or fh_all.get("sz" + bare) or {}
    if not isinstance(series, dict) or not series:
        return 0.0
    if "data" in series and isinstance(series["data"], dict):
        series = series["data"]
    days = sorted([d for d in series.keys() if str(d)[:10] <= asof], reverse=True)[:lookback]
    total = 0.0
    for d in days:
        try:
            v = series[d]
            total += float(v.get("main_net") if isinstance(v, dict) else (v or 0))
        except Exception:
            pass
    return total


def settle_e2_t2_fund_extend(
    g,
    signal_ai,
    cost_rt,
    sym,
    fh_all=None,
    stop_pct=-0.10,
    extend_price_ratio=0.95,
    fund_lookback=3,
    limit_frac=0.97,
):
    """上线协议日K近似：E2 收盘确认硬止损 + T+2 资金延期 1 日（仅一次）。

    优先级：收盘≤成本止损 → 资金净流入且收盘≥95%成本则延到次日收盘强平 → 否则 T+2 收盘。
    不含盘中 peel（日K难还原）。
    """
    if signal_ai + 2 >= len(g):
        return None
    bi, si = signal_ai + 1, signal_ai + 2
    prev_close = float(g.loc[signal_ai, "close"])
    buy_open = float(g.loc[bi, "open"])
    if prev_close <= 0 or buy_open <= 0:
        return {"skip": "bad_price"}
    gap = buy_open / prev_close - 1.0
    buy_date = str(g.loc[bi, "date"])[:10]
    if gap >= limit_pct(sym) * limit_frac:
        return {"skip": "open_limit", "buy_date": buy_date, "open_gap": gap}

    stop_price = buy_open * (1.0 + stop_pct)
    cl = float(g.loc[si, "close"])
    sell_date = str(g.loc[si, "date"])[:10]

    if cl <= stop_price + 1e-12:
        gross = cl / buy_open - 1.0
        return {
            "skip": None,
            "buy_date": buy_date,
            "sell_date": sell_date,
            "buy": buy_open,
            "sell": cl,
            "open_gap": gap,
            "gross_ret": gross,
            "ret": gross - cost_rt,
            "legs": 1,
            "exit": "e2_close_stop",
            "stop_hit": True,
            "t2_extended": False,
        }

    fund_sum = _fund_sum_asof(fh_all or {}, sym, sell_date, fund_lookback)
    can_extend = fund_sum > 0 and cl >= buy_open * extend_price_ratio
    if can_extend and si + 1 < len(g):
        si2 = si + 1
        cl2 = float(g.loc[si2, "close"])
        sell_date2 = str(g.loc[si2, "date"])[:10]
        # 延期日仍可 E2 收盘止损
        if cl2 <= stop_price + 1e-12:
            gross = cl2 / buy_open - 1.0
            return {
                "skip": None,
                "buy_date": buy_date,
                "sell_date": sell_date2,
                "buy": buy_open,
                "sell": cl2,
                "open_gap": gap,
                "gross_ret": gross,
                "ret": gross - cost_rt,
                "legs": 1,
                "exit": "e2_stop_after_extend",
                "stop_hit": True,
                "t2_extended": True,
            }
        gross = cl2 / buy_open - 1.0
        return {
            "skip": None,
            "buy_date": buy_date,
            "sell_date": sell_date2,
            "buy": buy_open,
            "sell": cl2,
            "open_gap": gap,
            "gross_ret": gross,
            "ret": gross - cost_rt,
            "legs": 1,
            "exit": "t2_extended_force",
            "stop_hit": False,
            "t2_extended": True,
        }

    gross = cl / buy_open - 1.0
    return {
        "skip": None,
        "buy_date": buy_date,
        "sell_date": sell_date,
        "buy": buy_open,
        "sell": cl,
        "open_gap": gap,
        "gross_ret": gross,
        "ret": gross - cost_rt,
        "legs": 1,
        "exit": "t2_close",
        "stop_hit": False,
        "t2_extended": False,
    }


def settle_full_trail(
    g, signal_ai, cost_rt, sym, arm=0.03, pull=0.01, max_hold=5, limit_frac=0.97
):
    """旧全仓：激活后回撤≥pull 全清；否则 max_hold 日收盘。"""
    if signal_ai + 1 >= len(g):
        return None
    bi = signal_ai + 1
    prev_close = float(g.loc[signal_ai, "close"])
    buy_open = float(g.loc[bi, "open"])
    if prev_close <= 0 or buy_open <= 0:
        return {"skip": "bad_price"}
    gap = buy_open / prev_close - 1.0
    if gap >= limit_pct(sym) * limit_frac:
        return {"skip": "open_limit", "buy_date": str(g.loc[bi, "date"])[:10], "open_gap": gap}

    peak = buy_open
    armed = False
    end = min(bi + max_hold, len(g) - 1)
    for ai in range(bi, end + 1):
        hi = float(g.loc[ai, "high"])
        cl = float(g.loc[ai, "close"])
        if hi > peak:
            peak = hi
        if peak / buy_open - 1.0 >= arm:
            armed = True
        if armed and peak > 0 and (peak - cl) / peak >= pull:
            gross = cl / buy_open - 1.0
            return {
                "skip": None,
                "buy_date": str(g.loc[bi, "date"])[:10],
                "sell_date": str(g.loc[ai, "date"])[:10],
                "buy": buy_open,
                "sell": cl,
                "open_gap": gap,
                "gross_ret": gross,
                "ret": gross - cost_rt,
                "legs": 1,
                "exit": "full_trail",
            }
    cl = float(g.loc[end, "close"])
    gross = cl / buy_open - 1.0
    return {
        "skip": None,
        "buy_date": str(g.loc[bi, "date"])[:10],
        "sell_date": str(g.loc[end, "date"])[:10],
        "buy": buy_open,
        "sell": cl,
        "open_gap": gap,
        "gross_ret": gross,
        "ret": gross - cost_rt,
        "legs": 1,
        "exit": "max_hold",
    }


def settle_peel(
    g,
    signal_ai,
    cost_rt,
    sym,
    arm=0.03,
    peel_pull=0.015,
    max_hold=5,
    limit_frac=0.97,
    peel_max_steps=2,
):
    """动态减半：权重 1→0.5→0.25→0；日K用 high/close 近似。"""
    if signal_ai + 1 >= len(g):
        return None
    bi = signal_ai + 1
    prev_close = float(g.loc[signal_ai, "close"])
    buy_open = float(g.loc[bi, "open"])
    if prev_close <= 0 or buy_open <= 0:
        return {"skip": "bad_price"}
    gap = buy_open / prev_close - 1.0
    if gap >= limit_pct(sym) * limit_frac:
        return {"skip": "open_limit", "buy_date": str(g.loc[bi, "date"])[:10], "open_gap": gap}

    weight = 1.0
    realized = 0.0  # weighted gross without cost yet
    peak = buy_open
    armed = False
    awaiting = False
    peel_snap = peak
    peel_count = 0
    legs = 0
    end = min(bi + max_hold, len(g) - 1)
    last_ai = end

    for ai in range(bi, end + 1):
        hi = float(g.loc[ai, "high"])
        cl = float(g.loc[ai, "close"])
        last_ai = ai
        if hi > peak:
            peak = hi
        if peak / buy_open - 1.0 >= arm:
            armed = True
        if awaiting and peak > peel_snap + 1e-12:
            awaiting = False
        if not armed or awaiting or weight <= 0:
            continue
        if peak <= 0:
            continue
        pb = (peak - cl) / peak
        if pb < peel_pull:
            continue
        # peel
        if peel_count >= peel_max_steps:
            sell_w = weight
            weight = 0.0
        else:
            sell_w = weight * 0.5
            weight = weight - sell_w
        realized += sell_w * (cl / buy_open - 1.0)
        legs += 1
        peel_count += 1
        peel_snap = peak
        awaiting = weight > 0
        if weight <= 1e-12:
            weight = 0.0
            break

    if weight > 0:
        cl = float(g.loc[last_ai, "close"])
        realized += weight * (cl / buy_open - 1.0)
        legs += 1
        weight = 0.0

    # 成本：按成交腿数粗算（每腿各付一半往返成本的简化：整笔 cost_rt 一次）
    # 更贴近：每笔卖出付 cost_rt * sell_w；买入付一次。这里用 cost_rt 一次 + 0.5*cost_rt*(legs-1)
    cost = cost_rt * (0.5 + 0.5 * max(legs, 1))
    return {
        "skip": None,
        "buy_date": str(g.loc[bi, "date"])[:10],
        "sell_date": str(g.loc[last_ai, "date"])[:10],
        "buy": buy_open,
        "sell": float(g.loc[last_ai, "close"]),
        "open_gap": gap,
        "gross_ret": realized,
        "ret": realized - cost,
        "legs": legs,
        "exit": "peel",
        "peel_count": peel_count,
    }


def settle_t1_stop10_peel(
    g,
    signal_ai,
    cost_rt,
    sym,
    arm: float = 0.03,
    peel_pull: float = 0.015,
    stop_pct: float = -0.10,
    limit_frac: float = 0.97,
    peel_max_steps: int = 2,
):
    """基线 D：low 触及成本硬止损即全清。"""
    return settle_t1_antidump(
        g,
        signal_ai,
        cost_rt,
        sym,
        mode="pierce",
        arm=arm,
        peel_pull=peel_pull,
        stop_pct=stop_pct,
        limit_frac=limit_frac,
        peel_max_steps=peel_max_steps,
    )


def _peel_and_eod(
    buy_open: float,
    bi_hi: float,
    hi: float,
    cl: float,
    arm: float,
    peel_pull: float,
    cost_rt: float,
    peel_max_steps: int = 2,
):
    peak = max(buy_open, bi_hi, hi)
    armed = (peak / buy_open - 1.0) >= arm
    weight = 1.0
    realized = 0.0
    peel_count = 0
    legs = 0
    exit_tag = "t1_eod"

    if armed and peak > 0:
        pb = (peak - cl) / peak
        if pb >= peel_pull:
            if peel_count >= peel_max_steps:
                sell_w = weight
                weight = 0.0
            else:
                sell_w = weight * 0.5
                weight = weight - sell_w
            realized += sell_w * (cl / buy_open - 1.0)
            legs += 1
            peel_count += 1
            exit_tag = "peel_then_eod" if weight > 1e-12 else "peel_clear"

    if weight > 1e-12:
        realized += weight * (cl / buy_open - 1.0)
        legs += 1
        if peel_count == 0:
            exit_tag = "t1_eod"

    cost = cost_rt * (0.5 + 0.5 * max(legs, 1))
    return realized, cost, legs, exit_tag, peel_count, armed


def settle_t1_antidump(
    g,
    signal_ai,
    cost_rt,
    sym,
    mode: str = "pierce",
    arm: float = 0.03,
    peel_pull: float = 0.015,
    stop_pct: float = -0.10,
    limit_frac: float = 0.97,
    peel_max_steps: int = 2,
    entry_gap_skip: float = -0.03,
    gap_half_trigger: float = -0.05,
):
    """防「开盘炸盘再拉升」对照（日K近似）。

    mode:
      pierce         基线：low 触及止损全清（现 D）
      wick_protect   方案1：low 刺穿但收盘回到止损上 → 当作开盘毛刺，不硬止损
      close_confirm  方案2：仅当收盘仍≤止损才清仓（要站稳）
      half_stop      方案3：触及止损先卖一半，另一半收到收盘
      gap_half       方案4：可卖日开盘已相对成本低开≥5%（或开在止损下）→ 开盘卖半、收盘清半
      entry_gap_skip 方案5：买入日开盘相对昨收低开超过阈值则跳过入场
    """
    if signal_ai + 2 >= len(g):
        return None
    bi = signal_ai + 1
    si = signal_ai + 2
    prev_close = float(g.loc[signal_ai, "close"])
    buy_open = float(g.loc[bi, "open"])
    if prev_close <= 0 or buy_open <= 0:
        return {"skip": "bad_price"}
    gap = buy_open / prev_close - 1.0
    buy_date = str(g.loc[bi, "date"])[:10]
    sell_date = str(g.loc[si, "date"])[:10]

    if gap >= limit_pct(sym) * limit_frac:
        return {"skip": "open_limit", "buy_date": buy_date, "open_gap": gap}

    if mode == "entry_gap_skip" and gap <= entry_gap_skip:
        return {
            "skip": "entry_gap_down",
            "buy_date": buy_date,
            "open_gap": gap,
        }

    stop_price = buy_open * (1.0 + stop_pct)
    bi_hi = float(g.loc[bi, "high"])
    op = float(g.loc[si, "open"])
    hi = float(g.loc[si, "high"])
    lo = float(g.loc[si, "low"])
    cl = float(g.loc[si, "close"])
    open_vs_cost = op / buy_open - 1.0

    def _pack(realized, cost, legs, exit_tag, peel_count, armed, stop_hit, sell_px):
        return {
            "skip": None,
            "buy_date": buy_date,
            "sell_date": sell_date,
            "buy": buy_open,
            "sell": sell_px,
            "open_gap": gap,
            "gross_ret": realized,
            "ret": realized - cost,
            "legs": legs,
            "exit": exit_tag,
            "peel_count": peel_count,
            "armed": armed,
            "stop_hit": stop_hit,
            "mode": mode,
        }

    # —— 方案4：开盘已大幅低开 → 开盘卖半 + 收盘清半（不按盘中 low 全清）——
    if mode == "gap_half" and (open_vs_cost <= gap_half_trigger or op <= stop_price + 1e-12):
        sell_open = op
        realized = 0.5 * (sell_open / buy_open - 1.0) + 0.5 * (cl / buy_open - 1.0)
        cost = cost_rt * (0.5 + 0.5 * 2)
        return _pack(
            realized,
            cost,
            2,
            "gap_half_open_eod",
            0,
            False,
            True,
            cl,
        )

    pierced = lo <= stop_price + 1e-12
    gap_through = op <= stop_price + 1e-12

    # —— 方案2：收盘确认止损 ——
    if mode == "close_confirm":
        if cl <= stop_price + 1e-12:
            sell = cl
            gross = sell / buy_open - 1.0
            return _pack(gross, cost_rt, 1, "close_confirm_stop", 0, False, True, sell)
        realized, cost, legs, exit_tag, peel_count, armed = _peel_and_eod(
            buy_open, bi_hi, hi, cl, arm, peel_pull, cost_rt, peel_max_steps
        )
        return _pack(realized, cost, legs, exit_tag, peel_count, armed, False, cl)

    # —— 方案1：影线保护（刺穿但收回）——
    if mode == "wick_protect" and pierced:
        if cl > stop_price + 1e-12:
            realized, cost, legs, exit_tag, peel_count, armed = _peel_and_eod(
                buy_open, bi_hi, hi, cl, arm, peel_pull, cost_rt, peel_max_steps
            )
            return _pack(
                realized,
                cost,
                legs,
                f"wick_protect_{exit_tag}",
                peel_count,
                armed,
                False,
                cl,
            )
        # 收盘仍在止损下 → 仍止损
        sell = op if gap_through else stop_price
        if cl < sell:
            sell = cl
        gross = sell / buy_open - 1.0
        return _pack(gross, cost_rt, 1, "wick_protect_stop", 0, False, True, sell)

    # —— 方案3：触及止损只卖一半 ——
    if mode == "half_stop" and pierced:
        stop_sell = op if gap_through else stop_price
        realized = 0.5 * (stop_sell / buy_open - 1.0) + 0.5 * (cl / buy_open - 1.0)
        cost = cost_rt * (0.5 + 0.5 * 2)
        return _pack(realized, cost, 2, "half_stop_eod", 0, False, True, cl)

    # —— 基线 pierce / gap_half 未触发开盘半仓 / entry_gap_skip 通过后 ——
    if mode in ("pierce", "entry_gap_skip", "gap_half") and pierced:
        sell = op if gap_through else stop_price
        exit_tag = "hard_stop_10_gap" if gap_through else "hard_stop_10"
        gross = sell / buy_open - 1.0
        return _pack(gross, cost_rt, 1, exit_tag, 0, False, True, sell)

    realized, cost, legs, exit_tag, peel_count, armed = _peel_and_eod(
        buy_open, bi_hi, hi, cl, arm, peel_pull, cost_rt, peel_max_steps
    )
    return _pack(realized, cost, legs, exit_tag, peel_count, armed, False, cl)


def day_chg(g: pd.DataFrame, ai: int):
    if ai < 1:
        return None
    prev = float(g.loc[ai - 1, "close"])
    cur = float(g.loc[ai, "close"])
    if prev <= 0:
        return None
    return cur / prev - 1.0


def near_limit(chg, lim: float, frac: float = 0.97) -> bool:
    if chg is None:
        return False
    return chg >= lim * frac


def max_drawdown(day_rets: np.ndarray) -> float:
    if len(day_rets) == 0:
        return 0.0
    eq = np.cumprod(1.0 + day_rets)
    peak = np.maximum.accumulate(eq)
    return float((eq / peak - 1.0).min())


def summarize(trades, name, thr):
    filled = [t for t in trades if not t.get("skipped")]
    skipped = [t for t in trades if t.get("skipped")]
    if not filled:
        return {
            "arm": name,
            "n_signals": len(trades),
            "n_filled": 0,
            "n_skipped": len(skipped),
            "hit_3pct": None,
            "avg_ret": None,
            "note": "no fills",
        }
    rets = np.array([float(t["ret"]) for t in filled], dtype=float)
    by = defaultdict(list)
    for t in filled:
        by[t["date"]].append(float(t["ret"]))
    days = sorted(by)
    day = np.array([float(np.mean(by[d])) for d in days], dtype=float)
    exit_counts: dict[str, int] = defaultdict(int)
    for t in filled:
        exit_counts[str(t.get("exit") or "unknown")] += 1
    n = max(len(filled), 1)
    return {
        "arm": name,
        "n_signals": len(trades),
        "n_filled": len(filled),
        "n_skipped": len(skipped),
        "fill_rate": float(len(filled) / max(len(trades), 1)),
        "n_days": len(days),
        "hit_3pct_rate": float(np.mean(rets >= thr)),
        "win_rate": float(np.mean(rets > 0)),
        "avg_ret": float(np.mean(rets)),
        "median_ret": float(np.median(rets)),
        "p25_ret": float(np.percentile(rets, 25)),
        "p75_ret": float(np.percentile(rets, 75)),
        "day_win_rate": float(np.mean(day > 0)),
        "day_avg_ret": float(np.mean(day)),
        "max_drawdown": max_drawdown(day),
        "total_return": float(np.prod(1.0 + day) - 1.0),
        "avg_legs": float(np.mean([t.get("legs") or 1 for t in filled])),
        "exit_breakdown": {k: {"n": v, "rate": float(v / n)} for k, v in sorted(exit_counts.items())},
        "stop_hit_rate": float(np.mean([bool(t.get("stop_hit")) for t in filled])),
        "peel_trigger_rate": float(
            np.mean([int(t.get("peel_count") or 0) > 0 for t in filled])
        ),
    }


def pick_candidates_momentum(groups, date, args, fh_all):
    cands = []
    for sym, g in groups.items():
        idx = g.index[g["date"] == date]
        if len(idx) == 0:
            continue
        ai = int(idx[0])
        if ai < 20 or ai + 1 >= len(g):
            continue
        c0 = float(g.loc[ai, "close"])
        c5 = float(g.loc[ai - 5, "close"]) if ai >= 5 else c0
        score = (c0 / c5 - 1.0) if c5 > 0 else 0.0
        if args.fund_gate and fh_all:
            fh = fh_all.get(sym) or fh_all.get(f"sz{sym}") or fh_all.get(f"sh{sym}") or {}
            if isinstance(fh, dict) and "data" in fh:
                fh = fh.get("data") or {}
            if fh and not fund_gate_ok(fh, date, 5):
                continue
        cands.append({"symbol": sym, "ai": ai, "score": score})
    return sorted(cands, key=lambda x: -x["score"])[: args.top_n]


def pick_candidates_vm25(groups, date, args, scorer, volume_gc_asof, fund_gate_pipeline):
    """对齐可交易 A 臂：严格金叉 + 信号日非涨停 + VM2.5 + 资金硬门控 → TopN。"""
    pool = []
    for sym, g in groups.items():
        idxs = g.index[g["date"] <= date]
        if len(idxs) == 0:
            continue
        ai = int(idxs[-1])
        if str(g.loc[ai, "date"]) != date:
            continue
        if ai + 2 >= len(g):
            continue
        lim = limit_pct(sym)
        chg = day_chg(g, ai)
        if near_limit(chg, lim, args.limit_frac):
            continue
        if not volume_gc_asof(g, ai):
            continue
        sub = g.iloc[: ai + 1].copy()
        try:
            r = scorer.score(sub, sym)
        except Exception:
            continue
        if not r or "error" in r:
            continue
        fh = scorer.fund_flow.get(sym, {})
        if args.fund_gate and not fund_gate_pipeline(fh, date, 5):
            continue
        pool.append(
            {
                "symbol": sym,
                "ai": ai,
                "score": float(r["score"]),
                "signal_chg": chg,
            }
        )
    return sorted(pool, key=lambda x: -x["score"])[: args.top_n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-04-01")
    ap.add_argument("--end", default="2026-07-17")
    ap.add_argument("--top-n", type=int, default=2)
    ap.add_argument("--threshold", type=float, default=0.03)
    ap.add_argument("--cost-rt", type=float, default=0.0015)
    ap.add_argument("--max-hold", type=int, default=5)
    ap.add_argument("--peel-pull", type=float, default=0.015)
    ap.add_argument("--arm", type=float, default=0.03)
    ap.add_argument(
        "--rank",
        choices=("vm25", "momentum"),
        default="vm25",
        help="选股：vm25=正式验收；momentum=快速代理",
    )
    ap.add_argument(
        "--fund-gate",
        action="store_true",
        default=None,
        help="资金硬门控（vm25 默认开；momentum 默认关）",
    )
    ap.add_argument("--no-fund-gate", action="store_true", help="关闭资金硬门控")
    ap.add_argument("--prefer", default="opt")
    ap.add_argument("--limit-frac", type=float, default=0.97)
    ap.add_argument("--stop-pct", type=float, default=-0.10, help="D 臂成本硬止损比例")
    ap.add_argument(
        "--suite",
        choices=("full", "antidump", "extend"),
        default="full",
        help="full=A/B/C/D；antidump=D0基线+五套防炸盘近似；extend=原T+2 vs E2+资金延期",
    )
    ap.add_argument(
        "--out",
        default="",
        help="输出文件名（默认按 suite/rank 自动命名）",
    )
    args = ap.parse_args()

    if args.no_fund_gate:
        args.fund_gate = False
    elif args.fund_gate is None:
        args.fund_gate = args.rank == "vm25"

    os.chdir(ROOT)

    kpath = ROOT / "data/kline_cache/kline_all.parquet"
    if not kpath.exists():
        kpath = ROOT / "kline_all.parquet"
    print("load kline", kpath, flush=True)
    kdf = pd.read_parquet(kpath)
    kdf["date"] = kdf["date"].astype(str).str[:10]
    kdf["symbol"] = kdf["symbol"].astype(str).map(_bare)
    for c in ("open", "high", "low", "close"):
        if c not in kdf.columns:
            raise SystemExit(f"missing column {c}")
    kdf = kdf[~kdf["symbol"].str.startswith(("8", "4"))]
    kdf = kdf.sort_values(["symbol", "date"]).reset_index(drop=True)

    print("build per-symbol groups...", flush=True)
    groups = {
        sym: g.sort_values("date").reset_index(drop=True)
        for sym, g in kdf.groupby("symbol", sort=False)
    }
    cal_sym = "600519" if "600519" in groups else next(iter(groups))
    dates = sorted(d for d in groups[cal_sym]["date"].unique() if args.start <= d <= args.end)

    scorer = None
    volume_gc_asof = None
    fund_gate_pipeline = None
    fh_all = {}
    fp = ROOT / "data/fund_flow_history.json"
    if fp.exists() and (args.suite == "extend" or args.fund_gate or args.rank != "vm25"):
        try:
            fh_all = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            fh_all = {}
    if args.rank == "vm25":
        from vm25_scorer import VM25Scorer
        from backtest_v3_pipeline import volume_gc_asof, fund_gate_ok as fund_gate_pipeline

        scorer = VM25Scorer(prefer=args.prefer)
        assert scorer.load(), "VM2.5 model load failed"
        print(
            f"rank=vm25 prefer={args.prefer} feats={len(scorer.feature_names)} "
            f"fund_gate={args.fund_gate} suite={args.suite}",
            flush=True,
        )
    else:
        print(f"rank=momentum fund_gate={args.fund_gate} suite={args.suite}", flush=True)

    print(f"days={len(dates)} symbols={len(groups)} calendar={cal_sym}", flush=True)

    antidump_modes = [
        ("D0_pierce", "pierce"),
        ("E1_wick_protect", "wick_protect"),
        ("E2_close_confirm", "close_confirm"),
        ("E3_half_stop", "half_stop"),
        ("E4_gap_half", "gap_half"),
        ("E5_entry_gap_skip", "entry_gap_skip"),
    ]

    if args.suite == "antidump":
        arms = {name: [] for name, _ in antidump_modes}
    elif args.suite == "extend":
        arms = {
            "A_t2_close": [],
            "F_e2_t2_fund_extend": [],
        }
    else:
        arms = {
            "A_t2_close": [],
            "B_peel_15": [],
            "C_full_trail1": [],
            "D_t1_stop10_peel": [],
        }

    t0 = time.time()
    for di, date in enumerate(dates):
        if args.rank == "vm25":
            picks = pick_candidates_vm25(
                groups, date, args, scorer, volume_gc_asof, fund_gate_pipeline
            )
        else:
            picks = pick_candidates_momentum(groups, date, args, fh_all)

        for p in picks:
            sym, ai = p["symbol"], p["ai"]
            g = groups[sym]
            if args.suite == "antidump":
                settled = {
                    name: settle_t1_antidump(
                        g,
                        ai,
                        args.cost_rt,
                        sym,
                        mode=mode,
                        arm=args.arm,
                        peel_pull=args.peel_pull,
                        stop_pct=args.stop_pct,
                    )
                    for name, mode in antidump_modes
                }
            elif args.suite == "extend":
                settled = {
                    "A_t2_close": settle_t2_with_sym(g, ai, args.cost_rt, sym),
                    "F_e2_t2_fund_extend": settle_e2_t2_fund_extend(
                        g,
                        ai,
                        args.cost_rt,
                        sym,
                        fh_all=fh_all,
                        stop_pct=args.stop_pct,
                    ),
                }
            else:
                settled = {
                    "A_t2_close": settle_t2_with_sym(g, ai, args.cost_rt, sym),
                    "B_peel_15": settle_peel(
                        g,
                        ai,
                        args.cost_rt,
                        sym,
                        arm=args.arm,
                        peel_pull=args.peel_pull,
                        max_hold=args.max_hold,
                    ),
                    "C_full_trail1": settle_full_trail(
                        g,
                        ai,
                        args.cost_rt,
                        sym,
                        arm=args.arm,
                        pull=0.01,
                        max_hold=args.max_hold,
                    ),
                    "D_t1_stop10_peel": settle_t1_stop10_peel(
                        g,
                        ai,
                        args.cost_rt,
                        sym,
                        arm=args.arm,
                        peel_pull=args.peel_pull,
                        stop_pct=args.stop_pct,
                    ),
                }
            for arm_name, st in settled.items():
                base = {
                    "date": date,
                    "symbol": sym,
                    "score": p.get("score"),
                }
                if st is None:
                    arms[arm_name].append({**base, "skipped": True, "skip_reason": "no_bar"})
                    continue
                if st.get("skip"):
                    arms[arm_name].append(
                        {
                            **base,
                            "skipped": True,
                            "skip_reason": st["skip"],
                            "buy_date": st.get("buy_date"),
                        }
                    )
                    continue
                arms[arm_name].append(
                    {
                        **base,
                        "skipped": False,
                        "ret": st["ret"],
                        "gross_ret": st["gross_ret"],
                        "buy": st["buy"],
                        "sell": st["sell"],
                        "buy_date": st["buy_date"],
                        "sell_date": st["sell_date"],
                        "legs": st.get("legs", 1),
                        "exit": st.get("exit"),
                        "peel_count": st.get("peel_count", 0),
                        "stop_hit": bool(st.get("stop_hit")),
                        "armed": st.get("armed"),
                        "t2_extended": bool(st.get("t2_extended")),
                        "mode": st.get("mode"),
                        "hit_3pct": st["ret"] >= args.threshold,
                    }
                )

        if (di + 1) % 5 == 0 or di == 0:
            print(
                f"  {date} picks={len(picks)} elapsed={int(time.time()-t0)}s",
                flush=True,
            )

    kpis = [summarize(arms[k], k, args.threshold) for k in arms]
    rank_label = (
        "VM2.5 + strict volume GC + hard fund gate (tradable A aligned)"
        if args.rank == "vm25"
        else "5d momentum proxy (NOT VM2.5)"
    )
    if args.suite == "antidump":
        out = {
            "protocol": {
                "entry": "T+1 open skip limit-up; signal-day near-limit excluded (vm25)",
                "rank": rank_label,
                "rank_mode": args.rank,
                "suite": "antidump",
                "approx_note": (
                    "日K无法还原分钟；E1≈开盘保护窗(刺穿收回不卖)；"
                    "E2≈止损确认(收盘站稳)；E3≈早盘分批；"
                    "E4≈大低开先卖半；E5≈买入低开过滤"
                ),
                "D0_pierce": f"baseline hard stop {args.stop_pct:.0%} on low pierce + peel + eod",
                "E1_wick_protect": "low pierce but close>stop → ignore stop (bounce)",
                "E2_close_confirm": "stop only if close<=stop",
                "E3_half_stop": "pierce → 50% at stop + 50% at close",
                "E4_gap_half": "sell-day open vs cost<=-5% → 50% open + 50% close",
                "E5_entry_gap_skip": "skip if buy open gap vs prev close <= -3%",
                "cost_rt": args.cost_rt,
                "top_n": args.top_n,
                "fund_gate": bool(args.fund_gate),
                "stop_pct": args.stop_pct,
            },
            "window": {"start": args.start, "end": args.end},
            "kpi": kpis,
            "n_trades": {k: len([t for t in arms[k] if not t.get("skipped")]) for k in arms},
            "comparison_focus": [name for name, _ in antidump_modes],
        }
        default_out = "exit_antidump_compare.json"
    elif args.suite == "extend":
        out = {
            "protocol": {
                "entry": "T+1 open skip limit-up; signal-day near-limit excluded (vm25)",
                "rank": rank_label,
                "rank_mode": args.rank,
                "suite": "extend",
                "A": "T+2 close (baseline)",
                "F": (
                    f"E2 close-confirm stop {args.stop_pct:.0%}; "
                    "else if 3d main_net>0 and close>=95% cost → hold +1d then force; "
                    "else T+2 close (no peel in day-K arm)"
                ),
                "cost_rt": args.cost_rt,
                "top_n": args.top_n,
                "fund_gate": bool(args.fund_gate),
                "stop_pct": args.stop_pct,
            },
            "window": {"start": args.start, "end": args.end},
            "kpi": kpis,
            "n_trades": {k: len([t for t in arms[k] if not t.get("skipped")]) for k in arms},
            "comparison_focus": ["A_t2_close", "F_e2_t2_fund_extend"],
        }
        default_out = (
            "exit_fund_extend_compare.json"
            if args.rank == "vm25"
            else "exit_fund_extend_compare_momentum.json"
        )
    else:
        out = {
            "protocol": {
                "entry": "T+1 open skip limit-up; signal-day near-limit excluded (vm25)",
                "rank": rank_label,
                "rank_mode": args.rank,
                "suite": "full",
                "A": "T+2 close",
                "B": f"peel arm>={args.arm:.0%} pull>={args.peel_pull:.1%} half×2 then clear; max_hold={args.max_hold}",
                "C": "full trail arm>=3% pull>=1%",
                "D": (
                    f"sellable day after buy: hard stop {args.stop_pct:.0%} vs cost; "
                    f"peel if peak>={args.arm:.0%}; force flat at that close"
                ),
                "cost_rt": args.cost_rt,
                "top_n": args.top_n,
                "fund_gate": bool(args.fund_gate),
                "note": "日K high/low/close 近似盘中；同日止损优先于 peel",
            },
            "window": {"start": args.start, "end": args.end},
            "kpi": kpis,
            "n_trades": {k: len([t for t in arms[k] if not t.get("skipped")]) for k in arms},
            "comparison_focus": ["A_t2_close", "B_peel_15", "D_t1_stop10_peel"],
        }
        default_out = (
            "exit_t1_stop10_compare.json"
            if args.rank == "vm25"
            else "exit_t1_stop10_compare_momentum.json"
        )
    out_name = args.out or default_out
    out_path = ROOT / "output" / out_name
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("======== Exit Peel Backtest ========", flush=True)
    print(json.dumps(out["protocol"], ensure_ascii=False), flush=True)
    for k in kpis:
        print(json.dumps(k, ensure_ascii=False), flush=True)
    print("saved", out_path, flush=True)


if __name__ == "__main__":
    main()
