#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import py_compile
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_any(path: Path) -> str:
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    if len(raw) > 4 and raw[1] == 0 and raw[3] == 0:
        return raw.decode("utf-16-le")
    return raw.decode("utf-8")


def main() -> int:
    bak = ROOT / "ml_screener.py.bak_before_p0"
    if not bak.exists():
        raise SystemExit("missing bak_before_p0")
    src = read_any(bak)

    # Split glued comment + ALL_FEATURES (UTF-16 conversion artifact)
    lines = []
    for line in src.splitlines():
        if "ALL_FEATURES" in line and not line.lstrip().startswith("ALL_FEATURES"):
            idx = line.find("ALL_FEATURES")
            left = line[:idx].rstrip()
            if left:
                lines.append(left)
            lines.append(line[idx:])
        else:
            lines.append(line)
    src2 = "\n".join(lines) + "\n"

    if "_load_v25" not in src2:
        src2 = src2.replace(
            '        elif self.model_version == "v20":\n            return self._load_v20()',
            '        elif self.model_version in ("v25", "vm25", "vm2.5"):\n'
            "            return self._load_v25()\n"
            '        elif self.model_version == "v20":\n'
            "            return self._load_v20()",
            1,
        )
        method = '''
    def _load_v25(self) -> bool:
        """Load VM2.5 via shared scorer (features_v2 + side data)."""
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
        src2 = src2.replace("    def _load_v20(self)", method + "    def _load_v20(self)", 1)

    if "return self._score_v25" not in src2:
        old = '        if self.model_version.startswith("v18") or self.model_version.startswith("v19"):'
        new = (
            '        if self.model_version in ("v25", "vm25", "vm2.5"):\n'
            "            return self._score_v25(kline_df, symbol, sector_heat)\n"
            '        if self.model_version.startswith("v18") or self.model_version.startswith("v19"):'
        )
        if old in src2:
            src2 = src2.replace(old, new, 1)

    out = ROOT / "ml_screener.py"
    out.write_text(src2, encoding="utf-8", newline="\n")
    py_compile.compile(str(out), doraise=True)
    print("REPAIR_OK", "v25=", "_load_v25" in src2)
    for i, line in enumerate(src2.splitlines()[17:26], start=18):
        print(f"{i}: {line[:110]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
