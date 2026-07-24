#!/usr/bin/env python3
import json
from pathlib import Path

p = Path("/home/ubuntu/alphapilot/output/daily_recommend.json")
d = json.loads(p.read_text(encoding="utf-8"))
recs = d.get("recommendations") or []
print("file", p, "size", p.stat().st_size)
print("pipeline_version", d.get("pipeline_version"))
print("model_version", d.get("model_version"))
print("asof", d.get("asof") or d.get("date") or d.get("signal_date") or d.get("asof_date"))
print("updated_at", d.get("updated_at") or d.get("generated_at") or d.get("timestamp"))
print("total_candidates", d.get("total_candidates"))
print("recommend_top_n", d.get("recommend_top_n"), "pool_n", d.get("recommend_pool_n"))
print("position_exposure", d.get("position_exposure"), "permission", d.get("permission"))
print("n_recs", len(recs))
for i, r in enumerate(recs[:15], 1):
    print(
        f"{i}. {r.get('symbol')} {r.get('name')} "
        f"score={r.get('score') or r.get('model_proba')} "
        f"pats={r.get('launch_patterns')} "
        f"main_net={r.get('main_net') or r.get('live_main_net')}"
    )
if not recs:
    print("EMPTY", {k: d.get(k) for k in ("empty_reason", "note", "error", "message")})
