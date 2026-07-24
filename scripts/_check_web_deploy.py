#!/usr/bin/env python3
import json
import urllib.request
from pathlib import Path

root = Path("/home/ubuntu/alphapilot")
p = root / "output/daily_recommend.json"
print("file", p, "size", p.stat().st_size if p.exists() else None)
if p.exists():
    d = json.loads(p.read_text(encoding="utf-8"))
    print("file_keys", list(d.keys()))
    print("file_generated", d.get("generated_at") or d.get("run_at"))
    print("file_pipeline", d.get("pipeline_version"))
    print("file_n", len(d.get("recommendations") or []))
    print("file_body", json.dumps(d, ensure_ascii=False)[:500])

for url in (
    "http://localhost:8000/api/v1/cn/recommend",
    "http://127.0.0.1:8000/api/v1/cn/recommend",
):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            d = json.loads(r.read().decode())
        print("api", url)
        print("  keys", list(d.keys())[:25])
        print("  generated", d.get("generated_at") or d.get("run_at") or d.get("updated_at"))
        print("  pipeline", d.get("pipeline_version"))
        print("  model", d.get("model") or d.get("model_version"))
        print("  exposure", d.get("position_exposure"))
        recs = d.get("recommendations") or []
        print("  n", len(recs))
        for x in recs[:5]:
            print("   ", x.get("symbol"), x.get("name"), x.get("score"))
    except Exception as e:
        print("api_fail", url, e)

# code wire
rec = (root / "recommend.py").read_text(encoding="utf-8", errors="replace")
print("code_load_v25", 'load_model(version="v25")' in rec)
print("ml_has_load_v25", "def _load_v25" in (root / "ml_screener.py").read_text(encoding="utf-8", errors="replace"))
