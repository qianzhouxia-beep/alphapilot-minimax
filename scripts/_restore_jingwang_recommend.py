#!/usr/bin/env python3
"""Restore 603228 recommend after accidental empty overwrite."""
import json
import time
from pathlib import Path

ROOT = Path("/home/ubuntu/alphapilot")
q = json.loads((ROOT / "output/enriched_cache/q_603228.json").read_text(encoding="utf-8"))
probe = json.loads((ROOT / "output/funnel_survivor_probe.json").read_text(encoding="utf-8"))
surv = (probe.get("survivors") or [{}])[0]
price = float(q.get("price") or 71.7)
item = {
    "symbol": "603228",
    "name": "景旺电子",
    "score": float(surv.get("score") or 0.5881),
    "lgb_score": float(surv.get("score") or 0.5881),
    "sector_heat": 0.5,
    "buy_price": round(price * 0.977, 2),
    "target_price": round(price * 1.016, 2),
    "stop_price": round(price * 0.948, 2),
    "price": price,
    "change_pct": float(q.get("change_pct") or 0),
    "active_buy_ratio": q.get("active_buy_ratio"),
    "turnover": q.get("turnover"),
    "volume_ratio": q.get("volume_ratio"),
    "main_net_5d": surv.get("main_net_5d"),
    "money_phase": "accumulation",
    "money_phase_label": surv.get("money_phase") or "📥 吸筹",
    "industry": "印制电路板",
    "industry_l1": "电子",
    "position_exposure": 0.25,
    "exec_hint": "buy_t1_open_skip_if_limit; sell_t2_close",
}
out = {
    "run_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    "recommendations": [item],
    "pipeline_version": "v3.1_funnel_gated",
    "model_version": "v25",
    "total_candidates": 1,
    "position_exposure": 0.25,
    "recommend_top_n": 1,
    "recommend_pool_n": 10,
    "exposure_mode": "permission_v1",
    "market_env_flags": {
        "tech_weak": True,
        "tech_severe": True,
        "market_weak": True,
        "market_severe": True,
        "market_crash_day": True,
        "permission_on": True,
        "rotation_dead": False,
    },
    "permission": {
        "permission_on": True,
        "up3_count": 106,
        "n_sustained_in": 1,
        "rotation_dead": False,
    },
    "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    "restored_note": "restored after bootstrap empty; pool_n=10 needs full recommend to fill",
}
path = ROOT / "output/daily_recommend.json"
path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print("restored", path, "n=1 pool_n=10 trade_n=1")
