#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""个股上涨趋势首选 + 分层阀门（防错杀）。

阀门分层（默认）：
  硬踢（只杀明确不买的结构）：
    - 完整下跌通道 / 非上升破位（价破 MA20 + 短均线空头）
  软门槛（加分 + 排序优先，不删票）：
    - 收盘站上 MA25
    - 成交量 MA5 > 成交量 MA60
    - ma5>ma20 / ma20>ma60 / 站上 MA60 / MACD / trend_resume

Env:
  ENABLE_TREND_PREFER=1
  TREND_PREFER_SORT_FIRST=1
  ENABLE_DOWNTREND_FILTER=1       硬踢破位下行，默认开
  DOWNTREND_FILTER_MODE=drop      drop|demote
  MA25_VOL_MODE=soft              soft=加分优先（默认）| hard=硬踢 | off=关闭
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent


def _env_on(name: str, default: bool = True) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def enabled() -> bool:
    return _env_on("ENABLE_TREND_PREFER", True)


def _bare(sym: str) -> str:
    s = str(sym or "").lower().replace("sh", "").replace("sz", "").replace("bj", "")
    return s[-6:] if len(s) >= 6 else s


def _ma25_vol_mode() -> str:
    """soft（默认）| hard | off。兼容旧 ENABLE_MA25_VOL_BASELINE。"""
    raw = (os.environ.get("MA25_VOL_MODE") or "").strip().lower()
    if raw in ("soft", "hard", "off"):
        return raw
    if os.environ.get("ENABLE_MA25_VOL_BASELINE") is not None:
        return "soft" if _env_on("ENABLE_MA25_VOL_BASELINE", True) else "off"
    return "soft"


_KLINE_CACHE: pd.DataFrame | None = None

def _load_kline() -> pd.DataFrame | None:
    global _KLINE_CACHE
    if _KLINE_CACHE is not None:
        return _KLINE_CACHE
    for p in (ROOT / "data/kline_cache/kline_all.parquet", ROOT / "kline_all.parquet"):
        if p.exists():
            try:
                df = pd.read_parquet(p)
                df["date"] = df["date"].astype(str).str[:10]
                df["symbol"] = (
                    df["symbol"].astype(str).str.replace(r"^(sh|sz|bj)", "", regex=True).str[-6:]
                )
                _KLINE_CACHE = df
                return df
            except Exception:
                continue
    return None


def calc_trend_flags(stock: pd.DataFrame) -> dict[str, Any] | None:
    """用日 K 计算趋势标志。失败返回 None。"""
    if stock is None or len(stock) < 60:
        return None
    s = stock.sort_values("date")
    close = s["close"].astype(float)
    if len(close) < 60 or float(close.iloc[-1]) <= 0:
        return None
    vol_col = "volume" if "volume" in s.columns else ("vol" if "vol" in s.columns else None)
    volume = s[vol_col].astype(float) if vol_col else None

    ma5 = float(close.tail(5).mean())
    ma20 = float(close.tail(20).mean())
    ma25 = float(close.tail(25).mean())
    ma60 = float(close.tail(60).mean())
    c = float(close.iloc[-1])
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = float((ema12 - ema26).iloc[-1])
    dea = float((ema12 - ema26).ewm(span=9, adjust=False).mean().iloc[-1])
    hist = (dif - dea) * 2.0

    ma5_gt_ma20 = ma5 > ma20
    ma20_gt_ma60 = ma20 > ma60
    price_above_ma60 = c > ma60
    price_above_ma25 = c > ma25
    price_below_ma20 = c < ma20
    macd_bull = dif > 0
    macd_hist_pos = hist > 0

    vol_ma5 = vol_ma60 = None
    vol_ma5_gt_vol_ma60 = False
    if volume is not None and len(volume) >= 60:
        vol_ma5 = float(volume.tail(5).mean())
        vol_ma60 = float(volume.tail(60).mean())
        vol_ma5_gt_vol_ma60 = vol_ma60 > 0 and vol_ma5 > vol_ma60

    baseline_pass = bool(price_above_ma25 and vol_ma5_gt_vol_ma60)

    ma_bearish_stack = (not ma5_gt_ma20) and (not ma20_gt_ma60) and (not price_above_ma60)
    downtrend_channel = bool(ma_bearish_stack and price_below_ma20)
    not_uptrend_channel = bool(
        (not ma5_gt_ma20) and price_below_ma20 and (not price_above_ma60)
    )
    channel_reject = bool(downtrend_channel or not_uptrend_channel)

    return {
        "ma5": round(ma5, 4),
        "ma20": round(ma20, 4),
        "ma25": round(ma25, 4),
        "ma60": round(ma60, 4),
        "close": round(c, 4),
        "ma5_gt_ma20": ma5_gt_ma20,
        "ma20_gt_ma60": ma20_gt_ma60,
        "price_above_ma60": price_above_ma60,
        "price_above_ma25": price_above_ma25,
        "price_below_ma20": price_below_ma20,
        "vol_ma5": round(vol_ma5, 2) if vol_ma5 is not None else None,
        "vol_ma60": round(vol_ma60, 2) if vol_ma60 is not None else None,
        "vol_ma5_gt_vol_ma60": vol_ma5_gt_vol_ma60,
        "baseline_pass": baseline_pass,
        "macd_dif": round(dif, 6),
        "macd_hist": round(hist, 6),
        "macd_bull": macd_bull,
        "macd_hist_pos": macd_hist_pos,
        "ma_bullish_stack": bool(ma5_gt_ma20 and ma20_gt_ma60 and price_above_ma60 and c > ma5),
        "ma_bearish_stack": ma_bearish_stack,
        "downtrend_channel": downtrend_channel,
        "not_uptrend_channel": not_uptrend_channel,
        "channel_reject": channel_reject,
    }


