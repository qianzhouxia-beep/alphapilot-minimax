#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
开盘前集合竞价门控 — 09:25 跑，09:30 前完成。

逻辑：
  1. 加载 daily_recommend.json 中 Top~100 只候选
  2. 腾讯批量实时行情 → 提取集合竞价开盘数据 (open, volume, amount)
  3. 计算个股集合竞价信号：跳空 gap、竞价量
  4. 板块聚合：按 industry_l1 汇总竞价 gap → sector 强弱判定
  5. 门控规则（严格）:
     - gap >= +9% 近涨停不推
     - gap < -2%  硬剔除（低开过多）
     - gap < 0 且 所在板块 gap_mean < -1.5% → 硬剔除（双重弱）
     - gap = 0~-2% → 降权
     - 板块集中度: Top20 同板块最多 3 只
  6. 写回 daily_recommend.json（含 pre_market_* 字段）

时间窗口 09:25–09:30：腾讯批量80只请求 ~2秒，重排序 <50ms，绰绰有余。
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter, OrderedDict
from datetime import datetime
from pathlib import Path

import requests
import numpy as np

ROOT = Path("/home/ubuntu/alphapilot")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

REC_PATH = ROOT / "output/daily_recommend.json"
INDUSTRY_MAP_PATH = ROOT / "data/stock_industry_map.json"
CALL_AUCTION_TOP_N = 100       # 只看 Top~100 的集合竞价
GAP_HARD_DROP = -2.0           # gap < -2% 硬剔除（之前 -5% 太松）
GAP_DEMOTE = -0.5              # gap < -0.5% 开始降权
GAP_LIMIT_UP = 9.0             # gap > 9% 视为近涨停不推

# 板块集中度限制
MAX_SAME_SECTOR_IN_TOP10 = 2   # Top10 同板块最多 2 只
MAX_SAME_SECTOR_IN_TOP20 = 3   # Top20 同板块最多 3 只
MAX_SAME_SECTOR_IN_POOL = 5    # 全池最多 5 只
SECTOR_WEAK_THRESHOLD = -1.5   # 板块 gap_mean < -1.5% 视为弱板块

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://gu.qq.com/",
}
_TENCENT = "https://qt.gtimg.cn/q="


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ── 腾讯实时行情 ──

def _tencent_prefix(sym: str) -> str:
    if sym.startswith("6"):
        return "sh"
    if sym.startswith(("4", "8", "9")):
        return "bj"
    return "sz"


def _parse_quote(body: str) -> dict | None:
    """解析腾讯单只行情字符串 → dict（只取集合竞价相关字段）。"""
    f = body.split("~")
    if len(f) < 38:
        return None
    try:
        return {
            "price": float(f[3]),
            "prev_close": float(f[4]),
            "open": float(f[5]),
            "volume": float(f[6]),          # 手
            "amount_wan": float(f[37]),      # 成交额(万)
            "change_pct": float(f[32]),
        }
    except (ValueError, IndexError):
        return None


def fetch_call_auction_quotes(symbols: list[str], batch: int = 80) -> dict:
    """批量获取腾讯实时行情 → {symbol: quote}。"""
    out = {}
    for i in range(0, len(symbols), batch):
        chunk = symbols[i:i + batch]
        secs = [_tencent_prefix(s) + s for s in chunk]
        q = ",".join(secs)

        try:
            r = requests.get(_TENCENT, params={"q": q}, headers=_HEADERS, timeout=12)
            r.raise_for_status()
            for line in r.text.strip().split(";"):
                if not line.strip() or "=" not in line:
                    continue
                sec = line.split("=")[0].replace("v_", "")
                sym = sec[-6:]
                body = line.split('="', 1)[1].rsplit('"', 1)[0]
                d = _parse_quote(body)
                if d:
                    d["symbol"] = sym
                    out[sym] = d
        except Exception as e:
            log(f"  batch fetch error [{i//batch}]: {e}")
    return out


# ── 板块映射 ──

