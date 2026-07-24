#!/usr/bin/env python3
import json, subprocess, sys
from pathlib import Path
ROOT = Path("/home/ubuntu/alphapilot")
path = ROOT / "ml_screener.py"
src = path.read_text(encoding="utf-8")
bak = ROOT / "ml_screener.py.bak_before_v25"
if not bak.exists():
    bak.write_text(src, encoding="utf-8")
if "_load_v25" not in src:
    needle = 'elif self.model_version == "v20":'
    insert = 'elif self.model_version in ("v25", "vm25", "vm2.5"):\n            return self._load_v25()\n        ' + needle
    src = src.replace(needle, insert, 1)
    method = """
    def _load_v25(self) -> bool:
        try:
            from vm25_scorer import scorer as vm25
            ok = vm25.load()
            if not ok:
                print(" V25 load failed, fallback v20")
                return self._load_v20()
            self.models = vm25.models
            self.model_loaded = True
            self.model_version = "v25"
            self._vm25 = vm25
            print(f" V25 loaded via vm25_scorer feats={len(vm25.feature_names)}")
            return True
        except Exception as e:
            print(f" V25 load error: {e}; fallback v20")
            return self._load_v20()

"""
    src = src.replace("    def _load_v20(self)", method + "    def _load_v20(self)", 1)
    if "return self._score_v25" not in src:
        parts = src.split("if feats.empty or len(feats) < 30:")
        if len(parts) >= 2:
            head, rest = parts[0], parts[1]
            sn = 'elif self.model_version == "v20":'
            si = 'elif self.model_version in ("v25", "vm25", "vm2.5"):\n            return self._score_v25(kline_df, symbol, sector_heat)\n        ' + sn
            rest = rest.replace(sn, si, 1)
            src = head + "if feats.empty or len(feats) < 30:" + rest
    score_m = """
    def _score_v25(self, kline_df, symbol, sector_heat):
        vm = getattr(self, "_vm25", None)
        if vm is None:
            from vm25_scorer import scorer as vm
            vm.load()
            self._vm25 = vm
        return vm.score(kline_df, symbol, sector_heat=sector_heat)

"""
    if "_score_v25" not in src:
        src = src.replace("    def _score_v14(self", score_m + "    def _score_v14(self", 1)
    path.write_text(src, encoding="utf-8")
r = subprocess.run([sys.executable, "-m", "py_compile", str(path)])
print("ml_screener_compile", r.returncode)
if r.returncode != 0:
    sys.exit(1)
rp = ROOT / "recommend.py"
rs = rp.read_text(encoding="utf-8")
rb = ROOT / "recommend.py.bak_before_v25"
if not rb.exists():
    rb.write_text(rs, encoding="utf-8")
rs2 = rs.replace('load_model(version="v20")', 'load_model(version="v25")')
rs2 = rs2.replace("load_model(version='v20')", "load_model(version='v25')")
if rs2 != rs:
    rp.write_text(rs2, encoding="utf-8")
    print("recommend->v25")
else:
    print("recommend unchanged or already v25")
print("WIRE_OK")