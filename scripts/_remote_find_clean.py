#!/usr/bin/env python3
from pathlib import Path
import py_compile

root = Path("/home/ubuntu/alphapilot")
for p in sorted(root.glob("ml_screener.py*")) + sorted(root.glob("recommend.py*")):
    try:
        py_compile.compile(str(p), doraise=True)
        print("OK", p.name, p.stat().st_size)
    except Exception as e:
        print("FAIL", p.name, p.stat().st_size, str(e)[:120])