def _boost_weights() -> dict[str, float]:
    return {
        "ma5_gt_ma20": float(os.environ.get("TREND_BOOST_MA5_MA20", "0.03") or 0.03),
        "ma20_gt_ma60": float(os.environ.get("TREND_BOOST_MA20_MA60", "0.03") or 0.03),
        "price_above_ma60": float(os.environ.get("TREND_BOOST_ABOVE_MA60", "0.02") or 0.02),
        "price_above_ma25": float(os.environ.get("TREND_BOOST_ABOVE_MA25", "0.03") or 0.03),
        "vol_ma5_gt_vol_ma60": float(os.environ.get("TREND_BOOST_VOL_MA", "0.03") or 0.03),
        "baseline_pass": float(os.environ.get("TREND_BOOST_BASELINE", "0.04") or 0.04),
        "macd_bull": float(os.environ.get("TREND_BOOST_MACD", "0.02") or 0.02),
        "macd_hist_pos": float(os.environ.get("TREND_BOOST_MACD_HIST", "0.01") or 0.01),
        "full_stack": float(os.environ.get("TREND_BOOST_FULL_STACK", "0.04") or 0.04),
        "trend_resume": float(os.environ.get("TREND_BOOST_RESUME", "0.05") or 0.05),
        "downtrend_penalty": float(os.environ.get("TREND_PENALTY_DOWNTREND", "0.25") or 0.25),
        "baseline_miss_penalty": float(os.environ.get("TREND_PENALTY_BASELINE_MISS", "0.04") or 0.04),
    }


def _downtrend_filter_on() -> bool:
    return _env_on("ENABLE_DOWNTREND_FILTER", True)


def _downtrend_mode() -> str:
    v = (os.environ.get("DOWNTREND_FILTER_MODE") or "drop").strip().lower()
    return v if v in ("drop", "demote") else "drop"


