#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
09:35 开盘重排门 — 根据实时资金 4 档归因 + 板块资金重排序。

覆盖逻辑：
  输入: daily_recommend.json（05:00 管线的原始推荐 + 09:25 集合竞价门控标注）
  输出: 写回 daily_recommend.json，score 被实时资金信号覆盖
  下游: 09:35 morning_live_fund_select / 09:36 paper_trading 自然使用新排序

数据源策略（积分优化）：
  - 腾讯 qt.gtimg.cn（免费）→ 实时涨跌幅
  - Wind MCP（~0.6 分/次）→ 前 20 只候选的 4 档归因
  - Wind 板块流（~5 分/次）→ 板块实时资金方向
  - 同花顺 akshare（免费）→ 后 20 只的主力净流入（无 4 档）

设计参考: docs/LIVE_RERANK_GATE.md
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from collections import Counter, OrderedDict
from datetime import datetime
from pathlib import Path

import requests
import numpy as np

ROOT = Path("/home/ubuntu/alphapilot")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

REC_PATH = ROOT / "output/daily_recommend.json"
WIND_CAND_PATH = ROOT / "data" / "wind_candidate_flow.json"  # enrich_candidates_wind 已缓存
WIND_BOARD_PATH = ROOT / "data" / "wind_board_flow.json"
INDUSTRY_MAP_PATH = ROOT / "data" / "stock_industry_map.json"

# Wind 只打前 N 只的 4 档归因（省积分）
WIND_TOP_N = 20
# 暴跌剔除线
CHG_HARD_DROP = -5.0

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://gu.qq.com/",
}
_TENCENT = "https://qt.gtimg.cn/q="


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ────────────────────────────────────────────
# 1. 腾讯免费实时行情 → 涨跌幅/价格
# ────────────────────────────────────────────

def _tencent_prefix(sym: str) -> str:
    if sym.startswith("6"):
        return "sh"
    if sym.startswith(("4", "8", "9")):
        return "bj"
    return "sz"


def _parse_quote(body: str) -> dict | None:
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
            "high": float(f[33]) if len(f) > 33 and f[33] else 0.0,
            "low": float(f[34]) if len(f) > 34 and f[34] else 0.0,
        }
    except (ValueError, IndexError):
        return None


def fetch_tencent_quotes(symbols: list[str], batch: int = 80) -> dict:
    """批量获取腾讯实时行情 → {symbol: {change_pct, price, ...}}"""
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
            log(f"  tencent batch [{i//batch}] error: {e}")
    return out


# ────────────────────────────────────────────
# 2. Wind MCP 4 档资金 — 前 WIND_TOP_N 只
# ────────────────────────────────────────────

def _bare(sym: str) -> str:
    s = str(sym or "").lower().replace("sh", "").replace("sz", "").replace("bj", "")
    return re.sub(r"\D", "", s)[-6:]


def _windcode(bare: str) -> str:
    b = _bare(bare)
    if not b or len(b) != 6:
        return b
    if b.startswith(("5", "6", "9")):
        return f"{b}.SH"
    return f"{b}.SZ"


def load_wind_api_key() -> str:
    from scripts.enrich_candidates_wind import load_api_key
    return load_api_key()


def wind_mcp_call(api_key: str, tool_name: str, arguments: dict, timeout: float = 60.0) -> dict:
    from scripts.enrich_candidates_wind import mcp_call
    return mcp_call(api_key, tool_name, arguments, timeout)


def wind_extract_row(result: dict) -> dict:
    from scripts.enrich_candidates_wind import _extract_row
    return _extract_row(result)


