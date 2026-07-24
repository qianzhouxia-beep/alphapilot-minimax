#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对比硬宇宙 vs 软宇宙在同一份 daily_recommend 缓存上的差异（不改线上结果）。

用法（上海 VM）:
  python3 -u scripts/compare_hard_vs_soft_universe.py
  python3 -u scripts/compare_hard_vs_soft_universe.py --src output/daily_recommend.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="output/daily_recommend.json")
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()

    path = ROOT / args.src
    if not path.exists():
        # 回退：用 recommend 缓存但可能已是管线后文件；尝试 raw 无则退出
        raise SystemExit(f"missing {path}")

    data = json.loads(path.read_text(encoding="utf-8"))
    items = list(data.get("recommendations") or [])

    # 加载宇宙集合
    gc = set()
    try:
        raw = json.loads((ROOT / "output/volume_gc_pool.json").read_text(encoding="utf-8"))
        if isinstance(raw, list):
            gc = {str(x)[-6:] for x in raw}
    except Exception:
        pass
    try:
        lp = json.loads((ROOT / "output/launch_patterns_pool.json").read_text(encoding="utf-8"))
        for x in lp.get("symbols") or lp.get("hits") or []:
            if isinstance(x, str):
                gc.add(x[-6:])
            elif isinstance(x, dict) and x.get("symbol"):
                gc.add(str(x["symbol"])[-6:])
        # by_pattern values
        for v in (lp.get("by_pattern") or {}).values():
            if isinstance(v, list):
                for s in v:
                    if isinstance(s, str):
                        gc.add(s[-6:])
    except Exception:
        pass

    bypass = set()
    try:
        bp = json.loads((ROOT / "output/hot_sector_bypass_pool.json").read_text(encoding="utf-8"))
        for s in bp.get("symbols") or []:
            bypass.add(str(s)[-6:])
    except Exception:
        pass

    def bare(sym: str) -> str:
        s = str(sym or "").lower().replace("sh", "").replace("sz", "").replace("bj", "")
        return s[-6:]

    def in_u(it):
        b = bare(it.get("symbol"))
        return b in gc or b in bypass

    hard = [it for it in items if in_u(it)]
    hard_sorted = sorted(hard, key=lambda x: -float(x.get("score") or 0))
    soft_sorted = sorted(items, key=lambda x: -float(x.get("score") or 0))

    hard_top = [bare(x.get("symbol")) for x in hard_sorted[: args.top]]
    soft_top = [bare(x.get("symbol")) for x in soft_sorted[: args.top]]

    out = {
        "n_items": len(items),
        "n_hard_universe": len(hard),
        "n_soft_extra": len(items) - len(hard),
        "hard_top": [
            {"symbol": x.get("symbol"), "name": x.get("name"), "score": x.get("score")}
            for x in hard_sorted[: args.top]
        ],
        "soft_top": [
            {
                "symbol": x.get("symbol"),
                "name": x.get("name"),
                "score": x.get("score"),
                "in_hard_universe": in_u(x),
                "arm": x.get("selection_arm"),
            }
            for x in soft_sorted[: args.top]
        ],
        "top_overlap": len(set(hard_top) & set(soft_top)),
        "soft_only_in_top": [
            {"symbol": x.get("symbol"), "name": x.get("name"), "score": x.get("score")}
            for x in soft_sorted[: args.top]
            if not in_u(x)
        ],
    }
    out_path = ROOT / "output" / "compare_hard_vs_soft_universe.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"saved {out_path}")


if __name__ == "__main__":
    main()
