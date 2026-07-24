#!/usr/bin/env python3
from pathlib import Path

roots = [
    Path("/home/ubuntu/alphapilot/frontend_out"),
    Path("/home/ubuntu/alphapilot"),
    Path("/var/www"),
]
keys = ("score_pct", "score_label", "VM2", "评分", "model_version", "pipeline_version")
for root in roots:
    if not root.exists():
        continue
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in {".js", ".jsx", ".tsx", ".ts", ".vue", ".html", ".css"}:
            continue
        if p.stat().st_size > 8_000_000:
            continue
        try:
            t = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        hits = [k for k in keys if k in t]
        if hits and "node_modules" not in str(p):
            print(f"{p} :: {hits} :: size={p.stat().st_size}")
