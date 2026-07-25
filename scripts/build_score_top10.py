#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构建「评分 Top10」榜：只按 score 降序取前 10，不加资金/板块等门槛。

数据来源优先级：
1) output/daily_recommend_full.json / recommend 全量缓存（若有）
2) 各 output/*.json 里带 score 的候选并集
3) 不足 10 只时，对量价金叉池轻量补评分
"""
from __future__ import annotations

import json
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


def bare(s: str) -> str:
    x = str(s or "")
    for p in ("sh", "sz", "bj", "SH", "SZ", "BJ"):
        x = x.replace(p, "")
    return x[-6:] if len(x) >= 6 else x


def harvest() -> dict[str, dict]:
    by: dict[str, dict] = {}
    paths = [
        ROOT / "output/daily_recommend_full.json",
        ROOT / "output/debate_v2_result.json",
        ROOT / "output/daily_recommend.json",
        ROOT / "recommend_cache.json",
    ]
    paths += sorted((ROOT / "output").glob("*.json"))
    for p in paths:
        if not p.exists() or p.name == "score_top10.json":
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
            if not code:
                continue
            sc = float(it.get("score") or it.get("lgb_score") or it.get("model_proba") or 0)
            if sc <= 0:
                continue
            prev = by.get(code)
            if prev is None or sc > float(prev.get("score") or 0):
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

    ranked = sorted(by.values(), key=lambda x: -float(x.get("score") or 0))
    top10_raw = ranked[:10]

    # 今日推荐（门控后）对照
    rec_path = ROOT / "output/daily_recommend.json"
    picks_path = ROOT / "output/morning_live_picks.json"
    recommend_rows = []
    if picks_path.exists():
        try:
            mp = json.loads(picks_path.read_text(encoding="utf-8"))
            if str(mp.get("asof") or "").startswith(time.strftime("%Y-%m-%d")):
                recommend_rows = mp.get("picks") or []
        except Exception:
            pass
    if not recommend_rows and rec_path.exists():
        d = json.loads(rec_path.read_text(encoding="utf-8"))
        recommend_rows = (d.get("recommendations") or [])[: int(d.get("recommend_top_n") or 2)]
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
        "asof": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mode": "score_only_no_threshold",
        "note": "按 VM2.5/缓存 score 降序取前10，不经资金/板块硬门槛",
        "items": top10,
        "recommend_compare": recommend_rows,
        "n": len(top10),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved", OUT)
    print("TOP10:")
    for r in top10:
        print(
            f"  #{r['rank']} {r.get('symbol')} {r.get('name')} score={r.get('score'):.4f} "
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
