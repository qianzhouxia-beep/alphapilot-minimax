#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
集合竞价板块热点引擎 — 09:26 跑，09:28 前完成。

核心思路：
  - 09:25 集合竞价结束 → 量化机构在 5 分钟内完成板块方向判定
  - 本引擎模拟这个流程：扫全行业代表股竞价信号 → 聚合板块热力 → 资金交叉验证
  - 输出 call_auction_sector_heat.json 供 09:35 live_momentum_scanner 消费

五大聚合维度：
  ① 竞价涨幅均值 (gap_mean) — 板块整体高开/低开
  ② 竞价放量比 (vol_surge)  — 竞价量 vs 近5日均量
  ③ 主力方向 (flow_align)   — 竞价方向 vs 近5日主力净额方向
  ④ 板块一致性 (consensus)  — 板块内正 gap 占比
  ⑤ 板块偏好 (research_bias)— Wind 研报 prefer/avoid

交叉验证来源:
  - wind_board_flow.json   — Wind 板块 5日/20日主力净额
  - fund_flow_history.json — 通达信个股近5日主力净额
  - sector_research_bias.json — 盘前板块研报偏好
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
import numpy as np

ROOT = Path("/home/ubuntu/alphapilot")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

# ── 配置 ──
OUTPUT_PATH = ROOT / "output/call_auction_sector_heat.json"
SECTOR_REPS_PATH = ROOT / "data/sector_representatives.json"
WIND_FLOW_PATH = ROOT / "data/wind_board_flow.json"
FUND_FLOW_PATH = ROOT / "data/fund_flow_history.json"
SECTOR_BIAS_PATH = ROOT / "output/sector_research_bias.json"
INDUSTRY_MAP_PATH = ROOT / "data/stock_industry_map.json"
KLINE_CACHE = ROOT / "data/kline_all.parquet"

TENCENT_API = "https://qt.gtimg.cn/q="
BATCH_SIZE = 80
FETCH_TIMEOUT = 12
TARGET_STOCKS = 4500  # 全市场竞价扫描（实测 1000只=2.2s，4500只≈10s）

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://gu.qq.com/",
}


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ═══════════════════════════════════════════════
# 1. 报价拉取
# ═══════════════════════════════════════════════

def _tencent_prefix(sym: str) -> str:
    if sym.startswith("6"):
        return "sh"
    if sym.startswith(("4", "8", "9")):
        return "bj"
    return "sz"


def _parse_quote(body: str) -> Optional[dict]:
    f = body.split("~")
    if len(f) < 38:
        return None
    try:
        return {
            "price": float(f[3]),
            "prev_close": float(f[4]),
            "open": float(f[5]),
            "volume": float(f[6]),
            "amount_wan": float(f[37]),
            "change_pct": float(f[32]),
        }
    except (ValueError, IndexError):
        return None


