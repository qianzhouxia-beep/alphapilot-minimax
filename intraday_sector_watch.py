#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盘中板块资金巡检 — 检测选股板块资金反转，触发紧急撤单/卖出信号。

核心逻辑：
  05:00/09:25/09:35 的选股基于盘前板块信号。
  开盘后板块可能由流入→流出，导致持仓股下跌。
  本模块每小时巡检，用 akshare 免费源聚合板块实时资金流，
  若持仓板块反转（转流出），生成紧急卖出信号。

数据源：akshare stock_fund_flow_individual（免费，60s缓存，~13s全市场扫描）
  → 聚合至 industry_l1 级 → 与选股时的板块基线对比

输出: output/sector_watch_alerts.json
  { "alerts": [{ "symbol", "name", "sector", "reason", "action", "severity" }],
    "sector_snapshots": { sector: { main_net, n_stocks, direction } },
    "run_at": "..." }

消费方：trade_executor.py --sell-only 每 10 分钟巡检时读取本文件触发卖出
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path("/home/ubuntu/alphapilot")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

REC_PATH = ROOT / "output/daily_recommend.json"
PT_PATH = ROOT / "data" / "paper_trading.json"
ALERT_PATH = ROOT / "output" / "sector_watch_alerts.json"
INDUSTRY_MAP_PATH = ROOT / "data" / "stock_industry_map.json"
BOARD_FLOW_PATH = ROOT / "data" / "wind_board_flow.json"

# 板块反转卖出触发阈值
SECTOR_NET_OUTFLOW = -5e6       # 板块主力净流出 > 500万 → 标记流出
SECTOR_NEGATIVE_RATIO = 0.6     # 板块内 60% 个股净流出 → 确认反转
SECTOR_ACCELERATE = -1e7        # 板块净流出 > 1000万 → 强卖出

def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ── 数据加载 ──

