#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""机会许可门（Permission Gate）— 折中方案。

指数不再单独判死刑：先看截面机会（宽度 + 3/5/10 日 sustained_in），再定仓位。

许可 ON：涨≥3% 只数 ≥100，或 ≥1 个 sustained_in 行业
nuclear 空仓：仅 crash_day 且 无 sustained_in 且 up3 < 50
其余：至少地板 0.25（薄仓 Top1）
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent

UP3_ON = int(os.environ.get("PERM_UP3_ON", "100"))
UP3_BOOST = int(os.environ.get("PERM_UP3_BOOST", "200"))
UP3_DEAD = int(os.environ.get("PERM_UP3_DEAD", "50"))


def _bare(sym: str) -> str:
    s = str(sym or "").lower().replace("sh", "").replace("sz", "").replace("bj", "")
    return s[-6:]


def _load_kline(kdf: pd.DataFrame | None = None) -> pd.DataFrame:
    if kdf is not None:
        return kdf
    for p in (ROOT / "data/kline_cache/kline_all.parquet", ROOT / "kline_all.parquet"):
        if p.exists():
            df = pd.read_parquet(p)
            df = df.copy()
            df["date"] = df["date"].astype(str).str[:10]
            df["symbol"] = df["symbol"].astype(str).map(_bare)
            return df
    raise FileNotFoundError("kline parquet missing")


def count_up3(asof: str, kdf: pd.DataFrame | None = None, thr: float = 0.03) -> int:
    """asof 日涨幅 ≥ thr 的股票数（相对前一交易日收盘）。"""
    df = _load_kline(kdf)
    asof = str(asof)[:10]
    cal = sorted(df["date"].unique())
    prevs = [d for d in cal if d < asof]
    if not prevs:
        return 0
    prev = prevs[-1]
    day = df.loc[df["date"] == asof, ["symbol", "close"]]
    if day.empty:
        return 0
    prv = df.loc[df["date"] == prev, ["symbol", "close"]].rename(columns={"close": "prev"})
    m = day.merge(prv, on="symbol", how="inner")
    m = m[(m["prev"] > 0) & (m["close"] > 0)]
    if m.empty:
        return 0
    ret = m["close"] / m["prev"] - 1.0
    return int((ret >= thr).sum())


def count_sustained_industries(asof: str) -> tuple[int, list[str]]:
    """3/5/10 日行业资金：sustained_in 个数与名称。"""
    try:
        from weak_fund_sleeve import (
            aggregate_industry_flow,
            load_fund,
            load_industry_map,
        )
    except Exception:
        return 0, []
    fund = load_fund()
    imap = load_industry_map()
    if not fund or not imap:
        return 0, []
    # 日历用资金流日期并集
    sample = next(iter(fund.values()), {})
    cal = sorted(str(k)[:10] for k in sample.keys()) if isinstance(sample, dict) else []
    if not cal:
        return 0, []
    asof = str(asof)[:10]
    if asof not in cal:
        le = [d for d in cal if d <= asof]
        if not le:
            return 0, []
        asof = le[-1]
    ind = aggregate_industry_flow(fund, imap, cal, asof)
    names = [v["industry"] for v in ind.values() if v.get("class") == "sustained_in"]
    names.sort()
    return len(names), names[:12]


def compute_permission(asof: str, kdf: pd.DataFrame | None = None) -> dict[str, Any]:
    asof = str(asof)[:10]
    up3 = count_up3(asof, kdf=kdf)
    n_sus, sus_names = count_sustained_industries(asof)
    permission_on = up3 >= UP3_ON or n_sus >= 1
    rotation_dead = n_sus == 0 and up3 < UP3_DEAD
    return {
        "asof": asof,
        "up3_count": up3,
        "n_sustained_in": n_sus,
        "sustained_industries": sus_names,
        "permission_on": bool(permission_on),
        "rotation_dead": bool(rotation_dead),
        "thresholds": {"up3_on": UP3_ON, "up3_boost": UP3_BOOST, "up3_dead": UP3_DEAD},
        "mode": "permission_v1",
    }


def position_exposure_permission(flags: dict | None, permission: dict | None) -> float:
    """折中仓位：nuclear 极严；有许可则按指数降仓；无许可非 nuclear → 地板 0.25。"""
    f = flags or {}
    p = permission or {}
    crash = bool(f.get("market_crash_day"))
    up3 = int(p.get("up3_count") or 0)
    n_sus = int(p.get("n_sustained_in") or 0)
    permission_on = bool(p.get("permission_on"))
    rotation_dead = bool(p.get("rotation_dead"))
    if not p:
        rotation_dead = n_sus == 0 and up3 < UP3_DEAD

    # 唯一真空仓：瀑布 + 轮动死 + 宽度极差
    if crash and rotation_dead:
        return 0.0

    severe = bool(f.get("market_severe"))
    weak = bool(f.get("market_weak") or f.get("tech_severe"))

    if permission_on:
        if not severe and not weak:
            return 1.0
        if severe:
            return 0.5 if up3 >= UP3_BOOST else 0.25
        # weak / tech_severe
        return 0.5

    # 许可关、但未 nuclear → 仍给薄仓，避免指数误杀
    return 0.25


def enrich_env_with_permission(
    env: dict,
    asof: str | None = None,
    kdf: pd.DataFrame | None = None,
) -> dict:
    """就地写入 permission + 重算 position_exposure。"""
    from market_env_gate import position_exposure_ladder

    asof = str(asof or env.get("asof") or env.get("date") or "")[:10]
    if not asof and env.get("ts"):
        asof = str(env["ts"])[:10]
    if not asof:
        import time

        asof = time.strftime("%Y-%m-%d")

    perm = compute_permission(asof, kdf=kdf)
    flags = dict(env.get("flags") or {})
    flags["permission_on"] = perm["permission_on"]
    flags["rotation_dead"] = perm["rotation_dead"]
    expo = position_exposure_permission(flags, perm)
    env["asof"] = asof
    env["flags"] = flags
    env["permission"] = perm
    env["position_exposure_ladder"] = position_exposure_ladder(flags)
    env["position_exposure"] = expo
    env["exposure_mode"] = "permission_v1"
    return env
