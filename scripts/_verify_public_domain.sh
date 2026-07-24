#!/bin/bash
set -euo pipefail
BASE="${1:-https://alphapilot.api-tokenmaster.com}"

echo "=== GET $BASE/cn/ ==="
curl -sS -m 20 -L "$BASE/cn/" -o /tmp/ap_cn.html
grep -oE 'VM2.5|信心分|模型概率|非百分制|V18|V1\.9' /tmp/ap_cn.html | sort | uniq -c || true

echo "=== GET $BASE/api/v1/cn/recommend ==="
curl -sS -m 20 "$BASE/api/v1/cn/recommend" -o /tmp/ap_rec.json
python3 - <<'PY'
import json
d=json.load(open("/tmp/ap_rec.json"))
print({
  "pipeline_version": d.get("pipeline_version"),
  "model_version": d.get("model_version"),
  "position_exposure": d.get("position_exposure"),
  "score_scale": (d.get("stats") or {}).get("score_scale"),
  "n": len(d.get("recommendations") or []),
})
PY