def load_industry_map() -> dict[str, dict]:
    if not INDUSTRY_MAP_PATH.exists():
        return {}
    try:
        return json.loads(INDUSTRY_MAP_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _bare(sym: str) -> str:
    s = str(sym or "").lower().replace("sh", "").replace("sz", "").replace("bj", "")
    return s[-6:] if len(s) >= 6 else s


def get_sector(sym: str, imap: dict) -> str:
    meta = imap.get(_bare(sym), {})
    if isinstance(meta, dict):
        return meta.get("industry_l1", "其他")
    return "其他"


def load_current_positions() -> list[dict]:
    """从 paper_trading.json 加载当前持仓"""
    if not PT_PATH.exists():
        return []
    try:
        pt = json.loads(PT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    positions = []
    for s in pt.get("strategies", []):
        for p in s.get("positions", []):
            qty = float(p.get("quantity") or 0)
            if qty > 0:
                positions.append({
                    "symbol": _bare(p.get("symbol", "")),
                    "name": p.get("name", ""),
                    "quantity": qty,
                    "buy_price": float(p.get("buy_price") or 0),
                    "strategy_id": s.get("id", ""),
                    "protocol": p.get("protocol", "tradable_top2"),
                })
    return positions


def load_selection_sectors() -> set[str]:
    """从 daily_recommend.json 读取选股时的板块基线。
    返回选股时有板块加分的板块集合（prefer）。
    """
    if not REC_PATH.exists():
        return set()
    try:
        rec = json.loads(REC_PATH.read_text(encoding="utf-8"))
        lr = rec.get("live_rerank") or rec.get("pre_market_gate") or {}
        # 从 live_rerank 元数据提取
        if "sector_dist_before" in lr:
            sectors = set(lr.get("sector_dist_before", {}).keys())
            return sectors
        # fallback: 从 recommandations 提取板块
        imap = load_industry_map()
        items = rec.get("recommendations", [])
        sectors = set()
        for it in items:
            sec = get_sector(it.get("symbol", ""), imap)
            if sec != "其他":
                sectors.add(sec)
        return sectors
    except Exception:
        return {}


def load_pre_open_sector_assignment() -> dict[str, str]:
    """从 wind_board_flow.json consult 读取选股时的板块基线。
    返回 { sector: "prefer"/"avoid"/"neutral" }
    """
    if not BOARD_FLOW_PATH.exists():
        return {}
    try:
        data = json.loads(BOARD_FLOW_PATH.read_text(encoding="utf-8"))
        consult = data.get("consult") or {}
        prefer = set(consult.get("prefer", []))
        avoid = set(consult.get("avoid", []))
        result = {}
        for s in prefer:
            result[s] = "prefer"
        for s in avoid:
            result[s] = "avoid"
        return result
    except Exception:
        return {}


# ── 实时资金扫描 ──

def fetch_sector_fund_flow(
    positions: list[dict],
    imap: dict,
) -> tuple[dict[str, dict], dict[str, list[str]]]:
    """用 live_fund_flow 的 akshare 免费源，聚合板块级别资金流。

    返回:
      sector_stats: { sector: { main_net, n_pos, n_neg, neg_ratio, direction } }
      sector_members: { sector: [symbol, ...] }  // 持仓股所在板块的所有监控股
    """
    from live_fund_flow import batch_fund_flow

    # 收集所有持仓股
    pos_symbols = list({p["symbol"] for p in positions if p["symbol"]})
    if not pos_symbols:
        return {}, {}

    # 批量获取实时资金（akshare免费，60s缓存）
    t0 = time.time()
    flows = batch_fund_flow(pos_symbols)
    elapsed = time.time() - t0
    log(f"实时资金扫描: {len(flows)}/{len(pos_symbols)} 只返回, 耗时 {elapsed:.1f}s")

    # 按板块聚合
    sector_agg: dict[str, dict] = defaultdict(lambda: {
        "main_nets": [], "n_pos": 0, "n_neg": 0, "n_total": 0,
    })
    sector_members: dict[str, list[str]] = defaultdict(list)

    for sym, f in flows.items():
        bare = _bare(sym)
        sector = get_sector(bare, imap)
        main_net = float(f.get("main_net", 0) or 0)
        sector_agg[sector]["main_nets"].append(main_net)
        sector_agg[sector]["n_total"] += 1
        if main_net > 0:
            sector_agg[sector]["n_pos"] += 1
        else:
            sector_agg[sector]["n_neg"] += 1
        # 记录该板块仓位的 symbol
        if bare in {p["symbol"] for p in positions}:
            sector_members[sector].append(bare)

    # 计算板块统计
    sector_stats = {}
    for sector, agg in sector_agg.items():
        main_nets = agg["main_nets"]
        total_main = sum(main_nets)
        n = agg["n_total"]
        neg_ratio = agg["n_neg"] / max(n, 1)
        if total_main >= SECTOR_NET_OUTFLOW and neg_ratio < SECTOR_NEGATIVE_RATIO:
            direction = "inflow"
        elif total_main < SECTOR_ACCELERATE:
            direction = "accelerate_outflow"
        elif total_main < SECTOR_NET_OUTFLOW:
            direction = "outflow"
        else:
            direction = "stable"

        sector_stats[sector] = {
            "main_net": round(total_main, 2),
            "n_stocks": n,
            "n_negative": agg["n_neg"],
            "neg_ratio": round(neg_ratio, 2),
            "direction": direction,
        }

    return sector_stats, sector_members


def generate_alerts(
    positions: list[dict],
    sector_stats: dict[str, dict],
    sector_members: dict[str, list[str]],
    baseline: dict[str, str],
    imap: dict,
) -> list[dict]:
    """生成紧急卖出信号。

    规则：
      1. 持仓板块由 prefer→outflow/accelerate_outflow → 触发卖出
      2. 持仓板块 accelerate_outflow → 强卖出
      3. 持仓股所在板块 outflow → 不论基线, 个股也跌 → 卖出
    """
    alerts = []

    for pos in positions:
        sym = pos["symbol"]
        name = pos["name"]
        sector = get_sector(sym, imap)
        ss = sector_stats.get(sector)
        if not ss:
            continue

        direction = ss["direction"]
        main_net = ss["main_net"]
        baseline_tier = baseline.get(sector, "")

        # 规则1: 板块加速流出 (<-1000万) → 强卖出
        if direction == "accelerate_outflow":
            alerts.append({
                "symbol": sym,
                "name": name,
                "sector": sector,
                "reason": f"板块资金加速流出({main_net/1e8:.2f}亿)",
                "action": "force_sell",
                "severity": "high",
                "sector_main_net": main_net,
            })
            continue

        # 规则2: 板块流出 + 基线是prefer → 反转信号
        if direction == "outflow" and baseline_tier == "prefer":
            alerts.append({
                "symbol": sym,
                "name": name,
                "sector": sector,
                "reason": f"板块资金反转:选股时prefer→现流出({main_net/1e8:.2f}亿)",
                "action": "force_sell",
                "severity": "medium",
                "sector_main_net": main_net,
            })
            continue

        # 规则3: 板块稳定/流入 → 不触发
        if direction in ("inflow", "stable"):
            continue

    return alerts


# ── 主入口 ──

def run_sector_watch() -> int:
    """主入口：检查持仓板块资金反转，输出告警。"""
    log("=" * 60)
    log("盘中板块资金巡检 — akshare免费源")

    # 1. 当前持仓
    positions = load_current_positions()
    if not positions:
        # 无持仓时清空告警
        ALERT_PATH.write_text(json.dumps(
            {"alerts": [], "sector_snapshots": {},
             "run_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             "note": "无持仓"},
            ensure_ascii=False, indent=2), encoding="utf-8")
        log("无持仓，跳过巡检")
        return 0

    log(f"当前持仓: {len(positions)} 只")
    for p in positions:
        log(f"  {p['name']}({p['symbol']}) qty={p['quantity']}")

    # 2. 行业映射
    imap = load_industry_map()
    log(f"行业映射: {len(imap)} 只")

    # 3. 选股时板块基线
    baseline = load_pre_open_sector_assignment()
    log(f"板块基线: {len(baseline)} 个 (prefer={sum(1 for v in baseline.values() if v=='prefer')})")

    # 4. 实时板块资金
    sector_stats, sector_members = fetch_sector_fund_flow(positions, imap)

    if not sector_stats:
        log("无法获取板块资金数据")
        return 1

    # 5. 板块趋势汇总
    directions = defaultdict(int)
    for s, ss in sector_stats.items():
        directions[ss["direction"]] += 1
        log(f"  板块[{s}]: net={ss['main_net']/1e8:.2f}亿 "
            f"负比={ss['neg_ratio']:.0%} "
            f"方向={ss['direction']} "
            f"({ss['n_stocks']}只)")

    log(f"板块汇总: inflow={directions.get('inflow',0)} "
        f"stable={directions.get('stable',0)} "
        f"outflow={directions.get('outflow',0)} "
        f"加速流出={directions.get('accelerate_outflow',0)}")

    # 6. 生成告警
    alerts = generate_alerts(positions, sector_stats, sector_members, baseline, imap)

    log(f"卖出信号: {len(alerts)} 只")
    for a in alerts:
        log(f"  🚨 {a['name']}({a['symbol']}) [{a['sector']}] "
            f"{a['reason']} severity={a['severity']}")

    # 7. 写告警文件
    output = {
        "alerts": alerts,
        "sector_snapshots": sector_stats,
        "positions_checked": [
            {"symbol": p["symbol"], "name": p["name"], "quantity": int(p["quantity"])}
            for p in positions
        ],
        "run_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "n_positions": len(positions),
        "n_alerts": len(alerts),
        "sector_summary": dict(directions),
    }
    ALERT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"写告警文件 {ALERT_PATH} ({len(alerts)} 条告警)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_sector_watch())
