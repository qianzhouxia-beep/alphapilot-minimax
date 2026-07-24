#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rebuild ml_screener.py / recommend.py to UTF-8 + VM2.5; strip broken docstrings."""
from __future__ import annotations

import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_any(path: Path) -> str:
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    if len(raw) > 4 and raw[1] == 0 and raw[3] == 0:
        return raw.decode("utf-16-le")
    return raw.decode("utf-8", errors="replace")


def strip_pua(s: str) -> str:
    return "".join(
        ch for ch in s if not (0xE000 <= ord(ch) <= 0xF8FF) and ch not in ("\ufffd", "\x00")
    )


def fix_glued(src: str) -> str:
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


def strip_all_triple_strings(src: str) -> str:
    # Remove every triple-quoted string (docstrings); keep normal code.
    out = []
    i = 0
    n = len(src)
    dq = '"' * 3
    sq = "'" * 3
    while i < n:
        if src.startswith(dq, i) or src.startswith(sq, i):
            q = src[i : i + 3]
            j = src.find(q, i + 3)
            if j < 0:
                # malformed docstring: drop the whole line from opening quotes
                nl = src.find("\n", i)
                i = nl + 1 if nl >= 0 else n
                continue
            # skip the whole well-formed triple string
            i = j + 3
            continue
        out.append(src[i])
        i += 1
    return "".join(out)


def ensure_v25(src: str) -> str:
    if 'elif self.model_version in ("v25", "vm25", "vm2.5")' not in src:
        src = src.replace(
            '        elif self.model_version == "v20":\n            return self._load_v20()',
            '        elif self.model_version in ("v25", "vm25", "vm2.5"):\n'
            "            return self._load_v25()\n"
            '        elif self.model_version == "v20":\n'
            "            return self._load_v20()",
            1,
        )
    if "def _load_v25" not in src:
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

"""
        src = src.replace("    def _load_v20(self)", method + "    def _load_v20(self)", 1)
    if "return self._score_v25" not in src:
        old = '        if self.model_version.startswith("v18") or self.model_version.startswith("v19"):'
        new = (
            '        if self.model_version in ("v25", "vm25", "vm2.5"):\n'
            "            return self._score_v25(kline_df, symbol, sector_heat)\n" + old
        )
        if old in src:
            src = src.replace(old, new, 1)
    return src


def unglue_junk_before_assign(src: str) -> str:
    """Fix 'comment debris    stmt = ...' glued on one line."""
    import re

    out = []
    for line in src.splitlines():
        has_cjk = any("\u4e00" <= c <= "\u9fff" for c in line)
        m = re.search(r"^(.*?)(\s+)([A-Za-z_][\w\.]*\s*=\s*.+)$", line)
        if has_cjk and m:
            left = m.group(1).rstrip()
            stmt = m.group(2) + m.group(3)  # keep spaces as indentation
            if left and not left.lstrip().startswith("def ") and "lambda" not in left:
                out.append(stmt if stmt.startswith((" ", "\t")) else ("    " + m.group(3)))
                continue
        m2 = re.match(
            r"^(\s*)(.+?)\s{2,}([A-Za-z_][\w\.]*\s*=\s*.+)$",
            line,
        )
        if m2:
            junk = m2.group(2).strip()
            if not junk.startswith("#") and "=" not in junk and (" " in junk or ":" in junk):
                out.append(m2.group(1) + m2.group(3))
                continue
        out.append(line)
    return "\n".join(out) + "\n"


def unglue_hash_return(src: str) -> str:
    """Fix lines where 'return' was glued into a # comment (UTF-16 artifact)."""
    out = []
    for line in src.splitlines():
        if "#" in line and "return " in line:
            hash_at = line.find("#")
            ret_at = line.find("return ")
            if hash_at < ret_at:
                indent = line[: len(line) - len(line.lstrip())]
                out.append(indent + "return " + line[ret_at + len("return ") :])
                continue
        out.append(line)
    return "\n".join(out) + "\n"


def drop_orphan_cjk_debris(src: str) -> str:
    """Drop leftover Chinese comment/doc debris that lost leading #."""
    keep = []
    for line in src.splitlines():
        has_cjk = any("\u4e00" <= c <= "\u9fff" for c in line)
        if has_cjk:
            stripped = line.lstrip()
            codeish = (
                stripped.startswith("#")
                or stripped.startswith("def ")
                or stripped.startswith("class ")
                or stripped.startswith("import ")
                or stripped.startswith("from ")
                or "print(" in line
                or stripped.startswith("return ")
                or ("=" in line and ("(" in line or "[" in line or '"' in line or "'" in line))
            )
            if not codeish:
                continue
        keep.append(line)
    return "\n".join(keep) + "\n"


def fix_broken_print_lines(src: str) -> str:
    """Neutralize print lines that contain CJK/mojibake (UTF-16 damage)."""
    import re

    lines = src.splitlines()
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if "print(" in line:
            has_cjk = any("\u4e00" <= c <= "\u9fff" for c in line)
            broken = (
                has_cjk
                or line.count('"') % 2 == 1
                or "\ufffd" in line
                or line.rstrip().endswith("?)")
            )
            if broken and ("f\"" in line or "f'" in line or 'print("' in line or "print(f" in line):
                indent = re.match(r"^(\s*)", line).group(1)
                out.append(f'{indent}print("...")')
                # drop dangling %-format / paren continuations of the old print
                j = i + 1
                while j < len(lines):
                    s = lines[j].lstrip()
                    if s.startswith("%") or s.startswith("+ (") or s.startswith("+(") or s.startswith(")"):
                        j += 1
                        continue
                    if s.startswith("+") and "join" in s:
                        j += 1
                        continue
                    break
                i = j
                continue
        out.append(line)
        i += 1
    return "\n".join(out) + "\n"


def unglue_hash_try(src: str) -> str:
    """Fix '# comment    try:' glued lines."""
    import re

    out = []
    for line in src.splitlines():
        if "#" in line and re.search(r"\btry:\s*$", line):
            hash_at = line.find("#")
            try_at = line.rfind("try:")
            if hash_at < try_at:
                indent = re.match(r"^(\s*)", line).group(1)
                out.append(indent + "try:")
                continue
        out.append(line)
    return "\n".join(out) + "\n"


def process(name: str, bak: str, add_v25: bool) -> None:
    src = read_any(ROOT / bak if (ROOT / bak).exists() else ROOT / name)
    src = strip_pua(src)
    src = fix_glued(src)
    src = strip_all_triple_strings(src)
    src = unglue_hash_return(src)
    src = unglue_junk_before_assign(src)
    src = drop_orphan_cjk_debris(src)
    src = unglue_hash_try(src)
    src = fix_broken_print_lines(src)
    # collapse excessive blank lines
    while "\n\n\n" in src:
        src = src.replace("\n\n\n", "\n\n")
    if add_v25:
        src = ensure_v25(src)
    else:
        src = src.replace('load_model(version="v20")', 'load_model(version="v25")')
        src = src.replace("load_model(version='v20')", "load_model(version='v25')")
    out = ROOT / name
    out.write_text(src, encoding="utf-8", newline="\n")
    py_compile.compile(str(out), doraise=True)
    print("OK", name, "lines", len(src.splitlines()))


def main() -> int:
    process("ml_screener.py", "ml_screener.py.bak_before_p0", True)
    process("recommend.py", "recommend.py.bak_before_p0", False)
    print("REBUILD_DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
