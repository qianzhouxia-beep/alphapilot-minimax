#!/usr/bin/env python3
import os
import sys
from pathlib import Path

ROOT = Path("/home/ubuntu/alphapilot")
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
from ml_screener import screener

ok = screener.load_model(version="v25")
print("ok", ok, "ver", screener.model_version, "n", len(screener.models))
