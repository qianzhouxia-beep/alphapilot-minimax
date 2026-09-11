#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盘中资金强度分析 — 回答「今天流入这个量，算什么水平？后续能冲板吗？」

核心逻辑（每只监控标的）：
  1. 强度分位 rank_pct：
     今日实时主力净额(折算全天) vs 该股近 60 日历史日度净额序列 → 分位(0~1)。
     例：rank=0.88 → 今天这波资金流入，历史上只有 12% 的日子更强。
  2. 流速 speed_ratio：
     (今日净额 / 已交易分钟) ÷ (历史日均净额 / 240) → >1 说明资金比历史平均急。
  3. 冲板概率 limit_up_prob：
     用全市场近 60 日横截面建「净额分位 → 当日涨停率」经验表（约 30 万样本），
     按当前分位查表，再用当日已涨幅修正（越接近涨停，剩余空间越小）。
     经验表带日期缓存（每日重建一次），盘中每 3 分钟运行仅做轻量计算。

数据源：
  - 实时快照: output/institutional_watch.json（institutional_watch.py 每3分钟刷新）
  - 历史净额: data/fund_flow_history.json（5003 股 × 132 日，口径=元，正流入）
  - 历史涨跌: data/kline_cache/kline_all.parquet（用于算涨停样本）

输出: output/fund_strength.json
  { ts, asof, n_items, items: { bare_code: { rank_pct, speed_ratio, limit_up_prob, label } } }

由 institutional_watch.py 每轮快照后调用，也可独立跑:
  python3 fund_strength.py
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(os.environ.get("ALPHAPILOT_ROOT", "/home/ubuntu/alphapilot"))
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

OUT = ROOT / "output"
DATA = ROOT / "data"
WATCH_PATH = OUT / "institutional_watch.json"
FUND_HIST_PATH = DATA / "fund_flow_history.json"
KLINE_PATH = DATA / "kline_cache" / "kline_all.parquet"
STRENGTH_PATH = OUT / "fund_strength.json"
TABLE_CACHE = DATA / "fund_limitup_table_cache.json"

HIST_LOOKBACK = 60          # 对比窗口（交易日）
TRADING_MINUTES = 240       # 全日交易分钟
ELAPSED_MIN = 120           # 早盘折算下限（分钟）：折算不超过 ~3.3x
MIN_HIST_DAYS = 10          # 单股历史天数下限

_EMPTY = {
    "ts": None,
    "asof": None,
    "n_items": 0,
    "items": {},
    "note": "资金强度分析未运行",
}


def _bare(sym: str) -> str:
    return str(sym or "").lower().replace("sh", "").replace("sz", "").replace("bj", "")[-6:]


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_json(path: Path, data: Any) -> None:
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def elapsed_minutes() -> float:
    """当前已交易分钟数（早盘 0-120，午后 120-240，盘外回退 240）。"""
    import datetime as _dt

    now = _dt.datetime.now()
    hm = now.hour * 60 + now.minute
    if hm <= 9 * 60 + 30:
        return 1.0
    if hm <= 11 * 60 + 30:
        return float(hm - (9 * 60 + 30))
    if hm <= 13 * 60:
        return 120.0
    if hm <= 15 * 60:
        return 120.0 + float(hm - 13 * 60)
    return 240.0


def _load_fund_hist() -> dict[str, dict[str, float]]:
    d = _load_json(FUND_HIST_PATH) or {}
    out: dict[str, dict[str, float]] = {}
    for sym, hist in d.items():
        if isinstance(hist, dict):
            try:
                out[_bare(sym)] = {str(k): float(v) for k, v in hist.items()}
            except Exception:
                continue
    return out


def _build_limitup_table(fund: dict[str, dict[str, float]]) -> dict[str, float]:
    """全市场横截面经验表: 分位桶(0~9) → 当日涨停率。约 30 万样本，耗时 ~80s。"""
    import pandas as pd

    try:
        kdf = pd.read_parquet(KLINE_PATH, columns=["date", "close", "symbol"])
    except Exception:
        return {}
    dates = sorted(kdf["date"].unique())
    if len(dates) > HIST_LOOKBACK:
        dates = dates[-HIST_LOOKBACK:]
    kdf = kdf[kdf["date"].isin(dates)]
    if kdf.empty:
        return {}
    kdf["chg"] = kdf.groupby("symbol")["close"].pct_change()
    kdf["limit_up"] = (kdf["chg"] >= 0.095).astype(int)

    buckets: dict[int, list[float]] = {i: [] for i in range(10)}
    for sym, hist in fund.items():
        if len(hist) < 20:
            continue
        seq = sorted(hist.values())
        sub = kdf[kdf["symbol"] == sym]
        if sub.empty:
            continue
        lu_by_date = dict(zip(sub["date"].astype(str), sub["limit_up"]))
        for dt, net in hist.items():
            if dt not in lu_by_date or len(seq) < 2:
                continue
            rank = sum(1 for x in seq if x <= net) / len(seq)
            b = min(9, int(rank * 10))
            buckets[b].append(float(lu_by_date[dt]))
    return {str(b): float(np.mean(vals)) for b, vals in buckets.items() if vals}


def load_limitup_table(force_rebuild: bool = False) -> dict[str, float]:
    """带日期缓存的经验表：当日已建则直接读，否则重建并落盘。"""
    today = time.strftime("%Y-%m-%d")
    if not force_rebuild:
        cache = _load_json(TABLE_CACHE)
        if cache and cache.get("asof") == today and isinstance(cache.get("table"), dict):
            return {str(k): float(v) for k, v in cache["table"].items()}

    t0 = time.time()
    fund = _load_fund_hist()
    table = _build_limitup_table(fund)
    _save_json(TABLE_CACHE, {"asof": today, "table": table})
    print(f"[fund_strength] 经验表重建完成: {len(table)} 桶, 耗时 {time.time()-t0:.0f}s", flush=True)
    return table


