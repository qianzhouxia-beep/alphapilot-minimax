#!/usr/bin/env python3
"""Fill thin-book pool toward Top10 from GC ∩ scored caches / light rescore."""
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


def bare(s: str) -> str:
    s = str(s or "")
    for p in ("sh", "sz", "bj", "SH", "SZ", "BJ"):
        s = s.replace(p, "")
    return s[-6:]


def main() -> int:
    rec_path = ROOT / "output/daily_recommend.json"
    gc_path = ROOT / "output/volume_gc_pool.json"
    recs = json.loads(rec_path.read_text(encoding="utf-8"))
    items = list(recs.get("recommendations") or [])
    gc = set(json.loads(gc_path.read_text(encoding="utf-8"))) if gc_path.exists() else set()
    gc_b = {bare(x) for x in gc}
    pool_n = int(recs.get("recommend_pool_n") or 10)
    trade_n = int(recs.get("recommend_top_n") or 1)

    by = {bare(it.get("symbol")): it for it in items}

    # harvest scored names from any large json
    for p in sorted((ROOT / "output").glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(d, list):
            arr = d
        elif isinstance(d, dict):
            arr = d.get("recommendations") or d.get("items")
        else:
            continue
        if not isinstance(arr, list):
            continue
        for it in arr:
            if not isinstance(it, dict):
                continue
            code = bare(it.get("symbol"))
            if not code or code not in gc_b:
                continue
            if code in by and float(by[code].get("score") or 0) >= float(it.get("score") or 0):
                continue
            by[code] = dict(it)

    merged = sorted(by.values(), key=lambda x: -float(x.get("score") or 0))
    print(f"after harvest gc-scored: {len(merged)}")

    # if still thin, light-score remaining GC with screener (cap)
    need = pool_n - len(merged)
    if need > 0:
        try:
            from ml_screener import screener
            from data_fetcher import get_kline_sina

            screener.load_model()
            have = {bare(x.get("symbol")) for x in merged}
            targets = [c for c in sorted(gc_b) if c not in have][:40]
            print(f"light score {len(targets)} gc symbols...")
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
                    merged.append(
                        {
                            "symbol": code,
                            "name": r.get("name") or code,
                            "score": sc,
                            "lgb_score": sc,
                            "buy_price": r.get("buy_price") or r.get("target_price"),
                            "target_price": r.get("target_price"),
                            "stop_price": r.get("stop_price"),
                            "on_demand_fill": True,
                        }
                    )
                except Exception as e:
                    print(" skip", code, e)
            merged.sort(key=lambda x: -float(x.get("score") or 0))
        except Exception as e:
            print("light score failed:", e)

    # run soft gates on merged for consistency
    from alphapilot_pipeline_v3 import apply_money_gate, apply_market_env, apply_sector_rotation

    gated = apply_money_gate(merged)
    gated, meta = apply_market_env(gated)
    try:
        gated = apply_sector_rotation(gated)
    except Exception as e:
        print("sector skip", e)
    try:
        from caomujiebing_factor import apply_caomujiebing_soft_boost

        gated = apply_caomujiebing_soft_boost(gated, mkt_meta=meta)
    except Exception as e:
        print("cmjb skip", e)

    pool_n = int(meta.get("recommend_pool_n") or pool_n)
    trade_n = int(meta.get("recommend_top_n") or trade_n)
    top = gated[:pool_n]
    for it in top:
        it["position_exposure"] = meta.get("position_exposure", 0.25)
        it["exec_hint"] = "buy_t1_open_skip_if_limit; sell_t2_close"

    recs["recommendations"] = top
    recs["position_exposure"] = meta.get("position_exposure", 0.25)
    recs["recommend_top_n"] = trade_n
    recs["recommend_pool_n"] = pool_n
    recs["market_env_flags"] = meta.get("flags") or recs.get("market_env_flags")
    recs["permission"] = meta.get("permission") or recs.get("permission")
    recs["exposure_mode"] = meta.get("exposure_mode") or "permission_v1"
    recs["generated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    recs["fill_note"] = f"thin_pool_fill n={len(top)}"
    rec_path.write_text(json.dumps(recs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        "saved pool",
        len(top),
        "trade",
        trade_n,
        "names",
        [x.get("name") for x in top],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
