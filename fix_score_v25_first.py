#!/usr/bin/env python3
# Fix ml_screener.score_stock: route v25 before V16 feature build (avoids valid_scored=0).
from pathlib import Path
path = Path("/home/ubuntu/alphapilot/ml_screener.py")
src = path.read_text(encoding="utf-8")
bak = Path("/home/ubuntu/alphapilot/ml_screener.py.bak_score_v25_first")
if not bak.exists():
    bak.write_text(src, encoding="utf-8")

marker = "V25_SCORE_FIRST"
if marker in src:
    print("already patched")
else:
    old = '''    def score_stock(self, kline_df: pd.DataFrame, symbol: str = "", fundamentals: dict = None,
                    has_forecast: bool = False, yjyg_max_change: float = 0.0,
                    buy_inst_count: int = 0, has_lhb: bool = False,
                    margin_balance: float = 0.0, margin_buy: float = 0.0,
                    sector_heat: float = 0.0) -> dict:
        """对单只股票进行评分"""
        if not self.model_loaded and not self.load_model():
            return {"error": "model_not_loaded"}

        feats = build_full_features('''
    # more tolerant: find score_stock and inject early return
    import re
    pat = r'(def score_stock\(self[\s\S]*?if not self\.model_loaded and not self\.load_model\(\):\n\s*return \{"error": "model_not_loaded"\}\n)'
    m = re.search(pat, src)
    if not m:
        print("pattern not found, trying simpler inject")
        needle = 'if not self.model_loaded and not self.load_model():\n            return {"error": "model_not_loaded"}'
        inject = needle + f'''

        # {marker}: VM2.5 uses features_v2 path; do not depend on V16 build_full_features
        if self.model_version in ("v25", "vm25", "vm2.5"):
            return self._score_v25(kline_df, symbol, sector_heat)
'''
        if needle in src and marker not in src:
            src = src.replace(needle, inject, 1)
            path.write_text(src, encoding="utf-8")
            print("patched simpler")
        else:
            print("FAIL patch")
            raise SystemExit(1)
    else:
        inject = m.group(1) + f'''
        # {marker}: VM2.5 uses features_v2 path; do not depend on V16 build_full_features
        if self.model_version in ("v25", "vm25", "vm2.5"):
            return self._score_v25(kline_df, symbol, sector_heat)
'''
        src = src[:m.start()] + inject + src[m.end():]
        path.write_text(src, encoding="utf-8")
        print("patched regex")

import py_compile
py_compile.compile(str(path), doraise=True)
print("COMPILE_OK")