def _f(v):
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def fetch_wind_fund_flow_top_n(
    api_key: str, symbols: list[str], top_n: int = WIND_TOP_N
) -> dict[str, dict]:
    """Wind MCP 取前 top_n 只的 4 档资金归因。"""
    targets = symbols[:top_n]
    # 4 档归因字段
    indexes = (
        "中文简称,最新成交价,涨跌幅,"
        "该日机构资金净流入额,该日大户资金净流入额,"
        "该日中户资金净流入额,该日散户资金净流入额,"
        "当日主力净流入额,当日主力净流入占比"
    )
    result: dict[str, dict] = {}
    for sym in targets:
        try:
            resp = wind_mcp_call(
                api_key,
                "get_stock_price_indicators",
                {"windcode": _windcode(sym), "indexes": indexes, "unit": "元"},
                timeout=30,
            )
            row = wind_extract_row(resp)
            if row:
                result[sym] = {
                    "inst_net": _f(row.get("该日机构资金净流入额")),
                    "large_net": _f(row.get("该日大户资金净流入额")),
                    "mid_net": _f(row.get("该日中户资金净流入额")),
                    "retail_net": _f(row.get("该日散户资金净流入额")),
                    "main_net": _f(row.get("当日主力净流入额")),
                    "main_net_ratio": _f(row.get("当日主力净流入占比")),
                    "wind_price": _f(row.get("最新成交价")),
                    "wind_chg_pct": _f(row.get("涨跌幅")),
                    "source": "wind_mcp",
                }
        except Exception as e:
            log(f"  wind MCP {sym} fail: {str(e)[:60]}")
            result[sym] = {"source": "wind_fail"}
    log(f"  Wind 4档资金: {sum(1 for v in result.values() if v.get('source')=='wind_mcp')}/{len(targets)} ok")
    return result


# ────────────────────────────────────────────
# 3. 板块资金流向 — 从 Wind 板文件缓存读取
# ────────────────────────────────────────────

# ─── 板块别名匹配（与 wind_sector_prefer_boost.py 对齐）
SECTOR_ALIASES: dict[str, list[str]] = {
    "有色金属": ["有色金属", "工业金属", "贵金属"],
    "基础化工": ["基础化工", "农化制品"],
    "电力设备": ["电力设备", "电网设备", "电池", "光伏设备", "风电设备"],
    "电子": ["电子", "半导体", "消费电子"],
    "医药生物": ["医药生物", "化学制药", "中药", "生物制品"],
    "计算机": ["计算机", "软件开发", "IT服务"],
    "汽车": ["汽车", "汽车零部件"],
    "机械设备": ["机械设备", "通用设备", "专用设备", "自动化设备"],
    "电力": ["电力", "公用事业"],
    "房地产": ["房地产", "房地产开发"],
    "钢铁": ["钢铁", "普钢", "特钢"],
    "建筑装饰": ["建筑装饰", "基础建设"],
    "煤炭": ["煤炭", "焦炭"],
    "食品饮料": ["食品饮料", "白酒"],
}

def _clean_name(n: str) -> str:
    return re.sub(r"\(申万\)$", "", str(n or "")).strip()


def _expand_names(names: list[str]) -> set[str]:
    """展开板块名及其别名 → set[str]"""
    out: set[str] = set()
    for n in names:
        n = _clean_name(n)
        if not n:
            continue
        out.add(n)
        for a in SECTOR_ALIASES.get(n, []):
            out.add(a)
    return out


def _sector_hit(sector: str, name_set: set[str]) -> bool:
    """检查 stock 的 industry_l1 是否命中板块名集合（含别名/子串）"""
    if not sector or not name_set:
        return False
    for n in name_set:
        if sector == n or _clean_name(n) == sector:
            return True
        if len(sector) >= 2 and sector in _clean_name(n):
            return True
        if len(_clean_name(n)) >= 2 and _clean_name(n) in sector:
            return True
    return False