def analyze(force_rebuild: bool = False) -> dict:
    """主入口：读实时快照 + 历史，输出强度结论。"""
    watch = _load_json(WATCH_PATH)
    if not watch:
        return dict(_EMPTY)
    snapshot = watch.get("snapshot") or {}
    fund = _load_fund_hist()
    table = load_limitup_table(force_rebuild=force_rebuild)

    elapsed = elapsed_minutes()
    elapsed_capped = max(float(elapsed), ELAPSED_MIN)
    items: dict[str, dict] = {}
    for sym, row in snapshot.items():
        bare = _bare(sym)
        try:
            today_net = float(row.get("main_net") or 0)
        except (TypeError, ValueError):
            continue
        # 机构净占比（东财 f184 / f187，单位 %）
        try:
            main_net_pct = float(row.get("main_net_pct") or 0)
        except (TypeError, ValueError):
            main_net_pct = 0.0
        try:
            super_net_pct = float(row.get("super_net_pct") or 0)
        except (TypeError, ValueError):
            super_net_pct = 0.0
        hist = fund.get(bare) or {}
        vals = sorted(hist.values())
        if len(vals) < MIN_HIST_DAYS:
            items[bare] = {
                "symbol": bare, "name": row.get("name", ""), "source": row.get("source", ""),
                "rank_pct": None, "speed_ratio": None, "limit_up_prob": None,
                "label": "历史不足", "today_net_yi": round(today_net / 1e8, 4),
                "main_net_pct": round(main_net_pct, 2), "super_net_pct": round(super_net_pct, 2),
                "hist_days": len(vals),
            }
            continue

        # 1) 强度分位：今日净额折算全天后 vs 历史序列
        annualized = today_net / max(elapsed_capped / TRADING_MINUTES, 0.05)
        rank = sum(1 for x in vals if x <= annualized) / len(vals)
        rank_pct = round(min(0.999, max(0.001, rank)), 4)

        # 2) 流速：每分钟净额 vs 历史日均每分钟
        avg_daily = float(np.mean(vals))
        speed = (today_net / max(elapsed_capped, 1.0)) / (avg_daily / TRADING_MINUTES) if avg_daily else 0.0
        speed_ratio = round(max(0.0, min(9.999, speed)), 2)

        # 3) 冲板概率 = 当日涨停经验表(分位桶) × 涨幅空间修正
        b = min(9, int(rank_pct * 10))
        base = float(table.get(str(b), 0.0))
        try:
            chg = float(row.get("change_pct") or 0)
        except (TypeError, ValueError):
            chg = 0.0
        headroom = max(0.0, 1.0 - max(chg, 0.0) / 9.8)  # 已涨越多剩余空间越小
        limit_up_prob = round(min(0.95, base * (0.7 + 0.3 * headroom)), 4)

        label = _build_label(rank_pct, speed_ratio, limit_up_prob)
        inst_label = _build_inst_label(main_net_pct, super_net_pct)
        if inst_label:
            label = f"{label} · {inst_label}"
        items[bare] = {
            "symbol": bare, "name": row.get("name", ""), "source": row.get("source", ""),
            "rank_pct": rank_pct, "speed_ratio": speed_ratio, "limit_up_prob": limit_up_prob,
            "label": label,
            "today_net_yi": round(today_net / 1e8, 4),
            "main_net_pct": round(main_net_pct, 2), "super_net_pct": round(super_net_pct, 2),
            "hist_days": len(vals),
        }

    import datetime as _dt

    result = {
        "ts": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "asof": watch.get("ts"),
        "n_items": len(items),
        "items": items,
        "note": "资金强度：分位(近60日) + 流速 + 冲板概率(横截面经验表·当日口径)",
    }
    STRENGTH_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _build_inst_label(main_net_pct: float, super_net_pct: float) -> str:
    """机构净占比标签：主力净占比 / 超大单净占比（东财口径，单位 %）。

    超过阈值时给出读数，否则返回空串。
    """
    parts: list[str] = []
    if super_net_pct and abs(super_net_pct) >= 2.0:
        parts.append(f"超大单{super_net_pct:+.1f}%")
    elif main_net_pct and abs(main_net_pct) >= 2.0:
        parts.append(f"主力{main_net_pct:+.1f}%")
    return " · ".join(parts)


def _build_label(rank_pct: float | None, speed_ratio: float | None, limit_up_prob: float | None) -> str:
    if rank_pct is None:
        return "数据不足"
    parts: list[str] = []
    if rank_pct >= 0.9:
        parts.append("极强")
    elif rank_pct >= 0.7:
        parts.append("偏强")
    elif rank_pct >= 0.5:
        parts.append("中性")
    elif rank_pct >= 0.3:
        parts.append("偏弱")
    else:
        parts.append("极弱")
    if speed_ratio is not None:
        parts.append(f"流速{speed_ratio:.1f}x")
    if limit_up_prob is not None:
        prob_label = "高" if limit_up_prob >= 0.15 else ("中" if limit_up_prob >= 0.06 else "低")
        parts.append(f"冲板概率{prob_label}")
    return " · ".join(parts)


if __name__ == "__main__":
    import sys

    force = "--rebuild" in sys.argv
    r = analyze(force_rebuild=force)
    print(f"资金强度分析: {r['n_items']} 只")
    for sym, it in list(r.get("items", {}).items())[:8]:
        print(
            f"  {it['name']} {sym} rank={it.get('rank_pct')} "
            f"speed={it.get('speed_ratio')} limit={it.get('limit_up_prob')} → {it.get('label')}"
        )