def apply_trend_prefer_boost(
    items: list[dict[str, Any]],
    *,
    max_stocks: int = 200,
) -> list[dict[str, Any]]:
    """分层阀门：破位硬踢；MA25+量能默认软优先，避免错杀。"""
    if not items or not enabled():
        if items and not enabled():
            print("  trend_prefer: OFF (ENABLE_TREND_PREFER=0)", flush=True)
        return items

    kdf = _load_kline()
    if kdf is None:
        print("  trend_prefer: no kline cache, skip", flush=True)
        return items

    w = _boost_weights()
    ranked = sorted(items, key=lambda x: -float(x.get("score") or 0))
    focus = ranked[:max_stocks]
    focus_codes = {_bare(x.get("symbol")) for x in focus if _bare(x.get("symbol"))}

    flag_map: dict[str, dict[str, Any]] = {}
    for code in focus_codes:
        g = kdf[kdf["symbol"] == code]
        if g.empty:
            continue
        flags = calc_trend_flags(g)
        if flags:
            flag_map[code] = flags

    if not flag_map:
        print("  trend_prefer: no flags computed, skip", flush=True)
        return items

    prefer_n = 0
    baseline_n = 0
    boosted = 0
    dropped = 0
    demoted = 0
    drop_names: list[str] = []
    channel_on = _downtrend_filter_on()
    baseline_mode = _ma25_vol_mode()
    filt_mode = _downtrend_mode()
    out: list[dict[str, Any]] = []

    for r in items:
        nr = dict(r)
        code = _bare(r.get("symbol"))
        flags = flag_map.get(code)
        pats = r.get("launch_patterns") or []
        if isinstance(pats, str):
            pats = [pats]
        has_resume = "trend_resume" in set(pats or [])

        channel_reject = bool(flags and flags.get("channel_reject"))
        baseline_pass = bool(flags and flags.get("baseline_pass"))
        baseline_reject = bool(flags and not baseline_pass)

        hard_reject = bool(channel_reject and channel_on)
        if baseline_mode == "hard" and baseline_reject:
            hard_reject = True

        nr["downtrend_channel"] = bool(flags and flags.get("downtrend_channel"))
        nr["not_uptrend_channel"] = bool(flags and flags.get("not_uptrend_channel"))
        nr["baseline_pass"] = baseline_pass
        nr["price_above_ma25"] = bool(flags and flags.get("price_above_ma25"))
        nr["vol_ma5_gt_vol_ma60"] = bool(flags and flags.get("vol_ma5_gt_vol_ma60"))
        nr["trend_reject"] = hard_reject

        if hard_reject and filt_mode == "drop":
            dropped += 1
            drop_names.append(str(nr.get("name") or code))
            continue

        delta = 0.0
        hit: list[str] = []
        if flags:
            for key in (
                "ma5_gt_ma20",
                "ma20_gt_ma60",
                "price_above_ma60",
                "price_above_ma25",
                "vol_ma5_gt_vol_ma60",
                "macd_bull",
                "macd_hist_pos",
            ):
                if flags.get(key):
                    delta += w.get(key, 0.0)
                    hit.append(key)
            if flags.get("ma_bullish_stack"):
                delta += w["full_stack"]
                hit.append("full_stack")
            if baseline_pass and baseline_mode != "off":
                delta += w["baseline_pass"]
                hit.append("baseline_pass")
                baseline_n += 1
            elif baseline_mode == "soft" and baseline_reject:
                delta -= w["baseline_miss_penalty"]
                hit.append("baseline_miss")

            feats = dict(nr.get("features") or {})
            feats["ma5_gt_ma20"] = 1.0 if flags.get("ma5_gt_ma20") else 0.0
            feats["ma20_gt_ma60"] = 1.0 if flags.get("ma20_gt_ma60") else 0.0
            feats["price_above_ma60"] = 1.0 if flags.get("price_above_ma60") else 0.0
            feats["price_above_ma25"] = 1.0 if flags.get("price_above_ma25") else 0.0
            feats["vol_ma5_gt_vol_ma60"] = 1.0 if flags.get("vol_ma5_gt_vol_ma60") else 0.0
            feats["ma_direction"] = (
                1.0
                if flags.get("ma_bullish_stack")
                else (
                    -1.0
                    if flags.get("ma_bearish_stack") or flags.get("not_uptrend_channel")
                    else 0.0
                )
            )
            feats["macd_dif"] = flags.get("macd_dif")
            nr["features"] = feats
            nr["trend_flags"] = {
                k: flags.get(k)
                for k in (
                    "ma5_gt_ma20",
                    "ma20_gt_ma60",
                    "price_above_ma60",
                    "price_above_ma25",
                    "vol_ma5_gt_vol_ma60",
                    "baseline_pass",
                    "macd_bull",
                    "macd_hist_pos",
                    "ma_bullish_stack",
                    "ma_bearish_stack",
                    "downtrend_channel",
                    "not_uptrend_channel",
                    "channel_reject",
                )
            }

        if has_resume:
            delta += w["trend_resume"]
            hit.append("trend_resume")

        if hard_reject and filt_mode == "demote":
            delta -= w["downtrend_penalty"]
            hit.append("downtrend_penalty")
            demoted += 1
            nr["trend_avoid"] = True
            nr["drop_reason"] = (nr.get("drop_reason") or "") + "|channel_reject"

        prefer_strong = bool(
            flags
            and not hard_reject
            and flags.get("ma5_gt_ma20")
            and flags.get("ma20_gt_ma60")
            and flags.get("price_above_ma60")
        )
        prefer = bool(
            prefer_strong
            or (
                flags
                and not hard_reject
                and flags.get("ma5_gt_ma20")
                and (flags.get("price_above_ma60") or flags.get("ma20_gt_ma60"))
            )
        )
        nr["trend_prefer"] = prefer
        nr["trend_prefer_strong"] = prefer_strong
        nr["trend_prefer_hits"] = hit
        nr["trend_prefer_delta"] = round(delta, 4)

        base = float(nr.get("score") or 0)
        nr["score_pre_trend_prefer"] = round(base, 4)
        if abs(delta) > 1e-9:
            nr["score"] = round(max(0.01, base + delta), 4)
            if delta > 0:
                boosted += 1
        if prefer:
            prefer_n += 1
        out.append(nr)

    sort_first = _env_on("TREND_PREFER_SORT_FIRST", True)
    if sort_first:
        out.sort(
            key=lambda x: (
                1 if x.get("trend_avoid") or x.get("trend_reject") else 0,
                0 if x.get("trend_prefer_strong") else 1,
                0 if x.get("trend_prefer") else 1,
                0 if x.get("baseline_pass") else 1,
                -float(x.get("score") or 0),
            )
        )
    else:
        out.sort(key=lambda x: -float(x.get("score") or 0))

    print(
        f"  trend_prefer: n_flag={len(flag_map)} boosted={boosted} prefer={prefer_n} "
        f"baseline_ok={baseline_n} drop={dropped} demote={demoted} "
        f"ma25_vol={baseline_mode} channel={int(channel_on)} mode={filt_mode}",
        flush=True,
    )
    if drop_names:
        print(f"  trend_prefer hard-dropped: {', '.join(drop_names[:12])}", flush=True)
    return out
