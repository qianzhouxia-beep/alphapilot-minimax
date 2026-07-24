#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Restore ml_screener + recommend from known-good remote backups, ensure v25 wire."""
from __future__ import annotations

import os
import py_compile
import shutil
import sys
from pathlib import Path

ROOT = Path("/home/ubuntu/alphapilot")
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))


def restore_recommend() -> None:
    bak = ROOT / "recommend.py.bak_before_v25"
    dst = ROOT / "recommend.py"
    shutil.copy2(bak, dst)
    src = dst.read_text(encoding="utf-8")
    src = src.replace('load_model(version="v20")', 'load_model(version="v25")')
    src = src.replace("load_model(version='v20')", "load_model(version='v25')")
    dst.write_text(src, encoding="utf-8")
    py_compile.compile(str(dst), doraise=True)
    assert 'load_model(version="v25")' in src
    assert "def run_daily_recommend" in src
    print("OK recommend.py")


def restore_screener() -> None:
    # Prefer pre-corruption backup that already has v25 methods
    candidates = [
        ROOT / "ml_screener.py.bak_before_v25",
        ROOT / "ml_screener.py.bak_score_v25_first",
        ROOT / "ml_screener.py.bak_ap_0718",
    ]
    bak = next((p for p in candidates if p.exists() and p.stat().st_size > 12000), None)
    if bak is None:
        raise SystemExit("no usable ml_screener backup")
    dst = ROOT / "ml_screener.py"
    shutil.copy2(bak, dst)
    src = dst.read_text(encoding="utf-8")

    # Ensure v25 load branch
    if 'in ("v25", "vm25", "vm2.5")' not in src and '== "v25"' not in src:
        src = src.replace(
            '        elif self.model_version == "v20":\n            return self._load_v20()',
            '        elif self.model_version in ("v25", "vm25", "vm2.5"):\n'
            "            return self._load_v25()\n"
            '        elif self.model_version == "v20":\n'
            "            return self._load_v20()",
            1,
        )

    if "def _load_v25" not in src:
        method = '''
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
            self.meta = getattr(vm25, "meta", None)
            print(f" V25 loaded via vm25_scorer feats={len(vm25.feature_names)}")
            return True
        except Exception as e:
            print(f" V25 load error: {e}; fallback v20")
            return self._load_v20()

    def _score_v25(self, kline_df, symbol, sector_heat):
        vm = getattr(self, "_vm25", None)
        if vm is None:
            from vm25_scorer import scorer as vm
            vm.load()
            self._vm25 = vm
        return vm.score(kline_df, symbol, sector_heat=sector_heat)

'''
        src = src.replace("    def _load_v20(self)", method + "    def _load_v20(self)", 1)

    if "return self._score_v25" not in src:
        old = '        if self.model_version.startswith("v18") or self.model_version.startswith("v19"):'
        new = (
            '        if self.model_version in ("v25", "vm25", "vm2.5"):\n'
            "            return self._score_v25(kline_df, symbol, sector_heat)\n" + old
        )
        if old in src:
            src = src.replace(old, new, 1)

    if "screener = MLScreener" not in src:
        # bak may already have screener at bottom
        if "screener =" not in src:
            src = src.rstrip() + '\n\nscreener = MLScreener(model_version="v25")\n'

    # Prefer default global to v25
    src = src.replace('MLScreener(model_version="v20")', 'MLScreener(model_version="v25")')

    dst.write_text(src, encoding="utf-8")
    py_compile.compile(str(dst), doraise=True)

    # sanity: _load_v20 must not recurse into score_stock
    body = src.split("def _load_v20")[1].split("def ")[0]
    if "build_full_features" in body and "v20_meta" not in body:
        raise SystemExit("_load_v20 still looks corrupted")
    print("OK ml_screener.py from", bak.name)


def smoke() -> None:
    from ml_screener import screener

    ok = screener.load_model(version="v25")
    print("smoke load v25", ok, "version", screener.model_version, "models", len(screener.models))


if __name__ == "__main__":
    restore_recommend()
    restore_screener()
    smoke()
    print("RESTORE_DONE")
