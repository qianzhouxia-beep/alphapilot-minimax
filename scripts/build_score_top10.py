#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构建「评分 Top10」榜：09:35 终选候选，按三路融合综合分降序取前 10。

综合分 = 权重[模型分] * vm25 归一化 + 权重[资金流] * 主力净流入 tanh
        + 权重[板块热度] * 板块热度归一化
权重来自 output/feedback/model_weights.json（IC 反馈动态调整），缺失时用默认
vm25=0.50 / fund_flow=0.30 / sector_heat=0.20。

数据来源优先级：
1) output/daily_recommend.json（09:35 终选产物，score 已含管线综合调整）
2) 各 output/*.json 里带 score 的候选并集（仅补缺失）
3) 不足 10 只时，对量价金叉池轻量补评分
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from pathlib import Path

ROOT = Path("/home/ubuntu/alphapilot")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

OUT = ROOT / "output/score_top10.json"

DEFAULT_FUSION_WEIGHTS = {
    "vm25": 0.50,
    "fund_flow": 0.30,
    "sector_heat": 0.20,
}
FUND_TANH_SCALE = 10_000_000  # 1 亿 → tanh(1) = 0.76


def bare(s: str) -> str:
    x = str(s or "")
    for p in ("sh", "sz", "bj", "SH", "SZ", "BJ"):
        x = x.replace(p, "")
    return x[-6:] if len(x) >= 6 else x


def _load_fusion_weights() -> dict[str, float]:
    """读取 IC 反馈权重，缺失/损坏时用默认。"""
    try:
        p = ROOT / "output/feedback/model_weights.json"
        if p.exists():
            w = json.loads(p.read_text(encoding="utf-8")).get("weights", {})
            return {
                "vm25": float(w.get("vm25", DEFAULT_FUSION_WEIGHTS["vm25"])),
                "fund_flow": float(w.get("fund_flow", DEFAULT_FUSION_WEIGHTS["fund_flow"])),
                "sector_heat": float(w.get("sector_heat", DEFAULT_FUSION_WEIGHTS["sector_heat"])),
            }
    except Exception:
        pass
    return dict(DEFAULT_FUSION_WEIGHTS)


def _load_sector_heat_map() -> dict[str, float]:
    """板块热度映射 {板块名: 0~1}，key 覆盖一级(l1)与二级(l2)板块名。

    来源优先级：
    1) hot_sector_bypass_pool.json —— 今日主线板块（l2 名，change_pct 归一化），
       并通过 stock_industry_map 反查其 l1 名，让同属一级的候选也能命中
    2) call_auction_sector_heat.json —— 09:25 竞价热度（l1 名，heat_score）
    """
    m: dict[str, float] = {}
    try:
        imap: dict = {}
        ip = ROOT / "data/stock_industry_map.json"
        if ip.exists():
            try:
                imap = json.loads(ip.read_text(encoding="utf-8"))
            except Exception:
                imap = {}
        l2_to_l1: dict[str, str] = {}
        for meta in imap.values():
            l2 = meta.get("industry_l2")
            l1 = meta.get("industry_l1")
            if l2 and l1:
                l2_to_l1.setdefault(l2, l1)
    except Exception:
        l2_to_l1 = {}
    # 1) 主线板块
    try:
        p = ROOT / "output/hot_sector_bypass_pool.json"
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            l1_heat: dict[str, float] = {}
            for s in d.get("industries", []):
                nm = s.get("name")
                cp = float(s.get("change_pct") or 0)
                if not nm:
                    continue
                heat = max(0.0, min(1.0, (cp + 5.0) / 10.0))
                m[nm] = heat
                l1 = l2_to_l1.get(nm)
                if l1:
                    l1_heat[l1] = max(l1_heat.get(l1, 0.0), heat)
            for l1, heat in l1_heat.items():
                m[l1] = heat
    except Exception:
        pass
    # 2) 竞价热度兜底
    try:
        p = ROOT / "output/call_auction_sector_heat.json"
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            for s in d.get("hot_sectors", []):
                nm = s.get("sector")
                if nm and nm not in m:
                    m[nm] = max(0.0, min(1.0, float(s.get("heat_score") or 0.5)))
    except Exception:
        pass
    return m


def compute_fusion(rows: list[dict]) -> list[dict]:
    """三路融合综合分 + 按综合分降序。

    注入：
      _fusion_scores: {vm25, fund_flow, sector_heat}
      _fusion_weight: 综合分（0~1）
    保留 score（原始模型分）字段不变。

    vm25 = 池内 score min-max 归一化（避免 >1 分被 clamp 失去区分度）
    fund_flow = 主力净流入 tanh 归一化（+1亿 → 0.88）
    sector_heat = 板块热度（先按 l2 板块名匹配，再按 l1 匹配，未命中 0.5）
    """
    if not rows:
        return rows
    weights = _load_fusion_weights()
    heat_map = _load_sector_heat_map()
    try:
        imap = json.loads((ROOT / "data/stock_industry_map.json").read_text(encoding="utf-8"))
    except Exception:
        imap = {}
    scores = [float(r.get("score") or 0) for r in rows]
    lo, hi = min(scores), max(scores)
    span = (hi - lo) or 1.0
    for r in rows:
        sc = float(r.get("score") or 0)
        vm25 = max(0.0, min(1.0, (sc - lo) / span))  # 池内 min-max 归一化
        main_net = float(r.get("main_net") or r.get("live_main_net") or 0)
        fund = max(0.0, min(1.0, (math.tanh(main_net / FUND_TANH_SCALE) + 1.0) / 2.0))
        code = bare(r.get("symbol"))
        meta = imap.get(code) or {}
        l1 = meta.get("industry_l1") or r.get("industry_l1") or r.get("sector")
        l2 = meta.get("industry_l2")
        heat = 0.5
        if l2 and l2 in heat_map:
            heat = float(heat_map[l2])
        elif l1 and l1 in heat_map:
            heat = float(heat_map[l1])
        r["_sector_l2"] = l2
        r["_fusion_scores"] = {
            "vm25": round(vm25, 4),
            "fund_flow": round(fund, 4),
            "sector_heat": round(heat, 4),
        }
        r["_fusion_weight"] = round(
            weights["vm25"] * vm25
            + weights["fund_flow"] * fund
            + weights["sector_heat"] * heat,
            4,
        )
    return sorted(rows, key=lambda x: -float(x.get("_fusion_weight") or 0))


def harvest() -> dict[str, dict]:
    by: dict[str, dict] = {}
    # 1) 主数据源：09:35 终选产物（score 已含 LLM/S2/板块资金门控综合调整）
    rec = ROOT / "output/daily_recommend.json"
    if rec.exists():
        try:
            d = json.loads(rec.read_text(encoding="utf-8"))
            arr = d.get("recommendations") or []
            for it in arr:
                if not isinstance(it, dict):
                    continue
                code = bare(it.get("symbol"))
                if not code:
                    continue
                sc = float(it.get("score") or it.get("lgb_score") or it.get("model_proba") or 0)
                if sc <= 0:
                    continue
                row = dict(it)
                row["symbol"] = code
                row["score"] = sc
                row["_src"] = "daily_recommend"
                by[code] = row
        except Exception as e:
            print("harvest daily_recommend failed:", e)
    # 2) 兜底源：仅补缺失代码，不覆盖 09:35 终选分数
    paths = [
        ROOT / "output/daily_recommend_full.json",
        ROOT / "output/debate_v2_result.json",
        ROOT / "recommend_cache.json",
    ]
    paths += sorted((ROOT / "output").glob("*.json"))
    for p in paths:
        if not p.exists() or p.name in ("score_top10.json", "daily_recommend.json"):
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(d, list):
            arr = d
        elif isinstance(d, dict):
            arr = d.get("recommendations") or d.get("items") or []
        else:
            continue
        if not isinstance(arr, list):
            continue
        for it in arr:
            if not isinstance(it, dict):
                continue
            code = bare(it.get("symbol"))
            if not code or code in by:
                continue
            sc = float(it.get("score") or it.get("lgb_score") or it.get("model_proba") or 0)
            if sc <= 0:
                continue
            row = dict(it)
            row["symbol"] = code
            row["score"] = sc
            row["_src"] = p.name
            by[code] = row
    return by


def light_fill(by: dict[str, dict], need: int) -> dict[str, dict]:
    if need <= 0:
        return by
    gc_path = ROOT / "output/volume_gc_pool.json"
    if not gc_path.exists():
        return by
    try:
        gc = json.loads(gc_path.read_text(encoding="utf-8"))
        gc_b = {bare(x) for x in gc}
    except Exception:
        return by
    try:
        from ml_screener import screener
        from data_fetcher import get_kline_sina

        screener.load_model()
    except Exception as e:
        print("light_fill skip model:", e)
        return by

    targets = [c for c in sorted(gc_b) if c not in by][: max(need * 4, 40)]
    print(f"light score {len(targets)} to fill top10...")
    for code in targets:
        try:
            kl = get_kline_sina(code, start_date="20260101")
            if kl is None or getattr(kl, "empty", True):
                continue
            r = screener.score_stock(kl)
            if not r or "error" in r:
                continue
            sc = float(r.get("score") or 0)
            if sc <= 0:
                continue
            by[code] = {
                "symbol": code,
                "name": r.get("name") or code,
                "score": sc,
                "lgb_score": sc,
                "buy_price": r.get("buy_price") or r.get("target_price"),
                "target_price": r.get("target_price"),
                "stop_price": r.get("stop_price"),
                "_src": "light_score",
            }
            if len(by) >= 30:
                break
        except Exception as e:
            print(" skip", code, e)
    return by


def fetch_quotes_batch(symbols: list[str]) -> dict:
    """批量获取实时行情，返回 {bare_code: {fields...}}，失败时返回空 dict"""
    try:
        from enriched_data import get_quotes_batch

        raw = get_quotes_batch(symbols)
        if not raw:
            print("  [WARN] Tencent API 返回空，行情数据可能为旧")
            return {}
        print(f"  实时行情: {len(raw)}/{len(symbols)} 只有数据")
        return raw
    except Exception as e:
        print(f"  [WARN] Tencent API 异常: {e}，行情数据可能为旧")
        return {}


def fill_quote(row: dict, qs: dict, imap: dict) -> dict:
    """将实时行情、行业信息填入单行"""
    nr = dict(row)
    code = bare(row.get("symbol"))
    # 实时行情（优先覆盖）
    q = qs.get(code) or qs.get(f"sh{code}") or qs.get(f"sz{code}") or {}
    if q:
        nr["price"] = q.get("price")
        nr["change_pct"] = q.get("change_pct")
        nr["active_buy_ratio"] = q.get("active_buy_ratio")
        nr["turnover"] = q.get("turnover")
    else:
        print(f"  [WARN] {code} {row.get('name','')} 无实时行情")
    # 行业
    meta = imap.get(code) or {}
    nr.setdefault("name", meta.get("name") or nr.get("name"))
    nr["industry"] = meta.get("industry") or meta.get("industry_l3")
    nr["industry_l1"] = meta.get("industry_l1")
    nr["sector"] = nr.get("sector") or nr.get("industry")
    nr.pop("_src", None)
    return nr


def main() -> int:
    by = harvest()
    print(f"harvested scored={len(by)}")
    if len(by) < 10:
        by = light_fill(by, 10 - len(by))
        print(f"after light_fill scored={len(by)}")

    # 三路融合综合排名（模型分 + 资金流 + 板块热度）
    ranked = compute_fusion(list(by.values()))
    top10_raw = ranked[:10]

    # 今日推荐（门控后）对照
    rec_path = ROOT / "output/daily_recommend.json"
    picks_path = ROOT / "output/morning_live_picks.json"
    recommend_rows = []
    asof = time.strftime("%Y-%m-%d %H:%M:%S")
    if picks_path.exists():
        try:
            mp = json.loads(picks_path.read_text(encoding="utf-8"))
            if str(mp.get("asof") or "").startswith(time.strftime("%Y-%m-%d")):
                recommend_rows = mp.get("picks") or []
                asof = mp.get("asof") or asof
        except Exception:
            pass
    if not recommend_rows and rec_path.exists():
        d = json.loads(rec_path.read_text(encoding="utf-8"))
        recommend_rows = (d.get("recommendations") or [])[: int(d.get("recommend_top_n") or 2)]
        if d.get("generated_at") and str(d.get("generated_at")).startswith(time.strftime("%Y-%m-%d")):
            asof = d.get("generated_at") or asof
    recommend_rows_raw = [
        {**dict(x), "symbol": bare(x.get("symbol")), "score": float(x.get("score") or 0)}
        for x in recommend_rows
        if x.get("symbol")
    ]

    # ===== 一次性拉取实时行情（避免两次独立调用导致数据不一致）=====
    all_symbols = list(dict.fromkeys([r["symbol"] for r in top10_raw] + [r["symbol"] for r in recommend_rows_raw]))
    qs = fetch_quotes_batch(all_symbols)

    # 加载行业映射（一次）
    imap = {}
    try:
        imap = json.loads((ROOT / "data/stock_industry_map.json").read_text(encoding="utf-8"))
    except Exception:
        pass

    # 填充 Top10
    top10 = [fill_quote(r, qs, imap) for r in top10_raw]
    for i, r in enumerate(top10, 1):
        r["rank"] = i

    # 填充推荐对照
    recommend_rows = [fill_quote(r, qs, imap) for r in recommend_rows_raw]

    payload = {
        "asof": asof,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mode": "fusion_3way",
        "note": (
            "09:35 终选候选，按三路融合综合分降序取前10："
            "权重[模型分vm25]*归一化 + 权重[主力净流入] + 权重[板块热度]，"
            "权重来自 model_weights.json（IC 反馈动态调整）"
        ),
        "items": top10,
        "recommend_compare": recommend_rows,
        "n": len(top10),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved", OUT)
    print("TOP10:")
    for r in top10:
        print(
            f"  #{r['rank']} {r.get('symbol')} {r.get('name')} "
            f"fusion={r.get('_fusion_weight'):.4f} score={r.get('score'):.4f} "
            f"chg={r.get('change_pct')}"
        )
    print("RECOMMEND:")
    for r in recommend_rows:
        print(
            f"  {r.get('symbol')} {r.get('name')} score={float(r.get('score') or 0):.4f} "
            f"chg={r.get('change_pct')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
