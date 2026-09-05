#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回滚 _port_weak_regime_v231.py 对指定 3 个文件的修改（用户 2026-09-03 12:49
指示：本次只改 QMT 轨道 A）。反向应用同一组替换，断言唯一命中。"""
from __future__ import annotations

import importlib.util
import pathlib

ROOT = pathlib.Path(r"C:\Users\elvisq\Projects\alphapilot\production_strategies")
spec = importlib.util.spec_from_file_location(
    "port_mod", ROOT / "_port_weak_regime_v231.py")
port = importlib.util.module_from_spec(spec)
spec.loader.exec_module(port)

REVERT = [
    "track_a/TrackA_track_a_tdx_full_chain_sim.py",
    "ptrade/TrackA_track_a_ptrade_live.py",
    "ptrade/TrackA_track_a_ptrade_sim.py",
]


def main() -> int:
    ok = True
    for rel in REVERT:
        p = ROOT / rel
        text = p.read_text(encoding="utf-8")
        errs = []
        for i, (old, new) in enumerate(port.FILES[rel]):
            n = text.count(new)
            if n != 1:
                errs.append(f"  rep#{i} new-string count={n} (need 1)")
                continue
            text = text.replace(new, old, 1)
        if errs:
            ok = False
            print(f"[FAIL] {rel}")
            for e in errs:
                print(e)
            continue
        p.write_text(text, encoding="utf-8", newline="\n")
        print(f"[REVERTED] {rel}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
