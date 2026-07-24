#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0: align production funnel with tradable arm A + VM2.5."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    if len(raw) > 4 and raw[1] == 0 and raw[3] == 0:
        return raw.decode("utf-16-le")
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def write_utf8(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def patch_ml_screener() -> None:
    path = ROOT / "ml_screener.py"
    src = read_text(path)
    bak = ROOT / "ml_screener.py.bak_before_p0"
    if not bak.exists():
        bak.write_bytes(path.read_bytes())

    if 'in ("v25", "vm25", "vm2.5")' not in src or "_load_v25" not in src:
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
        src = src.replace("    def _load_v20(self)", method + "    def _load_v20(self)", 1)

    if 'return self._score_v25' not in src:
        old = '        if self.model_version.startswith("v18") or self.model_version.startswith("v19"):'
        new = (
            '        if self.model_version in ("v25", "vm25", "vm2.5"):\n'
            "            return self._score_v25(kline_df, symbol, sector_heat)\n"
            '        if self.model_version.startswith("v18") or self.model_version.startswith("v19"):'
        )
        if old in src:
            src = src.replace(old, new, 1)

    write_utf8(path, src)
    print("OK ml_screener.py -> utf-8 + v25")


def patch_recommend() -> None:
    path = ROOT / "recommend.py"
    src = read_text(path)
    bak = ROOT / "recommend.py.bak_before_p0"
    if not bak.exists():
        bak.write_bytes(path.read_bytes())
    src2 = src.replace('load_model(version="v20")', 'load_model(version="v25")')
    src2 = src2.replace("load_model(version='v20')", "load_model(version='v25')")
    write_utf8(path, src2)
    print("OK recommend.py -> utf-8 + load_model(v25)" if src2 != src else "OK recommend.py utf-8 (already v25?)")


def patch_money_flow_gate() -> None:
    path = ROOT / "money_flow_gate.py"
    src = read_text(path)
    bak = ROOT / "money_flow_gate.py.bak_before_p0"
    if not bak.exists():
        bak.write_bytes(path.read_bytes())

    if "import os" not in src.split("def apply_money_flow_gate")[0]:
        src = src.replace(
            'from enriched_data import get_quotes_batch, get_mootdx_finance_fundamentals\nfrom config import OUTPUT_DIR\n',
            "import json\nimport os\n\n"
            "from enriched_data import get_quotes_batch, get_mootdx_finance_fundamentals\n"
            "from config import OUTPUT_DIR\n",
            1,
        )

    # add hard_main_net_5d param
    if "hard_main_net_5d" not in src:
        src = src.replace(
            "    check_fundamentals: bool = True,\n) -> list:",
            "    check_fundamentals: bool = True,\n"
            "    hard_main_net_5d: bool = True,\n) -> list:",
            1,
        )
        # after computing main_net_5d block, mark hard fail
        marker = '            elif _today_net > 0 and r["main_net_10d"] < 0:\n                r["money_warning"] = f"当日流入但10日累计净流出"\n'
        insert = marker + (
            "\n        # 硬资金门：近5日主力净额合计<=0 直接出局（与回测 A 臂对齐）\n"
            '        r["fund_hard_fail"] = False\n'
            "        if hard_main_net_5d and sym_code in fund_hist:\n"
            "            _hist = fund_hist[sym_code]\n"
            "            _dates = sorted(_hist.keys(), reverse=True)\n"
            "            _nets5_h = [float(_hist[d]) for d in _dates[:5] if d in _hist]\n"
            "            if len(_nets5_h) >= 3 and float(r.get(\"main_net_5d\", 0) or 0) <= 0:\n"
            '                r["fund_hard_fail"] = True\n'
            '                r["money_warning"] = (r.get("money_warning") or "") + "|hard:main_net_5d<=0"\n'
        )
        if marker in src:
            src = src.replace(marker, insert, 1)

        # filter hard fails before pass/fail split
        old_split = "    # 重排\n    passed_list = [r for r in out if r.get(\"money_flow_pass\") is True]"
        new_split = (
            "    # 硬资金门出局\n"
            '    hard_dropped = [r for r in out if r.get("fund_hard_fail")]\n'
            '    out = [r for r in out if not r.get("fund_hard_fail")]\n'
            "    if hard_dropped:\n"
            '        print(f"  money_flow_gate hard_main_net_5d drop {len(hard_dropped)}", flush=True)\n'
            "    # 重排\n"
            '    passed_list = [r for r in out if r.get("money_flow_pass") is True]'
        )
        if old_split in src:
            src = src.replace(old_split, new_split, 1)

    # s2_score alias for pipeline apply_s2_weight
    if 'r["s2_score"]' not in src:
        src = src.replace(
            '        r["s2_bonus"] = s2\n        r["score"] = round(r.get("score", 0) + s2, 4)',
            '        r["s2_bonus"] = s2\n'
            '        r["s2_score"] = s2  # alias for pipeline apply_s2_weight\n'
            '        r["score"] = round(r.get("score", 0) + s2, 4)',
            1,
        )

    # when top_n is None, default to passed-only if enough passes; keep hard drops out always
    # already hard-dropped from out. Optionally prefer passed only:
    if "HARD_PASS_ONLY" not in src:
        src = src.replace(
            "    else:\n        result = passed_list + failed_list\n    return result",
            "    else:\n"
            "        # 生产默认：硬资金已删；其余未通过软门的票不再混入主列表\n"
            "        result = passed_list if passed_list else failed_list\n"
            "    return result",
            1,
        )

    write_utf8(path, src)
    print("OK money_flow_gate.py")


def patch_pipeline() -> None:
    path = ROOT / "alphapilot_pipeline_v3.py"
    src = read_text(path)
    bak = ROOT / "alphapilot_pipeline_v3.py.bak_before_p0"
    if not bak.exists():
        bak.write_bytes(path.read_bytes())

    # soft intraday off by default
    old_soft = '''    # 盘中软门控：实时资金流排名 + 行情软加权（不硬杀）
    try:
        from soft_intraday_gate import apply_soft_intraday_gate
        before = len(gated)
        gated = apply_soft_intraday_gate(gated, mode="soft")
        log(f"  ✅ 盘中软门控加权: {before} 只（不删票）")
    except Exception as e:
        log(f"  ⚠️ 盘中软门控跳过: {e}")
    return gated'''
    new_soft = '''    # 盘中软门控：默认关闭（生产 A 臂）；ENABLE_SOFT_INTRADAY=1 才开启
    if os.environ.get("ENABLE_SOFT_INTRADAY", "").strip() in ("1", "true", "TRUE", "yes"):
        try:
            from soft_intraday_gate import apply_soft_intraday_gate
            before = len(gated)
            gated = apply_soft_intraday_gate(gated, mode="soft")
            log(f"  ✅ 盘中软门控加权: {before} 只（不删票）")
        except Exception as e:
            log(f"  ⚠️ 盘中软门控跳过: {e}")
    else:
        log("  ⏭ 盘中软门控关闭（生产硬门控主臂；ENABLE_SOFT_INTRADAY=1 可开）")
    return gated'''
    if old_soft in src:
        src = src.replace(old_soft, new_soft, 1)

    # no GC empty fallback to unfiltered
    old_fb = '''    if not items:
        log("⚠️ 量价金叉过滤后无候选股，使用原始推荐")
        recs = json.load(open(rec_path))
        items = recs.get("recommendations", [])'''
    new_fb = '''    if not items:
        log("⛔ 量价金叉过滤后无候选股 — 不回退全量推荐（保持严格金叉）")
        items = []'''
    if old_fb in src:
        src = src.replace(old_fb, new_fb, 1)

    # S2: prefer s2_bonus
    old_s2 = '''def apply_s2_weight(items: list) -> list:
    """S2策略作为最终加权层"""
    log("▶ S2策略加权...")
    for item in items:
        s2_score = item.get("s2_score", 0)
        if s2_score:
            base = float(item.get("score", 0) or 0)
            item["score"] = round(base * (1 + s2_score * 0.05), 4)
    items.sort(key=lambda x: -float(x.get("score", 0) or 0))
    log(f"  ✅ 完成")
    return items'''
    new_s2 = '''def apply_s2_weight(items: list) -> list:
    """S2策略作为最终加权层（读取 s2_bonus / s2_score；资金门已加过一次加法分时跳过乘法以免双计）"""
    log("▶ S2策略加权...")
    n = 0
    for item in items:
        # 资金门控已把 s2_bonus 加进 score；此处仅在尚未标记时做乘法微调
        if item.get("s2_applied_in_money_gate"):
            continue
        s2 = item.get("s2_bonus", item.get("s2_score", 0)) or 0
        try:
            s2 = float(s2)
        except Exception:
            s2 = 0.0
        if s2:
            base = float(item.get("score", 0) or 0)
            item["score"] = round(base * (1 + s2 * 0.05), 4)
            n += 1
    items.sort(key=lambda x: -float(x.get("score", 0) or 0))
    log(f"  ✅ S2 微调 {n} 只（已在资金门加过的跳过）")
    return items'''
    if old_s2 in src:
        src = src.replace(old_s2, new_s2, 1)

    src = src.replace(
        'ok = run_step("V2.2模型选股", "python3 -u recommend.py", 1200)\n    if not ok:\n        log("❌ V2.2选股失败，终止管线")',
        'ok = run_step("VM2.5模型选股", "python3 -u recommend.py", 1200)\n    if not ok:\n        log("❌ VM2.5选股失败，终止管线")',
        1,
    )
    src = src.replace(
        'log("AlphaPilot 选股管线 v3.0（漏斗架构）")',
        'log("AlphaPilot 选股管线 v3.1（VM2.5 + 硬门控漏斗）")',
        1,
    )

    write_utf8(path, src)
    print("OK alphapilot_pipeline_v3.py")


def main() -> int:
    patch_ml_screener()
    patch_recommend()
    patch_money_flow_gate()
    patch_pipeline()
    # mark s2 applied in money gate so pipeline won't double-multiply
    path = ROOT / "money_flow_gate.py"
    src = read_text(path)
    if "s2_applied_in_money_gate" not in src:
        src = src.replace(
            '        r["s2_score"] = s2  # alias for pipeline apply_s2_weight\n'
            '        r["score"] = round(r.get("score", 0) + s2, 4)',
            '        r["s2_score"] = s2  # alias for pipeline apply_s2_weight\n'
            '        r["s2_applied_in_money_gate"] = True\n'
            '        r["score"] = round(r.get("score", 0) + s2, 4)',
            1,
        )
        write_utf8(path, src)
        print("OK money_flow_gate s2_applied flag")
    print("P0_FIX_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
