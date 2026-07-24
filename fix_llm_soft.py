#!/usr/bin/env python3
from pathlib import Path
p = Path("/home/ubuntu/alphapilot/alphapilot_pipeline_v3.py")
src = p.read_text(encoding="utf-8")
bak = Path("/home/ubuntu/alphapilot/alphapilot_pipeline_v3.py.bak_llm_soft")
if not bak.exists():
    bak.write_text(src, encoding="utf-8")
old = '''        if not news:
            return None'''
new = '''        if not news:
            # soft-fail: keep stock, neutral sentiment (avoid emptying funnel)
            return (sym, 0.0, "无新闻-中性放行")'''
if old in src and "无新闻-中性放行" not in src:
    src = src.replace(old, new, 1)
    p.write_text(src, encoding="utf-8")
    print("pipeline LLM soft-fail patched")
else:
    print("pipeline LLM patch skipped/already")