def fetch_quotes(symbols: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for i in range(0, len(symbols), BATCH_SIZE):
        chunk = symbols[i:i + BATCH_SIZE]
        secs = [_tencent_prefix(s) + s for s in chunk]
        try:
            r = requests.get(TENCENT_API, params={"q": ",".join(secs)},
                             headers=_HEADERS, timeout=FETCH_TIMEOUT)
            r.raise_for_status()
            for line in r.text.strip().split(";"):
                if not line.strip() or "=" not in line:
                    continue
                sec = line.split("=")[0].replace("v_", "")
                sym = sec[-6:]
                body = line.split('="', 1)[1].rsplit('"', 1)[0]
                d = _parse_quote(body)
                if d and d.get("open", 0) > 0 and d.get("prev_close", 0) > 0:
                    d["symbol"] = sym
                    out[sym] = d
        except Exception as e:
            log(f"  batch fetch [{i // BATCH_SIZE}] error: {e}")
            continue
    return out


# ═══════════════════════════════════════════════
# 2. 选股：行业代表股
# ═══════════════════════════════════════════════

def _bare(sym: str) -> str:
    s = str(sym or "").replace("sh", "").replace("sz", "").replace("bj", "")
    s = s.replace("SH", "").replace("SZ", "").replace("BJ", "")
    return s[-6:] if len(s) >= 6 else s


def load_industry_map() -> dict:
    if not INDUSTRY_MAP_PATH.exists():
        return {}
    try:
        return json.loads(INDUSTRY_MAP_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def select_representatives(industry_map: dict, max_per_sector: int = 5) -> list[str]:
    """
    从全市场中每个行业选 top-N 代表性个股。
    优先选：市值大 + 成交活跃 + 非ST。
    当 TARGET_STOCKS >= len(industry_map) 时，返回全市场。
    """
    if TARGET_STOCKS >= len(industry_map):
        return list(industry_map.keys())[:TARGET_STOCKS]

    sector_pool: dict[str, list[str]] = defaultdict(list)
    for code, imap in industry_map.items():
        sector = imap.get("industry_l1", "其他")
        if len(sector_pool[sector]) < max_per_sector:
            sector_pool[sector].append(code)

    reps = []
    for sector, codes in sorted(sector_pool.items()):
        reps.extend(codes)
    return reps


# ═══════════════════════════════════════════════
# 3. 板块竞价聚合
# ═══════════════════════════════════════════════

def aggregate_sector_heat(
    quotes: dict[str, dict],
    industry_map: dict,
    fund_flow: dict[str, dict],
    wind_flow: dict,
    sector_bias: dict,
) -> list[dict]:
    """聚合板块竞价热力 + 资金交叉验证 → 排序后的热点板块列表。"""

    # ── 3a. 个股竞价信号 ──
    stock_signals: dict[str, dict] = {}
    for sym, q in quotes.items():
        open_px = q.get("open", 0)
        prev = q.get("prev_close", 1)
        gap_pct = ((open_px / prev) - 1) * 100 if prev > 0 else 0
        stock_signals[sym] = {
            "gap_pct": round(gap_pct, 2),
            "volume": q.get("volume", 0),
            "amount_wan": q.get("amount_wan", 0),
        }

    # ── 3b. 按板块聚合 ──
    sector_data: dict[str, dict] = defaultdict(lambda: {
        "gaps": [], "volumes": [], "amounts": [], "symbols": [],
        "fund_5d_net": [], "fund_5d_count": 0,
    })

    for sym, sig in stock_signals.items():
        imap = industry_map.get(_bare(sym), {})
        sector = imap.get("industry_l1", "其他")
        sd = sector_data[sector]
        sd["gaps"].append(sig["gap_pct"])
        sd["volumes"].append(sig["volume"])
        sd["amounts"].append(sig["amount_wan"])
        sd["symbols"].append(sym)

        # 资金流交叉验证
        ff = fund_flow.get(sym, {})
        if ff:
            dates = sorted(ff.keys(), reverse=True)
            net_5d = sum(ff.get(d, 0) for d in dates[:5])
            if net_5d != 0:
                sd["fund_5d_net"].append(net_5d)
                sd["fund_5d_count"] += 1

    # ── 3c. 计算板块热力分 ──
    results = []
    for sector, sd in sector_data.items():
        gaps = sd["gaps"]
        if not gaps:
            continue

        gap_mean = float(np.mean(gaps))
        gap_std = float(np.std(gaps)) if len(gaps) > 1 else 0.01
        pos_ratio = sum(1 for g in gaps if g > 0) / len(gaps)

        # 放量比简化计算（竞价量/总报价量的均值）
        vol_mean = float(np.mean(sd["volumes"])) if sd["volumes"] else 0

        # 资金方向对齐分
        fund_align = 0.0
        if sd["fund_5d_net"]:
            fund_mean_5d = float(np.mean(sd["fund_5d_net"]))
            # 同向加分：竞价方向与近5日资金方向一致
            if gap_mean > 0 and fund_mean_5d > 0:
                fund_align = 1.0  # 共振
            elif gap_mean < 0 and fund_mean_5d < 0:
                fund_align = -1.0  # 同向下跌
            elif gap_mean > 0 and fund_mean_5d < 0:
                fund_align = -0.5  # 竞价强但资金弱 → 诱多嫌疑

        # Wind 板块流交叉
        wind_score = 0.0
        if wind_flow:
            for entry in (wind_flow if isinstance(wind_flow, list) else wind_flow.values()):
                if isinstance(entry, dict) and entry.get("sector", "") == sector:
                    net_5d = entry.get("net_5d", 0)
                    net_20d = entry.get("net_20d", 0)
                    if net_5d > 0:
                        wind_score += 0.5
                    if net_20d > 0:
                        wind_score += 0.3
                    break

        # 板块偏好加减分
        bias_score = 0.0
        if sector_bias:
            prefer = sector_bias.get("prefer", [])
            avoid = sector_bias.get("avoid", [])
            if sector in prefer:
                bias_score = 0.3
            elif sector in avoid:
                bias_score = -0.3

        # │ 综合热力分
        heat = (
            gap_mean * 0.25          # 竞价涨幅
            + pos_ratio * 0.20       # 板块一致性
            + fund_align * 0.25       # 资金方向对齐
            + wind_score * 0.15       # Wind 板块流确认
            + bias_score * 0.15       # 研报偏好
        )

        results.append({
            "sector": sector,
            "n_stocks": len(gaps),
            "gap_mean": round(gap_mean, 2),
            "gap_std": round(gap_std, 2),
            "pos_ratio": round(pos_ratio, 2),
            "fund_align": round(fund_align, 2),
            "wind_score": round(wind_score, 2),
            "bias_score": round(bias_score, 2),
            "heat_score": round(heat, 2),
            "top_symbols": sd["symbols"][:5],
            "fund_5d_covered": sd["fund_5d_count"],
        })

    # ── 3d. 排序 ──
    results.sort(key=lambda x: -x["heat_score"])

    return results


# ═══════════════════════════════════════════════
# 4. 资金流数据加载
# ═══════════════════════════════════════════════

def load_fund_flow() -> dict[str, dict]:
    if not FUND_FLOW_PATH.exists():
        return {}
    try:
        return json.loads(FUND_FLOW_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_wind_flow() -> dict:
    if not WIND_FLOW_PATH.exists():
        return {}
    try:
        return json.loads(WIND_FLOW_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_sector_bias() -> dict:
    if not SECTOR_BIAS_PATH.exists():
        return {"prefer": [], "avoid": []}
    try:
        return json.loads(SECTOR_BIAS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"prefer": [], "avoid": []}


# ═══════════════════════════════════════════════
# 5. 主入口
# ═══════════════════════════════════════════════

def main() -> int:
    t0 = time.time()
    log("集合竞价板块热点引擎启动")

    # 1. 加载行业映射 + 选代表股
    industry_map = load_industry_map()
    if not industry_map:
        log("[ERROR] 无行业映射数据")
        return 1

    reps = select_representatives(industry_map, max_per_sector=5)
    reps = reps[:TARGET_STOCKS]
    log(f"行业代表股: {len(reps)} 只")

    # 2. 拉取集合竞价行情
    t_fetch = time.time()
    quotes = fetch_quotes(reps)
    log(f"行情拉取: {len(quotes)}/{len(reps)} 只有效, 耗时 {time.time()-t_fetch:.1f}s")

    if len(quotes) < 30:
        log("[ERROR] 有效行情不足 30 只，可能集合竞价尚未完成")
        return 2

    # 3. 加载交叉验证数据
    fund_flow = load_fund_flow()
    wind_flow = load_wind_flow()
    sector_bias = load_sector_bias()
    log(f"资金流: {len(fund_flow)} 只 / Wind板块: {len(wind_flow) if isinstance(wind_flow,list) else len(wind_flow.values())} / 研报偏好: {len(sector_bias.get('prefer',[]))} prefer")

    # 4. 板块聚合 + 热力计算
    t_calc = time.time()
    results = aggregate_sector_heat(quotes, industry_map, fund_flow, wind_flow, sector_bias)
    log(f"板块聚合: {len(results)} 个板块, 耗时 {time.time()-t_calc:.1f}s")

    # 5. 输出
    hot = [r for r in results if r["heat_score"] > 0]
    cold = [r for r in results if r["heat_score"] <= 0]

    output = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "n_sectors": len(results),
        "n_stocks_checked": len(quotes),
        "elapsed_s": round(time.time() - t0, 1),
        "hot_sectors": [
            {k: v for k, v in r.items() if k != "top_symbols"}
            for r in hot[:8]
        ],
        "hot_sectors_detail": hot[:5],
        "cold_sectors": [
            {"sector": r["sector"], "heat_score": r["heat_score"],
             "gap_mean": r["gap_mean"], "pos_ratio": r["pos_ratio"]}
            for r in cold[:5]
        ],
        "all_sectors": results,
    }

    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    # 6. 打印摘要
    log("=" * 60)
    log("🔥 竞价热点方向（Top8）:")
    for i, r in enumerate(hot[:8]):
        tags = []
        if r["fund_align"] > 0.5:
            tags.append("资金共振")
        if r["wind_score"] > 0.5:
            tags.append("Wind确认")
        if r["bias_score"] > 0:
            tags.append("研报推荐")
        tag_str = " | ".join(tags) if tags else "—"
        log(f"  #{i+1} {r['sector']:12s} 热度={r['heat_score']:+.2f}  "
            f"gap={r['gap_mean']:+.1f}% 一致性={r['pos_ratio']:.0%}  "
            f"({tag_str})")

    if cold:
        log(f"\n❄️ 竞价冷门: {', '.join(r['sector'] for r in cold[:5])}")

    log(f"\n输出: {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size} bytes) 总耗时 {time.time()-t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
