#!/usr/bin/env python3
from pathlib import Path
import py_compile
import shutil

ROOT = Path("/home/ubuntu/alphapilot")
bak = ROOT / "recommend.py.bak_before_v25"
dst = ROOT / "recommend.py"
shutil.copy2(bak, dst)
src = dst.read_text(encoding="utf-8")
src = src.replace('load_model(version="v20")', 'load_model(version="v25")')
src = src.replace("load_model(version='v20')", "load_model(version='v25')")
dst.write_text(src, encoding="utf-8")
py_compile.compile(str(dst), doraise=True)
print("recommend restored+v25", 'version="v25"' in src)
