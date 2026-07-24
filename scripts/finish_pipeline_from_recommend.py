#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Continue V3 funnel after recommend.py (reuse existing GC pool + scores)."""
from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path("/home/ubuntu/alphapilot")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from alphapilot_pipeline_v3 import (  # noqa: E402
    apply_money_gate,
    apply_market_env,
    apply_sector_rotation,
    llm_review,
    apply_s2_weight,
    log,
)


def main() -> int:
    rec_path = ROOT / "output/daily_recommend.json"
    gc_path = ROOT / "output/volume_gc_pool.json"
    if not rec_path.exists():
        log("missing daily_recommend.json")
        return 1
    recs = json.loads(rec_path.read_text(encoding="utf-8"))
    items = recs.get("recommendations") or []
    log(f"loaded recommendations: {len(items)}")

    gc_set = set()
    if gc_path.exists():
        try:
            gc_set = set(json.loads(gc_path.read_text(encoding="utf-8")))
        except Exception:
            gc_set = set()

    def _in_gc(it: dict) -> bool:
        if not gc_set:
            return True
        sym = str(it.get("symbol") or "")
        return sym in gc_set or sym[-6:] in gc_set or f"sh{sym[-6:]}" in gc_set or f"sz{sym[-6:]}" in gc_set

    # 若上次已截成极少票，仅当「更大缓存 ∩ 金叉池」非空时才回补，避免把池子清空
    if len(items) < 15:
        for alt in (
            ROOT / "output/daily_recommend_full.json",
            ROOT / "output/debate_v2_result.json",
            ROOT / "recommend_cache.json",
        ):
            if not alt.exists():
                continue
            try:
                ad = json.loads(alt.read_text(encoding="utf-8"))
                alt_items = ad.get("recommendations") or ad.get("items") or []
            except Exception:
                continue
            if not isinstance(alt_items, list) or len(alt_items) <= len(items):
                continue
            inter = [it for it in alt_items if _in_gc(it)]
            if len(inter) > len([it for it in items if _in_gc(it)]):
                log(
                    f"bootstrap candidates from {alt.name}: "
                    f"{len(items)} → {len(alt_items)} (gc∩={len(inter)})"
                )
                items = alt_items
                break

    if gc_set:
        before = len(items)
        items = [it for it in items if _in_gc(it)]
        log(f"量价金叉过滤: {before} → {len(items)} (pool={len(gc_set)})")
        if not items:
            log("⛔ 金叉过滤后为空，不回退")
            items = []

    # 评分榜（无门槛）：与门控推荐分离；优先全量脚本，失败则用当前列表
    try:
        import subprocess

        subprocess.check_call(
            [sys.executable, str(ROOT / "scripts/build_score_top10.py")],
            cwd=str(ROOT),
            timeout=600,
        )
        log("score_top10 已更新（无门槛）")
    except Exception as e:
        try:
            ranked = sorted(items, key=lambda x: -float(x.get("score") or 0))[:10]
            for i, r in enumerate(ranked, 1):
                r = dict(r)
                r["rank"] = i
                ranked[i - 1] = r
            (ROOT / "output/score_top10.json").write_text(
                json.dumps(
                    {
                        "asof": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "mode": "score_only_no_threshold",
                        "items": ranked,
                        "recommend_compare": [],
                        "n": len(ranked),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            log(f"score_top10 fallback n={len(ranked)} ({e})")
        except Exception as e2:
            log(f"score_top10 跳过: {e} / {e2}")

    items = apply_money_gate(items)
    log(f"资金门控后: {len(items)}")

    items, mkt_meta = apply_market_env(items)
    log(
        f"大盘环境后: {len(items)} exposure={mkt_meta.get('position_exposure')} "
        f"pool_n={mkt_meta.get('recommend_pool_n')} trade_n={mkt_meta.get('recommend_top_n')}"
    )

    if items:
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(apply_sector_rotation, items)
                items = fut.result(timeout=90)
        except Exception as e:
            log(f"板块轮动跳过: {e}")

    try:
        from caomujiebing_factor import apply_caomujiebing_soft_boost

        items = apply_caomujiebing_soft_boost(items, mkt_meta=mkt_meta)
        log(f"草木皆兵软加分后: {len(items)}")
    except Exception as e:
        log(f"草木皆兵跳过: {e}")

    pool_n = int(mkt_meta.get("recommend_pool_n") or 50)
    trade_n = int(mkt_meta.get("recommend_top_n") or 2)
    top_pool = items[: max(pool_n, 0)]
    if top_pool:
        top_pool = llm_review(top_pool)
        top_pool = apply_s2_weight(top_pool)

    def _limit_frac(sym: str) -> float:
        s = str(sym or "").replace("sh", "").replace("sz", "")[-6:]
        if s.startswith(("300", "301", "688")):
            return 0.20
        return 0.10

    exec_notes = []
    filtered = []
    for it in top_pool:
        chg = it.get("change_pct") or it.get("pct_chg") or it.get("signal_chg")
        try:
            chg_f = float(chg) / (100.0 if abs(float(chg)) > 1 else 1.0) if chg is not None else None
        except Exception:
            chg_f = None
        lim = _limit_frac(it.get("symbol", ""))
        if chg_f is not None and chg_f >= lim * 0.97:
            exec_notes.append({"symbol": it.get("symbol"), "reason": "signal_near_limit", "chg": chg_f})
            continue
        it = dict(it)
        it["position_exposure"] = mkt_meta.get("position_exposure", 1.0)
        it["exec_hint"] = "buy_t1_open_skip_if_limit; sell_t2_close"
        filtered.append(it)
    top_pool = filtered[:pool_n] if pool_n > 0 else []

    recs["recommendations"] = top_pool
    recs["pipeline_version"] = "v3.1_funnel_gated"
    recs["total_candidates"] = len(items)
    recs["position_exposure"] = mkt_meta.get("position_exposure", 1.0)
    recs["recommend_top_n"] = trade_n
    recs["recommend_pool_n"] = pool_n
    recs["market_env_flags"] = mkt_meta.get("flags") or {}
    recs["permission"] = mkt_meta.get("permission")
    recs["exposure_mode"] = mkt_meta.get("exposure_mode")
    recs["exec_excluded_near_limit"] = exec_notes
    recs["generated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    recs["model_version"] = "v25"
    rec_path.write_text(json.dumps(recs, ensure_ascii=False, indent=2), encoding="utf-8")
    log(
        f"saved {rec_path} pool={len(top_pool)} pool_n={pool_n} "
        f"trade_n={trade_n} exposure={recs['position_exposure']}"
    )
    log(f"Trade Top{trade_n}: {[x.get('name') for x in top_pool[:trade_n]]}")
    log(f"Pool: {[x.get('name') for x in top_pool]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
