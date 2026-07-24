#!/usr/bin/env python3
import json
import os
from pathlib import Path

ROOT = Path("/home/ubuntu/alphapilot")
os.chdir(ROOT)
rec = json.loads((ROOT / "output/daily_recommend.json").read_text(encoding="utf-8"))
print(
    "recommend",
    {
        "n": len(rec.get("recommendations") or []),
        "expo": rec.get("position_exposure"),
        "model": rec.get("model_version"),
        "gen": rec.get("generated_at"),
        "pipe": rec.get("pipeline_version"),
    },
)
import pandas as pd

p = ROOT / "data/kline_cache/kline_all.parquet"
if not p.exists():
    p = ROOT / "kline_all.parquet"
df = pd.read_parquet(p, columns=["date"])
print("kline_max", str(df["date"].max())[:10])
print("has_v25", (ROOT / "models").exists())
print("has_sleeve", (ROOT / "weak_rotation_sleeve.py").exists())
print("has_pipeline", (ROOT / "alphapilot_pipeline_v3.py").exists())
