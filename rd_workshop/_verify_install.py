#!/usr/bin/env python3
from pathlib import Path
from rd_workshop.normalize_factors import bare_code

assert bare_code("600519.SH") == "600519"
root = Path("/home/ubuntu/alphapilot")
assert (root / "rd_workshop/run_promotion_adapter.py").exists()
assert "ALPHAPILOT_MODEL_DIR" in (root / "train_v25.py").read_text(encoding="utf-8")
assert "ALPHAPILOT_MODEL_DIR" in (root / "vm25_scorer.py").read_text(encoding="utf-8")
print("vm_promotion_adapter_ok")
