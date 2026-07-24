#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sanitize UTF-16/mojibake Python files into compilable UTF-8."""
from __future__ import annotations

import py_compile
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_any(path: Path) -> str:
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    if len(raw) > 4 and raw[1] == 0 and raw[3] == 0:
        return raw.decode("utf-16-le")
    return raw.decode("utf-8", errors="replace")


def strip_bad(s: str) -> str:
    # Remove private-use / replacement chars that break Python 3.14
    out = []
    for ch in s:
        o = ord(ch)
        if 0xE000 <= o <= 0xF8FF or ch in ("\ufffd", "\u0000"):
            continue
        out.append(ch)
    return "".join(out)


def fix_glued_all_features(src: str) -> str:
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
    return "\n".join(lines) + "\n"


def neutralize_bad_docstrings(src: str) -> str:
    """Replace triple-quoted strings that still contain control issues with empty docs."""

    def repl(m: re.Match) -> str:
        body = m.group(0)
        if any(0xE000 <= ord(c) <= 0xF8FF for c in body) or "\ufffd" in body:
            quote = m.group(1)
            return quote + "." + quote
        return body

    # naive: """...""" and '''...''' non-greedy across lines
    src = re.sub(r'(""").*?(""")', repl, src, flags=re.S)
    src = re.sub(r"(''').*?(''')", repl, src, flags=re.S)
    return src


def ensure_v25(src: str) -> str:
    if "_load_v25" not in src:
        src = src.replace(
            '        elif self.model_version == "v20":\n            return self._load_v20()',
            '        elif self.model_version in ("v25", "vm25", "vm2.5"):\n'
            "            return self._load_v25()\n"
            '        elif self.model_version == "v20":\n'
            "            return self._load_v20()",
            1,
        )
        method = '''
    def _load_v25(self) -> bool:
        """Load VM2.5 via shared scorer."""
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
            "            return self._score_v25(kline_df, symbol, sector_heat)\n"
            + old
        )
        if old in src:
            src = src.replace(old, new, 1)
    return src


def process(path: Path, add_v25: bool = False, prefer_bak: Path | None = None) -> None:
    src_path = prefer_bak if prefer_bak and prefer_bak.exists() else path
    src = read_any(src_path)
    src = strip_bad(src)
    src = fix_glued_all_features(src)
    src = neutralize_bad_docstrings(src)
    if add_v25:
        src = ensure_v25(src)
    if path.name == "recommend.py":
        src = src.replace('load_model(version="v20")', 'load_model(version="v25")')
        src = src.replace("load_model(version='v20')", "load_model(version='v25')")
    path.write_text(src, encoding="utf-8", newline="\n")
    py_compile.compile(str(path), doraise=True)
    print("OK", path.name)


def main() -> int:
    process(
        ROOT / "ml_screener.py",
        add_v25=True,
        prefer_bak=ROOT / "ml_screener.py.bak_before_p0",
    )
    process(
        ROOT / "recommend.py",
        add_v25=False,
        prefer_bak=ROOT / "recommend.py.bak_before_p0",
    )
    print("SANITIZE_DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
