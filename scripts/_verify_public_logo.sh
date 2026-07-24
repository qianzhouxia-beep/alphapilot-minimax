#!/bin/bash
set -euo pipefail
BASE=https://alphapilot.api-tokenmaster.com

echo "=== HTML brand strings ==="
curl -sS -m 25 -L "$BASE/cn/" -o /tmp/ap_cn.html
grep -oE 'VM2.5|信心分|模型概率|V18|V1\.9|logo\.png' /tmp/ap_cn.html | sort | uniq -c || true

echo "=== logo.png headers/size ==="
curl -sSI -m 20 "$BASE/logo.png" | head -20
curl -sS -m 20 -o /tmp/ap_logo.png -w "bytes=%{size_download} http=%{http_code}\n" "$BASE/logo.png"
python3 - <<'PY'
from PIL import Image
im=Image.open('/tmp/ap_logo.png')
print('logo_size', im.size, 'mode', im.mode)
# expect new logo aspect ~ wide wordmark
print('wide_wordmark', im.size[0] > im.size[1]*2)
PY

echo "=== API meta ==="
curl -sS -m 20 "$BASE/api/v1/cn/recommend" | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d.get("pipeline_version"),d.get("model_version"),(d.get("stats") or {}).get("score_scale"))'
