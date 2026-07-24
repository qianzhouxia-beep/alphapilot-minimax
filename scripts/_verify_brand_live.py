#!/usr/bin/env python3
import json
import re
import urllib.request
from PIL import Image
from io import BytesIO

BASE = "https://alphapilot.api-tokenmaster.com"


def get(path: str):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "alphapilot-verify", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read(), dict(r.headers)


html, _ = get("/cn/")
text = html.decode("utf-8", "ignore")
print("has_VM2.5", "VM2.5" in text)
print("has_信心分", "信心分" in text)
print("has_brand-logo", "brand-logo.png" in text)
print("has_old_V18", "V18" in text)

raw, hdr = get("/brand-logo.png")
im = Image.open(BytesIO(raw))
print("brand_logo_bytes", len(raw), "size", im.size, "wide", im.size[0] > im.size[1] * 2)

rec = json.loads(urllib.request.urlopen(BASE + "/api/v1/cn/recommend", timeout=30).read())
print("api", rec.get("pipeline_version"), rec.get("model_version"), (rec.get("stats") or {}).get("score_scale"))
print("OK")
