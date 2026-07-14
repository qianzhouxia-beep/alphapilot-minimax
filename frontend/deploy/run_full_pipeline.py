#!/usr/bin/env python3
"""run_full_pipeline.py - 全量扫描+缓存写入 (无缓冲输出)"""
import sys, os, json
from datetime import datetime
from recommend import run_daily_recommend

# 无缓冲输出
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

os.chdir("/home/ubuntu/alphapilot")

print(f"[{datetime.now().isoformat()}] Starting full pipeline...")
r = run_daily_recommend(top_n=20)
items = r.get("recommendations", [])

print(f"[{datetime.now().isoformat()}] DONE: {len(items)} recommendations")

# 只写报错不写报错，确保 output 目录存在
os.makedirs("output", exist_ok=True)

with open("recommend_cache.json", "w", encoding="utf-8") as f:
    json.dump(r, f, ensure_ascii=False, default=str)
print(f"[{datetime.now().isoformat()}] CACHE saved: recommend_cache.json ({len(str(r))//1024}KB)")

# 也写到 output 目录保持兼容
with open("output/daily_recommend.json", "w", encoding="utf-8") as f:
    json.dump(r, f, ensure_ascii=False, default=str)
