#!/usr/bin/env python3
"""Verify API score display fields and frontend copy."""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8000"


def get(path: str):
    with urllib.request.urlopen(BASE + path, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> None:
    rec = get("/api/v1/cn/recommend")
    print("meta", {
        "pipeline_version": rec.get("pipeline_version"),
        "model_version": rec.get("model_version"),
        "position_exposure": rec.get("position_exposure"),
        "score_scale": (rec.get("stats") or {}).get("score_scale"),
        "n": len(rec.get("recommendations") or []),
    })

    # synthesize normalize check against live module
    import sys
    sys.path.insert(0, "/home/ubuntu/alphapilot")
    import api_server

    sample = api_server._normalize_recommend_item({"symbol": "sz000001", "name": "测试", "score": 0.35})
    print("normalize_0.35", {
        "confidence_score": sample["confidence_score"],
        "model_proba": sample["model_proba"],
        "score_pct": sample["score_pct"],
    })
    assert sample["confidence_score"] == 91, sample
    assert abs(sample["model_proba"] - 0.35) < 1e-6

    html = urllib.request.urlopen(BASE + "/cn/", timeout=20).read().decode("utf-8", "ignore")
    for needle in ("VM2.5", "信心分", "模型概率"):
        print(f"html_has_{needle}", needle in html)
        assert needle in html, needle

    # old misleading labels should be gone from landing copy
    for bad in ("V18", "V1.9"):
        print(f"html_has_{bad}", bad in html)

    print("OK")


if __name__ == "__main__":
    main()