def load_sector_flow() -> tuple[set[str], set[str], set[str]]:
    """加载 Wind 板块资金 consult 视图 → (prefer_names, avoid_names, watch_names)"""
    if not WIND_BOARD_PATH.exists():
        log(f"  [WARN] 板块资金文件 {WIND_BOARD_PATH} 不存在")
        return set(), set(), set()
    try:
        data = json.loads(WIND_BOARD_PATH.read_text(encoding="utf-8"))
        consult = data.get("consult") or {}
        prefer = _expand_names(list(consult.get("prefer", [])))
        avoid = _expand_names(list(consult.get("avoid", [])))
        watch = _expand_names(list(consult.get("rotation_watch", [])))
        log(f"  板块 consult: prefer={len(prefer)} avoid={len(avoid)} watch={len(watch)}")
        if prefer:
            log(f"    prefer样本: {list(prefer)[:5]}")
        if avoid:
            log(f"    avoid样本: {list(avoid)[:5]}")
        return prefer, avoid, watch
    except Exception as e:
        log(f"  [WARN] 板块资金解析失败: {e}")
        return set(), set(), set()


# ────────────────────────────────────────────
# 4. 行业映射
# ────────────────────────────────────────────

def load_industry_map() -> dict:
    if not INDUSTRY_MAP_PATH.exists():
        return {}
    try:
        return json.loads(INDUSTRY_MAP_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _sector_of(sym: str, industry_map: dict) -> str:
    imap = industry_map.get(_bare(sym), {})
    return imap.get("industry_l1", "其他")


# ────────────────────────────────────────────
# 5. 重排逻辑
# ────────────────────────────────────────────

def compute_rerank_factor(
    chg_pct: float | None,
    flow: dict | None,
    sector: str,
    prefer_sectors: set[str],
    avoid_sectors: set[str],
) -> tuple[float, str]:
    """根据实时涨跌幅 + 4 档资金返回乘数因子和理由。

    规则：
      暴跌剔除: chg_pct < -5%
      机构逆势: chg < -2% 且 inst_net > 0 → ×1.12
      机构出货: chg < -2% 且 inst_net < -5000w → ×0.80
      双买入:   inst_net > 0 且 large_net > 0 → ×1.05
      主力买入: main_net > 0 → ×1.02
      机构卖出: inst_net < -5000w → ×0.90
      抗跌加分: chg > 0 → ×(1 + chg/10)
      板块加分: 板块为 prefer → ×1.03
      板块减分: 板块为 avoid → ×0.92

    因子可叠加（乘法）。
    """
    factors = [1.0]
    reasons = []

    # 暴跌剔除 → 返回 0
    if chg_pct is not None and chg_pct < CHG_HARD_DROP:
        return 0.0, f"暴跌{chg_pct:.1f}%<-5%, 剔除"

    # 机构逆势信号
    inst_net = flow.get("inst_net") if flow else None
    large_net = flow.get("large_net") if flow else None
    main_net = flow.get("main_net") if flow else None

    if chg_pct is not None and chg_pct < -2.0:
        if inst_net is not None and inst_net > 0:
            factors.append(1.12)
            reasons.append(f"逆势+机构{inst_net/1e8:.1f}亿")
        elif inst_net is not None and inst_net < -5e7:
            factors.append(0.80)
            reasons.append(f"机构出货{inst_net/1e8:.1f}亿")
        else:
            factors.append(0.95)
            reasons.append(f"下跌{chg_pct:.1f}%")
    elif inst_net is not None and large_net is not None and inst_net > 0 and large_net > 0:
        factors.append(1.05)
        reasons.append(f"机{inst_net/1e8:.1f}亿+大{large_net/1e8:.1f}亿双买")
    elif main_net is not None and main_net > 0:
        factors.append(1.02)
        reasons.append(f"主力+{main_net/1e8:.1f}亿")
    elif inst_net is not None and inst_net < -5e7:
        factors.append(0.90)
        reasons.append(f"机构大卖{inst_net/1e8:.1f}亿")

    # 抗跌加分：红盘
    if chg_pct is not None and chg_pct > 0:
        bonus = 1 + min(chg_pct / 10, 0.05)  # 涨2% → +0.2%, 涨10% → +1%
        factors.append(bonus)
        reasons.append(f"红盘+{chg_pct:.1f}%")

    # 板块资金
    if prefer_sectors and _sector_hit(sector, prefer_sectors):
        factors.append(1.03)
        reasons.append(f"板块流入")
    elif avoid_sectors and _sector_hit(sector, avoid_sectors):
        factors.append(0.92)
        reasons.append(f"板块流出")

    # 相乘
    final = 1.0
    for f in factors:
        final *= f
    return round(final, 4), "; ".join(reasons)


def run_live_rerank() -> int:
    """主入口。"""
    if not REC_PATH.exists():
        log(f"[ERROR] {REC_PATH} 不存在")
        return 1

    recs = json.loads(REC_PATH.read_text(encoding="utf-8"))
    items: list = list(recs.get("recommendations") or [])
    if not items:
        log("[SKIP] 空推荐池")
        return 0

    log(f"推荐池加载: {len(items)} 只 — 开始开盘重排")

    # ─── A. 腾讯免费行情（全部） ───
    syms = [it.get("symbol", "") for it in items if it.get("symbol")]
    t0 = time.time()
    tencent = fetch_tencent_quotes(syms)
    te = time.time() - t0
    log(f"腾讯行情: {len(tencent)}/{len(syms)} 只返回, 耗时 {te:.1f}s")

    # ─── B. Wind 4档资金（前 WIND_TOP_N 只） ───
    api_key = None
    wind_flow: dict[str, dict] = {}

    # 优先用晨间 enrich_candidates_wind 已缓存的数据
    if WIND_CAND_PATH.exists():
        try:
            cached = json.loads(WIND_CAND_PATH.read_text(encoding="utf-8"))
            for sym, d in cached.items():
                if isinstance(d, dict):
                    wind_flow[_bare(sym)] = d
            log(f"Wind缓存数据: {len(wind_flow)} 只 (enrich_candidates_wind 已跑)")
        except Exception:
            pass

    # 只对前 WIND_TOP_N 只补充 4 档归因
    try:
        api_key = load_wind_api_key()
        wind_four_tier = fetch_wind_fund_flow_top_n(api_key, syms, top_n=WIND_TOP_N)

        # 合并：有 4 档归因的覆盖缓存
        for sym, d in wind_four_tier.items():
            if d.get("source") == "wind_mcp":
                wind_flow[_bare(sym)] = {
                    **wind_flow.get(_bare(sym), {}),
                    "inst_net": d.get("inst_net"),
                    "large_net": d.get("large_net"),
                    "mid_net": d.get("mid_net"),
                    "main_net": d.get("main_net"),
                    "main_net_ratio": d.get("main_net_ratio"),
                    "source": "wind_4_tier",
                }
    except Exception as e:
        log(f"  Wind MCP 失败（使用缓存或缺省值）: {e}")

    # ─── C. 板块资金 ───
    prefer_sectors, avoid_sectors, watch_sectors = load_sector_flow()
    industry_map = load_industry_map()

    # ─── D. 执行重排 ───
    eliminated = []
    survivors = []
    sector_dist_before = Counter()
    sector_dist_after = Counter()

    import copy

    for it in items:
        sym = _bare(it.get("symbol", ""))
        it = copy.deepcopy(it)

        # 腾讯行情
        tq = tencent.get(sym)
        chg_pct = tq.get("change_pct") if tq else None

        # Wind 资金
        wf = wind_flow.get(sym)

        # 板块
        sector = _sector_of(sym, industry_map)
        sector_dist_before[sector] += 1

        # 注入元数据
        it["live_chg_pct"] = chg_pct
        it["live_price"] = tq.get("price") if tq else None
        it["live_inst_net"] = wf.get("inst_net") if wf else None
        it["live_large_net"] = wf.get("large_net") if wf else None
        it["live_main_net"] = wf.get("main_net") if wf else None
        it["live_main_net_ratio"] = wf.get("main_net_ratio") if wf else None
        it["live_fund_source"] = wf.get("source", "no_data") if wf else "no_data"

        old_score = float(it.get("score", 0))

        # 计算重排因子
        factor, reason = compute_rerank_factor(chg_pct, wf, sector, prefer_sectors, avoid_sectors)

        if factor <= 0:
            it["live_score"] = 0
            it["live_factor"] = factor
            it["live_action"] = "eliminated"
            it["live_note"] = reason
            eliminated.append(it)
            continue

        new_score = round(old_score * factor, 4)
        it["live_score"] = new_score
        it["live_factor"] = factor
        it["live_action"] = "kept"
        it["live_note"] = reason

        # 更新 score
        it["icir_raw_score"] = it.get("icir_raw_score", old_score)
        it["score"] = new_score
        it["ml_score"] = new_score
        it["lgb_score"] = new_score

        survivors.append(it)
        sector_dist_after[sector] += 1

    # ─── 重排序 ───
    survivors.sort(key=lambda x: -float(x.get("score", 0)))

    log(f"重排完成: 幸存 {len(survivors)} 只, 剔除 {len(eliminated)} 只")

    # Top5 对比
    log("  重排前 Top5:")
    for i, it in enumerate(items[:5]):
        log(f"    #{i+1} {it.get('name','')}({it.get('symbol','')}) score={it.get('score',0):.4f}")
    log("  重排后 Top5:")
    for i, it in enumerate(survivors[:5]):
        n = it.get("name", "")
        s = it.get("symbol", "")
        sc = it.get("score", 0)
        chg = it.get("live_chg_pct", "N/A")
        inst = it.get("live_inst_net", 0)
        inst_str = f"{inst/1e8:.2f}亿" if inst and abs(inst) >= 1e4 else "—"
        note = it.get("live_note", "")
        log(f"    #{i+1} {n}({s}) score={sc:.4f} chg={chg}% inst={inst_str} [{note}]")

    log(f"  板块分布: before={dict(sector_dist_before.most_common(6))}")
    log(f"  板块分布: after={dict(sector_dist_after.most_common(6))}")

    # ─── 写回 ───
    recs["recommendations"] = survivors
    recs["live_rerank"] = {
        "run_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "n_input": len(items),
        "n_survivors": len(survivors),
        "n_eliminated": len(eliminated),
        "n_wind_4_tier": sum(1 for v in wind_flow.values() if v.get("source") == "wind_4_tier"),
        "n_wind_cached": sum(1 for v in wind_flow.values() if v.get("source") != "wind_4_tier" and v),
        "n_tencent_quotes": len(tencent),
        "sector_dist_before": dict(sector_dist_before.most_common(15)),
        "sector_dist_after": dict(sector_dist_after.most_common(15)),
        "eliminated": [
            {"symbol": x.get("symbol"), "name": x.get("name"),
             "chg_pct": x.get("live_chg_pct"), "reason": x.get("live_note")}
            for x in eliminated[:20]
        ],
        "rules": [
            "chg<-5% → 剔除",
            "chg<-2%且inst_net>0 → ×1.12 (机构逆势加仓)",
            "chg<-2%且inst_net<-5000w → ×0.80 (机构出货)",
            "inst_net>0且large_net>0 → ×1.05 (双买入)",
            "main_net>0 → ×1.02 (主力买入)",
            "inst_net<-5000w → ×0.90 (机构大卖)",
            "chg>0 → ×(1+chg/10) (逆势加分)",
            "板块流入→×1.03; 板块流出→×0.92",
        ],
        "data_note": "Wind前20只4档归因; 其余来自enrich_candidates_wind缓存/同花顺免费源",
    }
    REC_PATH.write_text(json.dumps(recs, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"写回 {REC_PATH} ({len(survivors)} 只)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_live_rerank())
