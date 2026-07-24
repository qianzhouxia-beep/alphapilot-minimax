#!/usr/bin/env python3
"""
尾盘选股策略引擎 — S2最优版
调度：工作日 14:45（crontab）→ 距 15:00 收盘约 15 分钟下单窗口
基于「尾盘 8 步法」文档对齐 + 策略一量比加强

核心逻辑（S2最优版）：
  1. 涨幅 +3% ~ +5%           ← 性价比区间（文档）
  2. 量比 > 1.5               ← S1 加强（文档为 >1）
  3. 换手率 5% ~ 10%          ← 文档
  4. 流通市值 50 ~ 200 亿     ← 文档
  5. 均线多头排列              ← close > MA5 > MA10 > MA20
  6. 站上均价线                ← close >= VWAP
  7. 入场节奏：14:30 后创日内新高，回踩分时均价不破
  8. 20日波动率(+筹码)排序选Top

输出: output/eod_s2_picks.json
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from data_fetcher import get_stock_list
from enriched_data import get_quotes_batch

OUTPUT_FILE = "output/eod_s2_picks.json"
KLINE_CACHE = "data/kline_cache/kline_all.parquet"
MIN_CACHE = Path("data/minute_cache_tdx")

# ── 可环境变量覆盖的硬筛参数 ──
CHG_MIN = float(os.environ.get("EOD_S2_CHG_MIN", "3") or 3)
CHG_MAX = float(os.environ.get("EOD_S2_CHG_MAX", "5") or 5)
TURN_MIN = float(os.environ.get("EOD_S2_TURN_MIN", "5") or 5)
TURN_MAX = float(os.environ.get("EOD_S2_TURN_MAX", "10") or 10)
CIRC_MV_MIN = float(os.environ.get("EOD_S2_CIRC_MV_MIN", "50") or 50)  # 亿
CIRC_MV_MAX = float(os.environ.get("EOD_S2_CIRC_MV_MAX", "200") or 200)
VOL_RATIO_MIN = float(os.environ.get("EOD_S2_VOL_RATIO_MIN", "1.5") or 1.5)
# 回踩：现价相对 VWAP 上方不超过该比例（更大则未真正回踩）
VWAP_PULLBACK_MAX = float(os.environ.get("EOD_S2_VWAP_PULLBACK_MAX", "0.02") or 0.02)
# 不破均价：允许极小浮点误差
VWAP_BREAK_TOL = float(os.environ.get("EOD_S2_VWAP_BREAK_TOL", "0.001") or 0.001)
# 无分钟线时：相对日内高点至少回撤一点才算「回踩」
MIN_PULLBACK_FROM_HIGH = float(os.environ.get("EOD_S2_MIN_PULLBACK_FROM_HIGH", "0.002") or 0.002)

# 通达信 1 分钟：09:30-11:30(120) + 13:00-15:00(120)；14:30 = 120+90
IDX_1430 = 210

_CHIP_DATA = None
_tdx_quotes = None


def _load_chip_data():
    global _CHIP_DATA
    if _CHIP_DATA is not None:
        return _CHIP_DATA
    try:
        with open("chip_data_all.json", encoding="utf-8") as f:
            _CHIP_DATA = {
                k.split(".")[0] if "." in k else k: v for k, v in json.load(f).items()
            }
    except Exception:
        _CHIP_DATA = {}
    return _CHIP_DATA


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def calc_volatility(df: pd.DataFrame, period: int = 20) -> float:
    if df is None or len(df) < period:
        return 0.0
    returns = df["close"].pct_change().dropna().tail(period)
    return float(returns.std()) if len(returns) >= period else 0.0


def check_bullish_ma_live(df: pd.DataFrame, live_close: float) -> bool:
    """均线多头：用历史收盘算 MA，现价替代今日 close"""
    if df is None or len(df) < 20 or not live_close:
        return False
    closes = df["close"].astype(float).tolist()
    last_date = str(df["date"].iloc[-1])[:10]
    today = datetime.now().strftime("%Y-%m-%d")
    if last_date == today:
        closes[-1] = float(live_close)
    else:
        closes.append(float(live_close))
    if len(closes) < 20:
        return False
    close = closes[-1]
    ma5 = float(np.mean(closes[-5:]))
    ma10 = float(np.mean(closes[-10:]))
    ma20 = float(np.mean(closes[-20:]))
    return close > ma5 > ma10 > ma20


def _tdx_client():
    global _tdx_quotes
    if _tdx_quotes is None:
        from mootdx.quotes import Quotes

        _tdx_quotes = Quotes.factory(market="std")
    return _tdx_quotes


def fetch_minutes_today(symbol: str) -> pd.DataFrame | None:
    """通达信当日 1 分钟；失败则返回 None（走行情兜底）。"""
    ymd = datetime.now().strftime("%Y%m%d")
    MIN_CACHE.mkdir(parents=True, exist_ok=True)
    path = MIN_CACHE / f"{symbol}_{ymd}.parquet"
    # 盘中缓存最多复用 60s，避免反复打通达信
    if path.exists() and (time.time() - path.stat().st_mtime) < 60:
        try:
            return pd.read_parquet(path)
        except Exception:
            pass
    try:
        df = _tdx_client().minutes(symbol=symbol, date=ymd)
        if df is None or len(df) < 30:
            return None
        df = df.reset_index(drop=True)
        try:
            df.to_parquet(path, index=False)
        except Exception:
            pass
        return df
    except Exception:
        return None


def _minute_prices(mdf: pd.DataFrame) -> list[float]:
    col = "price" if "price" in mdf.columns else ("close" if "close" in mdf.columns else None)
    if not col:
        return []
    out = []
    for v in mdf[col].tolist():
        try:
            p = float(v)
            if p > 0:
                out.append(p)
        except (TypeError, ValueError):
            continue
    return out


def check_pullback_vwap_entry(
    high: float,
    price: float,
    vwap: float,
    minute_df: pd.DataFrame | None = None,
) -> tuple[bool, str]:
    """
    入场节奏：14:30 后创出日内新高，回踩分时均价线不破。
    有分钟线则严格判定；否则用盘口高/现价/VWAP 做兜底近似。
    """
    if not high or high <= 0 or not price or not vwap or vwap <= 0:
        return False, "bad_inputs"
    if price < vwap * (1.0 - VWAP_BREAK_TOL):
        return False, "broke_vwap"

    prices = _minute_prices(minute_df) if minute_df is not None else []
    if len(prices) > IDX_1430:
        pre = prices[:IDX_1430]
        post = prices[IDX_1430:]
        pre_hi = max(pre) if pre else 0.0
        post_hi = max(post) if post else 0.0
        if post_hi < pre_hi * (1.0 - 1e-9):
            return False, "no_new_high_after_1430"

        # 14:30 后第一次创出（或平）全日高点的位置
        run_hi = pre_hi
        first_nh = None
        for i, p in enumerate(post):
            if p >= run_hi:
                run_hi = p
                first_nh = i
        if first_nh is None:
            return False, "no_new_high_bar"

        # 新高之后出现回踩到均价附近（现价仍不破）
        after = post[first_nh:]
        near = False
        for p in after:
            if p < vwap * (1.0 - VWAP_BREAK_TOL):
                return False, "broke_vwap_after_high"
            if 0 <= (p - vwap) / vwap <= VWAP_PULLBACK_MAX:
                near = True
        if not near and not (0 <= (price - vwap) / vwap <= VWAP_PULLBACK_MAX):
            return False, "no_pullback_to_vwap"
        if not (0 <= (price - vwap) / vwap <= VWAP_PULLBACK_MAX * 1.25):
            # 现价仍需贴近均价（略放宽）
            return False, "price_not_near_vwap"
        return True, "minute_pullback"

    # ── 行情兜底（无分钟 / 未到足够 bar）──
    if high < vwap:
        return False, "high_below_vwap"
    dist_vwap = (price - vwap) / vwap
    if dist_vwap > VWAP_PULLBACK_MAX:
        return False, "not_near_vwap"
    if dist_vwap < -VWAP_BREAK_TOL:
        return False, "broke_vwap"
    pullback = (high - price) / high
    if pullback < MIN_PULLBACK_FROM_HIGH and dist_vwap > 0.005:
        return False, "no_pullback_from_high"
    # 无分钟无法验证「14:30后新高」，仅作弱通过并打标
    return True, "quote_proxy_pullback"


def main():
    log("=" * 60)
    log("尾盘 S2最优版 策略引擎")
    log(
        f"参数: 涨幅[{CHG_MIN},{CHG_MAX}] 换手[{TURN_MIN},{TURN_MAX}] "
        f"流通市值[{CIRC_MV_MIN},{CIRC_MV_MAX}]亿 量比>{VOL_RATIO_MIN} +回踩均价"
    )
    log("=" * 60)

    stocks = get_stock_list()
    all_symbols = [str(s).zfill(6) for s in stocks["symbol"].tolist()]
    log(f"全市场: {len(all_symbols)} 只")

    kline_cache = {}
    if os.path.isfile(KLINE_CACHE):
        try:
            t0 = time.time()
            kdf = pd.read_parquet(KLINE_CACHE)
            kdf["symbol"] = (
                kdf["symbol"]
                .astype(str)
                .str.replace(r"^(sh|sz|bj)", "", regex=True)
                .str[-6:]
            )
            for sym, sdf in kdf.groupby("symbol", sort=False):
                sdf = sdf.sort_values("date")
                if len(sdf) >= 20:
                    kline_cache[sym] = sdf
            log(f"K线缓存: {len(kline_cache)} 只 ({time.time()-t0:.1f}s)")
        except Exception as e:
            log(f"  ⚠️ 缓存加载失败: {e}")

    t1 = time.time()
    quotes = get_quotes_batch(all_symbols, batch=80)
    log(f"批量行情: {len(quotes)}/{len(all_symbols)} ({time.time()-t1:.1f}s)")

    candidates = []
    chip_all = _load_chip_data()
    n_fail = {
        "chg": 0,
        "vr": 0,
        "turn": 0,
        "circ": 0,
        "ma": 0,
        "vwap": 0,
        "entry": 0,
        "nok": 0,
    }

    for i, symbol in enumerate(all_symbols):
        if i % 1000 == 0 and i > 0:
            log(f"  进度: {i}/{len(all_symbols)} 候选={len(candidates)}")
        try:
            quote = quotes.get(symbol)
            if not quote:
                n_fail["nok"] += 1
                continue

            price = float(quote.get("price", 0) or 0)
            change_pct = float(quote.get("change_pct", 0) or 0)
            volume_ratio = float(quote.get("volume_ratio", 0) or 0)
            high = float(quote.get("high", 0) or 0)
            low = float(quote.get("low", 0) or 0)
            volume = float(quote.get("volume", 0) or 0)
            amount = float(quote.get("amount", 0) or 0)
            turnover = float(quote.get("turnover", 0) or 0)
            circ_mv = float(
                quote.get("circ_mv")
                or quote.get("total_mv")
                or 0
            )
            name = quote.get("name", "")

            if change_pct < CHG_MIN or change_pct > CHG_MAX:
                n_fail["chg"] += 1
                continue
            if volume_ratio < VOL_RATIO_MIN:
                n_fail["vr"] += 1
                continue
            if turnover < TURN_MIN or turnover > TURN_MAX:
                n_fail["turn"] += 1
                continue
            if circ_mv < CIRC_MV_MIN or circ_mv > CIRC_MV_MAX:
                n_fail["circ"] += 1
                continue

            df = kline_cache.get(symbol)
            if df is None or len(df) < 20:
                n_fail["nok"] += 1
                continue
            if not check_bullish_ma_live(df, price):
                n_fail["ma"] += 1
                continue

            vol_shares = volume * 100.0
            vwap = (
                amount / vol_shares
                if vol_shares > 0 and amount > 0
                else (high + low + price) / 3
            )
            if price < vwap * (1.0 - VWAP_BREAK_TOL):
                n_fail["vwap"] += 1
                continue

            # 入场节奏：仅对通过硬筛的标的拉分钟（控制通达信压力）
            mdf = fetch_minutes_today(symbol)
            ok_entry, entry_tag = check_pullback_vwap_entry(high, price, vwap, mdf)
            if not ok_entry:
                n_fail["entry"] += 1
                continue

            vol20 = calc_volatility(df)

            chip_bonus = 0.0
            chip = chip_all.get(symbol)
            if chip:
                penetration = (
                    float(chip.get("chipPenetration", 0))
                    if "chipPenetration" in chip
                    else float(chip.get("chip_penetration", 0) or 0)
                )
                if penetration > 0.05:
                    chip_bonus += 1.5
                cost_shift = float(chip.get("avgCostShift5d", 0) or 0)
                if cost_shift > 0.01:
                    chip_bonus += 1.0
                profit_rate = float(chip.get("chipProfitRate", 0) or 0)
                if profit_rate > 40:
                    chip_bonus += 0.5

            candidates.append(
                {
                    "symbol": symbol,
                    "name": name,
                    "price": price,
                    "change_pct": change_pct,
                    "volume_ratio": volume_ratio,
                    "turnover": turnover,
                    "circ_mv": round(circ_mv, 2),
                    "volatility_20d": vol20,
                    "close_vs_high": (high - price) / high if high > 0 else 100,
                    "vwap": round(vwap, 4),
                    "entry_tag": entry_tag,
                    "chip_bonus": chip_bonus,
                }
            )
        except Exception:
            continue

    log(f"筛选完成: {len(candidates)} 只通过  漏斗={n_fail}")

    if candidates:
        candidates.sort(
            key=lambda x: x["volatility_20d"] + x.get("chip_bonus", 0), reverse=True
        )
        top = candidates[:5]
    else:
        top = []

    output = {
        "generated_at": datetime.now().isoformat(),
        "generated_time": datetime.now().strftime("%H:%M"),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "total_screened": len(all_symbols),
        "total_passed": len(candidates),
        "strategy": "S2最优版",
        "params": {
            "change_pct": [CHG_MIN, CHG_MAX],
            "turnover": [TURN_MIN, TURN_MAX],
            "circ_mv_yi": [CIRC_MV_MIN, CIRC_MV_MAX],
            "volume_ratio_min": VOL_RATIO_MIN,
            "entry": "post_1430_new_high_pullback_vwap",
        },
        "funnel_drop": n_fail,
        "picks": top,
        "note": (
            "涨幅3~5+换手5~10+流通50~200亿+回踩均价；按20日波动率排序"
            if top
            else "今日无符合条件的信号"
        ),
    }

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)

    try:
        from eod_s2_history import save_history

        hist_path = save_history(output)
        log(f"📚 历史归档: {hist_path}")
    except Exception as e:
        log(f"  ⚠️ 历史归档失败: {e}")

    if top:
        log("\n🏆 S2最优版 Top5:")
        for i, c in enumerate(top[:5]):
            log(
                f"  {i+1}. {c['name']} ({c['symbol']}) 涨跌={c['change_pct']:+.2f}% "
                f"换手={c['turnover']:.1f}% 流通={c['circ_mv']:.0f}亿 "
                f"量比={c['volume_ratio']:.1f} 入场={c.get('entry_tag')}"
            )
        log(f"\n✅ Top1: {top[0]['name']} ({top[0]['symbol']})")
    else:
        log("❌ 今日无符合 S2最优版 条件的标的")

    log(f"✅ 结果保存: {OUTPUT_FILE}")

    # ── 写入 Paper Trading 信号 ──
    PT_PATH = "data/paper_trading.json"
    if os.path.exists(PT_PATH) and top:
        with open(PT_PATH, encoding="utf-8") as f:
            pt = json.load(f)
        c = top[0]
        price = c["price"]
        signal = {
            "symbol": c["symbol"],
            "name": c["name"],
            "score": c["volatility_20d"] + c.get("chip_bonus", 0),
            "action": "buy",
            "price": price,
            "target_price": round(price * 1.05, 2),
            "stop_price": round(price * 0.97, 2),
            "quantity": 0,
            "strategy_id": "s2_eod",
            "reason": f"S2尾盘狙击（全仓|{c.get('entry_tag','')})",
            "entry_mode": "eod_full",
        }
        existing = set()
        for s in pt.get("strategies", []):
            for p in s.get("positions", []):
                existing.add(p.get("symbol", ""))
        if c["symbol"] not in existing:
            found_s2 = False
            equity = float(pt.get("account", {}).get("cash", 0) or 0) + float(
                pt.get("account", {}).get("market_value", 0) or 0
            )
            if equity <= 0:
                equity = float(pt.get("initial_capital") or 1000000.0)
            # 默认共用资金：allocated=总权益；仅 SHARED_CAPITAL=0 时各锁 50%
            shared = str(os.environ.get("SHARED_CAPITAL", "1")).strip().lower() in (
                "1", "true", "yes", "on",
            )
            eod_alloc = round(equity if shared else equity * 0.50, 2)
            daily_alloc = round(equity if shared else equity * 0.50, 2)
            for s in pt["strategies"]:
                if s["id"] == "s2_eod":
                    s["signals"] = [signal]
                    s["allocated"] = eod_alloc
                    s["capital_mode"] = "shared" if shared else "split"
                    s["name"] = "尾盘狙击"
                    found_s2 = True
                    break
            if not found_s2:
                pt["strategies"].append(
                    {
                        "id": "s2_eod",
                        "name": "尾盘狙击",
                        "status": "active",
                        "allocated": eod_alloc,
                        "capital_mode": "shared" if shared else "split",
                        "used": 0,
                        "signals": [signal],
                        "positions": [],
                    }
                )
            for s in pt["strategies"]:
                if s.get("id") == "v19_daily":
                    s["allocated"] = daily_alloc
                    s["capital_mode"] = "shared" if shared else "split"
            with open(PT_PATH, "w", encoding="utf-8") as f:
                json.dump(pt, f, ensure_ascii=False, indent=2)
            log("  ✅ S2 Top1 已写入 Paper Trading（尾盘全仓）")


if __name__ == "__main__":
    main()
