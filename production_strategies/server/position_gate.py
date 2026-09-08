#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""位置闸 (position gate) —— Issue#6 后续决策, 2026-09-06 老板拍板。

背景: 002437 誉衡 09-02 在高位回落段被候选池 rank1 推荐并买入 (现 -13%)。
其本质缺陷: 选股模型只有资金/动量维, 缺少"位置/结构"维 —— 对"翻倍后高位派发、
从 60 日高点回落途中"的票无感知, 把派发反抽误判为拉升。

回测 (bt_research/bt_position_gate_p*.py, 服务器真实 45 笔已成交 Top2 结算):
  规则 A (up_low>0.5 且 dist_hi<-0.05): veto 组 t5 均值 -7.33% (n=12, 胜率25%),
  保留组 t5 均值 +4.58% (n=23, 胜率65%)。002437 的首笔好买 (08-12 @3.43,
  T+5 +11.4%, up_low=0.48) 不拦; 后三笔高位追买全拦 (08-19/08-27/09-02)。
  更严规则 F 会漏 万里马(-13.7)/紫光(-8.8)/永安(-9.2) 三笔大亏, 故弃。

口径 (与回测一致, 无未来函数):
  hi60/lo60 = 截止 T-1 (含) 的 60 交易日最高/最低
  up_low    = close(T-1)/lo60 - 1   "当前仍高于 60 日低点多少"
  dist_hi   = close(T-1)/hi60 - 1   "当前距 60 日高点回落多少"
  veto: up_low > 0.5 and dist_hi < -0.05
  即: 已从底部大涨 >50% 且已自顶部回落 >5% = 高位派发/转弱嫌疑 → 不入候选。

仅对 kline 数据不足 (上市 <30 根) 的票放行 (不误杀次新); kline 缺失整体保守
放行 (保持旧行为), 绝不阻断导出主流程。

用法: 见 export_qmt_scores.py _apply_position_gate / morning live 链。
"""
from datetime import datetime
from pathlib import Path

# 可调阈值 (老板可后续在 CHANGELOG 直接改)
POS_UP_LOW_MIN = 0.5      # 高于 60 日低点 > 50%
POS_DIST_HI_MAX = -0.05   # 自 60 日高点回落 > 5%
POS_MIN_BARS = 30         # 少于 30 根历史 kline 保守放行


def _root_kline(root: Path) -> Path:
    p = root / "data" / "kline_cache" / "kline_all.parquet"
    if p.exists():
        return p
    cand = root.parents[1] if len(root.parents) > 1 else root
    p2 = cand / "data" / "kline_cache" / "kline_all.parquet"
    return p2 if p2.exists() else p


def _bare(sym: str) -> str:
    s = str(sym or "").split(".")[0].upper()
    for pre in ("SH", "SZ", "BJ"):
        s = s.replace(pre, "")
    return s.zfill(6)[-6:] if s else ""


def position_meta(root: Path, code_set) -> dict:
    """每只 code 的 60 日位置因子 (截止 T-1, 无未来函数)。

    返回 {bare6: {"runup60","up_low","dist_hi","ma60_pos","veto"}};
    数据不足/缺失 -> 该 code 不在返回 dict (调用方按放行处理)。
    """
    code_set = {_bare(c) for c in code_set if _bare(c)}
    if not code_set:
        return {}
    try:
        import pandas as pd
    except Exception:
        return {}
    kline = _root_kline(root)
    if not kline.exists():
        return {}
    try:
        df = pd.read_parquet(kline,
                             columns=["symbol", "date", "high", "low", "close"])
    except Exception as e:
        print(f"[POSGATE] kline read skip: {e}", flush=True)
        return {}
    df["date"] = pd.to_datetime(df["date"])
    df["symbol"] = df["symbol"].map(_bare)
    df = df[df["symbol"].isin(code_set)].sort_values(["symbol", "date"])
    if df.empty:
        return {}
    today = pd.Timestamp(datetime.now().strftime("%Y-%m-%d"))
    df = df[df["date"] < today]            # 只用 T-1 及以前
    if df.empty:
        return {}
    tail = df.groupby("symbol", group_keys=False).tail(60)
    last = df.groupby("symbol", group_keys=False).tail(1)
    out = {}
    for sym, grp in tail.groupby("symbol"):
        cls = last[last["symbol"] == sym]["close"]
        if len(grp) < POS_MIN_BARS or cls.empty:
            continue
        hi60 = float(grp["high"].max())
        lo60 = float(grp["low"].min())
        close_t1 = float(cls.iloc[0])
        if hi60 <= 0 or lo60 <= 0 or close_t1 <= 0:
            continue
        up_low = close_t1 / lo60 - 1.0
        dist_hi = close_t1 / hi60 - 1.0
        ma60 = float(grp["close"].mean())
        out[sym] = {
            "runup60": round(hi60 / lo60 - 1.0, 3),
            "up_low": round(up_low, 3),
            "dist_hi": round(dist_hi, 3),
            "ma60_pos": round(close_t1 / ma60 - 1.0, 3) if ma60 > 0 else None,
            "veto": bool(up_low > POS_UP_LOW_MIN and dist_hi < POS_DIST_HI_MAX),
        }
    return out


def stamp_rows(root: Path, rows) -> tuple:
    """给候选行打位置因子标, 返回 (rows, vetoed)。

    每行写入 runup60/up_low/dist_hi/ma60_pos/position_veto。
    kline 缺该 code -> 行留 position_veto=False (保守放行)。
    vetoed = [{symbol,name,runup60,up_low,dist_hi,position_veto}...] 供审计。
    """
    codes = {_bare(r.get("symbol")) for r in rows if r.get("symbol")}
    meta = position_meta(root, codes)
    vetoed = []
    for r in rows:
        m = meta.get(_bare(r.get("symbol")))
        if not m:
            r["runup60"] = None
            r["up_low"] = None
            r["dist_hi"] = None
            r["ma60_pos"] = None
            r["position_veto"] = False
            continue
        r["runup60"] = m["runup60"]
        r["up_low"] = m["up_low"]
        r["dist_hi"] = m["dist_hi"]
        r["ma60_pos"] = m["ma60_pos"]
        r["position_veto"] = bool(m["veto"])
        if m["veto"]:
            vetoed.append({
                "symbol": r.get("symbol"),
                "name": r.get("name") or "",
                "runup60": m["runup60"],
                "up_low": m["up_low"],
                "dist_hi": m["dist_hi"],
            })
    return rows, vetoed