def load_industry_map() -> dict:
    if not INDUSTRY_MAP_PATH.exists():
        return {}
    try:
        return json.loads(INDUSTRY_MAP_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _bare(sym: str) -> str:
    s = str(sym or "").replace("sh", "").replace("sz", "").replace("bj", "")
    s = s.replace("SH", "").replace("SZ", "").replace("BJ", "")
    return s[-6:] if len(s) >= 6 else s


# ── 信号计算 ──

def has_call_auction_data(q: dict) -> bool:
    vol = float(q.get("volume") or 0)
    amount = float(q.get("amount_wan") or 0)
    open_px = float(q.get("open") or 0)
    prev_close = float(q.get("prev_close") or 0)
    return (vol > 0 or amount > 0) and open_px > 0 and prev_close > 0


def compute_stock_signals(q: dict) -> dict:
    """计算个股集合竞价信号。
    返回 gap 信号，不再做分类信号（门控直接在 run 里做）。
    """
    open_px = float(q.get("open") or 0)
    prev_close = float(q.get("prev_close") or 0)
    volume = float(q.get("volume") or 0)
    amount_wan = float(q.get("amount_wan") or 0)

    gap_pct = ((open_px / prev_close) - 1) * 100 if prev_close > 0 else 0.0

    return {
        "gap_pct": round(gap_pct, 2),
        "call_amount_wan": round(amount_wan, 1),
        "call_volume_hand": int(volume),
        "close": q.get("price", 0),
    }


def aggregate_sector_signals(
    quotes: dict, industry_map: dict
) -> dict[str, dict]:
    """按 industry_l1 聚合集合竞价信号 → {sector: {gap_mean, n, neg_ratio, sector_weak}}"""
    sector_gaps: dict[str, list[float]] = {}
    for sym, q in quotes.items():
        imap = industry_map.get(_bare(sym), {})
        sector = imap.get("industry_l1", "其他")
        gap = q.get("gap_pct", 0)
        sector_gaps.setdefault(sector, []).append(gap)

    result = {}
    for sector, gaps in sector_gaps.items():
        gap_mean = float(np.mean(gaps)) if gaps else 0.0
        neg_ratio = sum(1 for g in gaps if g < 0) / max(len(gaps), 1)
        result[sector] = {
            "gap_mean": round(gap_mean, 2),
            "n": len(gaps),
            "neg_ratio": round(neg_ratio, 2),
            "sector_weak": gap_mean < SECTOR_WEAK_THRESHOLD,
        }
    return result


# ── 板块集中度限制 ──

def enforce_sector_diversity(
    pool: list[dict], sym_to_sector: dict[str, str]
) -> list[dict]:
    """确保池子不被单一板块主导：依次移除超出限额的尾部股票。"""
    kept = []
    sector_count: Counter = Counter()
    eliminated_for_diversity = []

    for it in pool:
        sym = it.get("symbol", "")
        sector = sym_to_sector.get(sym, "其他")
        rank = len(kept) + 1  # 当前排名（1-based）

        # 根据排名判断限额
        if rank <= 10:
            limit = MAX_SAME_SECTOR_IN_TOP10
        elif rank <= 20:
            limit = MAX_SAME_SECTOR_IN_TOP20
        else:
            limit = MAX_SAME_SECTOR_IN_POOL

        if sector_count[sector] >= limit:
            eliminated_for_diversity.append({
                "symbol": sym,
                "name": it.get("name", ""),
                "sector": sector,
                "rank": rank,
                "limit": limit,
            })
            continue

        kept.append(it)
        sector_count[sector] += 1

    if eliminated_for_diversity:
        log(f"  板块集中度限制剔除 {len(eliminated_for_diversity)} 只:")
        for x in eliminated_for_diversity[:8]:
            log(f"    {x['name']}({x['symbol']}) {x['sector']} @rank={x['rank']} limit={x['limit']}")

    return kept


# ── 主入口 ──

def run_pre_market_gate() -> int:
    """主入口：加载推荐池 → 集合竞价门控 → 写回。"""
    if not REC_PATH.exists():
        log(f"[ERROR] {REC_PATH} 不存在，跳过集合竞价门控")
        return 1

    recs = json.loads(REC_PATH.read_text(encoding="utf-8"))
    items: list = list(recs.get("recommendations") or [])
    if not items:
        log("[SKIP] 推荐池为空")
        return 0

    log(f"推荐池加载: {len(items)} 只")

    # 取 Top-N 做集合竞价检查
    top_items = items[:CALL_AUCTION_TOP_N]
    syms = [it.get("symbol", "") for it in top_items if it.get("symbol")]

    t0 = time.time()
    quotes = fetch_call_auction_quotes(syms)
    elapsed = time.time() - t0
    log(f"腾讯实时行情: 请求 {len(syms)} 只, 返回 {len(quotes)} 只, 耗时 {elapsed:.1f}s")

    if not quotes:
        log("[SKIP] 无集合竞价数据返回（API可能未更新）")
        return 2

    # 筛选有有效竞价数据的
    valid_quotes = {s: q for s, q in quotes.items() if has_call_auction_data(q)}
    log(f"有效集合竞价数据: {len(valid_quotes)}/{len(quotes)} 只")

    # 计算个股信号
    signals = {}
    for sym, q in valid_quotes.items():
        signals[sym] = compute_stock_signals(q)

    # 加载行业映射
    industry_map = load_industry_map()
    imap_hit = sum(1 for s in valid_quotes if _bare(s) in industry_map)
    log(f"行业映射: {imap_hit}/{len(valid_quotes)} 只匹配")

    # 建立 sym→sector 索引
    sym_to_sector = {}
    for sym in valid_quotes:
        imap = industry_map.get(_bare(sym), {})
        sym_to_sector[sym] = imap.get("industry_l1", "其他")

    # 将 gap 注入 quotes 供 sector 聚合用
    for sym, sig in signals.items():
        if sym in quotes:
            quotes[sym]["gap_pct"] = sig["gap_pct"]

    sector_signals = aggregate_sector_signals(quotes, industry_map)
    weak_sectors = {s for s, d in sector_signals.items() if d["sector_weak"]}
    log(
        f"板块竞价信号: {len(sector_signals)} 个板块, "
        + ", ".join(
            f"{s}(gap={d['gap_mean']}% n={d['n']}{' ⚠️WEAK' if d['sector_weak'] else ''})"
            for s, d in sorted(
                sector_signals.items(), key=lambda x: -abs(x[1]["gap_mean"])
            )[:8]
        )
    )
    if weak_sectors:
        log(f"  弱板块标记（gap<{SECTOR_WEAK_THRESHOLD}%）: {sorted(weak_sectors)}")

    # ── 执行门控逻辑 ──
    eliminated = []
    survivors = []

    elimination_reasons = Counter()

    for it in items:
        sym = it.get("symbol", "")
        sig = signals.get(sym)
        it = dict(it)  # 副本

        # 注入元数据（初始）
        it["pre_market_gap_pct"] = None
        it["pre_market_call_amount_wan"] = None
        it["pre_market_call_volume_hand"] = None
        it["pre_market_close"] = None
        it["pre_market_sector_weak"] = False

        if sig is None:
            # 无竞价数据：保留但降权 5%
            it["pre_market_adjusted_score"] = float(it.get("score", 0)) * 0.95
            it["pre_market_action"] = "no_data"
            it["pre_market_note"] = "no_call_auction_data"
            survivors.append(it)
            continue

        # 注入集合竞价信号
        it["pre_market_gap_pct"] = sig["gap_pct"]
        it["pre_market_call_amount_wan"] = sig["call_amount_wan"]
        it["pre_market_call_volume_hand"] = sig["call_volume_hand"]
        it["pre_market_close"] = sig["close"]

        sector = sym_to_sector.get(sym, "其他")
        ss = sector_signals.get(sector, {})
        sector_weak = ss.get("sector_weak", False)
        it["pre_market_sector_weak"] = sector_weak
        sector_gap_mean = ss.get("gap_mean", 0)

        gap_pct = sig["gap_pct"]

        # ── 规则1: 近涨停不推 ──
        if gap_pct >= GAP_LIMIT_UP:
            it["pre_market_adjusted_score"] = 0
            it["pre_market_action"] = "eliminated"
            it["pre_market_note"] = f"gap={gap_pct}% near_limit"
            eliminated.append(it)
            elimination_reasons["near_limit"] += 1
            continue

        # ── 规则2: gap < -2% 硬剔除 ──
        if gap_pct < GAP_HARD_DROP:
            it["pre_market_adjusted_score"] = 0
            it["pre_market_action"] = "eliminated"
            it["pre_market_note"] = f"gap={gap_pct}% <{GAP_HARD_DROP}%"
            eliminated.append(it)
            elimination_reasons["gap_too_low"] += 1
            continue

        # ── 规则3: gap < 0 且 板块弱 → 硬剔除 ──
        if gap_pct < 0 and sector_weak:
            it["pre_market_adjusted_score"] = 0
            it["pre_market_action"] = "eliminated"
            it["pre_market_note"] = (
                f"gap={gap_pct}% sector={sector}({sector_gap_mean}%) double_weak"
            )
            eliminated.append(it)
            elimination_reasons["sector_stock_double_weak"] += 1
            continue

        # ── 规则4: gap < -0.5% 降权 ──
        base_score = float(it.get("score", 0))
        if gap_pct < GAP_DEMOTE:
            # gap -0.5% → 降权 5%; gap -1.9% → 降权 ~25%
            penalty = max(0.05, min(0.35, abs(gap_pct) * 0.13))
            adj_score = base_score * (1 - penalty)
            it["pre_market_adjusted_score"] = round(max(0, adj_score), 4)
            it["pre_market_action"] = "demoted"
            it["pre_market_note"] = f"gap={gap_pct}% penalty={penalty:.2f}"
            survivors.append(it)
            continue

        # ── 规则5: gap >= -0.5% 保留 ──
        # 小幅加分（gap 0~+2% +3%, gap +2~+5% +6%）
        if gap_pct >= 2.0:
            bonus = 0.06
        elif gap_pct >= 0.5:
            bonus = 0.03
        elif gap_pct >= 0:
            bonus = 0.01
        else:
            bonus = 0.0

        # 板块信号微调（仅弱板块减分，强板块不额外加分避免追高）
        sector_penalty = 0.03 if sector_weak else 0.0

        total_adj = bonus - sector_penalty
        adj_score = base_score * (1 + total_adj)
        it["pre_market_adjusted_score"] = round(max(0, adj_score), 4)
        it["pre_market_action"] = "kept"
        it["pre_market_note"] = f"gap={gap_pct}% bonus={bonus}"
        survivors.append(it)

    # ── 重排序 ──
    survivors.sort(key=lambda x: -float(x.get("pre_market_adjusted_score") or 0))

    # 打印淘汰情况
    for reason, cnt in elimination_reasons.most_common():
        log(f"  剔除: {reason} {cnt} 只")
    log(f"剔除总计: {len(eliminated)} 只, 幸存: {len(survivors)} 只")

    # 打印幸存 Top10 板块分布
    sector_dist = Counter()
    for it in survivors[:20]:
        sym = it.get("symbol", "")
        sector = sym_to_sector.get(sym, "其他")
        sector_dist[sector] += 1
    log(f"  Top20 板块分布: {dict(sector_dist.most_common(6))}")

    # ── 板块集中度限制 ──
    final_pool = enforce_sector_diversity(survivors, sym_to_sector)

    # ── 注入 score 字段 ──
    for it in final_pool:
        adj = it.get("pre_market_adjusted_score")
        orig = it.get("score", 0)
        if adj is not None and adj > 0:
            it["icir_raw_score"] = orig
            if "ml_score" not in it or it.get("ml_score") == orig:
                it["ml_score"] = round(adj, 4)
            it["score"] = round(adj, 4)

    # 打印最终 Top5
    log("  Top5 调整后:")
    for i, it in enumerate(final_pool[:5]):
        sym = it.get("symbol", "")
        name = it.get("name", "")
        orig = it.get("icir_raw_score", it.get("score", 0))
        adj = it.get("score", orig)
        gap = it.get("pre_market_gap_pct", "N/A")
        act = it.get("pre_market_action", "kept")
        sector = sym_to_sector.get(sym, "?")
        log(f"    #{i+1} {name}({sym}) [{sector}] score={orig:.4f}->{adj:.4f} gap={gap}% {act}")

    diversity_drops = len(survivors) - len(final_pool)

    # ── 写回 ──
    recs["recommendations"] = final_pool
    recs["pre_market_gate"] = {
        "run_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "n_checked": len(valid_quotes),
        "n_eliminated": len(eliminated),
        "n_survivors": len(survivors),
        "n_diversity_drops": diversity_drops,
        "n_final_pool": len(final_pool),
        "elimination_reasons": dict(elimination_reasons),
        "weak_sectors": sorted(weak_sectors),
        "sector_signals": {
            s: {k: d[k] for k in ("gap_mean", "n", "neg_ratio", "sector_weak")}
            for s, d in sorted(sector_signals.items(), key=lambda x: -abs(x[1]["gap_mean"]))[:10]
        },
        "top20_sector_dist": dict(sector_dist.most_common(10)),
        "eliminated": [
            {"symbol": x.get("symbol"), "name": x.get("name"),
             "gap": x.get("pre_market_gap_pct"), "reason": x.get("pre_market_note"),
             "sector": sym_to_sector.get(x.get("symbol", ""), "?")}
            for x in eliminated[:20]
        ],
        "rules": [
            f"gap<{GAP_HARD_DROP}% → 硬剔除",
            "gap<0 且 板块weak → 硬剔除",
            f"gap<{GAP_DEMOTE}% → 降权(penalty~|gap|*0.13)",
            f"Top10 同板块上限 {MAX_SAME_SECTOR_IN_TOP10} 只",
            f"Top20 同板块上限 {MAX_SAME_SECTOR_IN_TOP20} 只",
            f"板块gap_mean<{SECTOR_WEAK_THRESHOLD}% → weak标记",
        ],
    }
    REC_PATH.write_text(json.dumps(recs, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"写回 {REC_PATH} ({len(final_pool)} 只)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_pre_market_gate())
