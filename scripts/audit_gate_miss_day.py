#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日门控误杀 / 漏杀复盘。

对照：
  - 无门槛 score_top10（或 daily_recommend 原始分）当日大涨票
  - money_flow_gate 硬淘 / 软淘后「今日推荐」未持有

输出：
  output/reviews/gate_miss_YYYY-MM-DD.json

用法：
  python3 -u scripts/audit_gate_miss_day.py
  python3 -u scripts/audit_gate_miss_day.py --date 2026-07-24
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path

ROOT = Path("/home/ubuntu/alphapilot")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parents[1]

OUT_DIR = ROOT / "output" / "reviews"


def _bare(s: str) -> str:
    x = str(s or "")
    for p in ("sh", "sz", "bj", "SH", "SZ", "BJ"):
        x = x.replace(p, "")
    return x[-6:] if len(x) >= 6 else x


def _ui_pct(score: float) -> int:
    s = float(score or 0)
    if s <= 0:
        return 0
    if s <= 1:
        return int(round(s * 100))
    return int(round(100 / (1 + math.exp(-s / 2))))


def _load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="", help="YYYY-MM-DD，默认今天")
    ap.add_argument("--chg-thr", type=float, default=5.0, help="大涨阈值（%%）")
    args = ap.parse_args()
    day = args.date or datetime.now().strftime("%Y-%m-%d")

    rec = _load_json(ROOT / "output" / "daily_recommend.json") or {}
    top = _load_json(ROOT / "output" / "score_top10.json") or {}
    raw_items = rec.get("recommendations") or rec.get("items") or []
    top_items = top.get("items") or []

    # 推荐池：过资金门后
    gated = []
    try:
        from money_flow_gate import apply_money_flow_gate

        gated = apply_money_flow_gate([dict(x) for x in raw_items], top_n=None)
    except Exception as e:
        gated = list(raw_items)
        gate_err = str(e)
    else:
        gate_err = None

    gated_syms = {_bare(x.get("symbol")) for x in gated}
    raw_by = {_bare(x.get("symbol")): x for x in raw_items}
    top_by = {_bare(x.get("symbol")): x for x in top_items}

    # 误杀：在无门槛 Top10 或 raw 高分，且涨幅≥阈值，但不在 gated
    universe = []
    for src, pool in (("score_top10", top_items), ("daily_raw", raw_items)):
        for it in pool:
            sym = _bare(it.get("symbol"))
            if not sym:
                continue
            chg = float(it.get("change_pct") or it.get("live_change_pct") or 0)
            sc = float(it.get("score") or it.get("lgb_score") or 0)
            universe.append((sym, chg, sc, src, it.get("name") or ""))

    # dedupe keep max chg
    best: dict[str, tuple] = {}
    for sym, chg, sc, src, name in universe:
        prev = best.get(sym)
        if prev is None or chg > prev[1] or (chg == prev[1] and sc > prev[2]):
            best[sym] = (sym, chg, sc, src, name)

    false_neg = []  # 踢掉却大涨
    for sym, chg, sc, src, name in sorted(best.values(), key=lambda x: -x[1]):
        if chg < args.chg_thr:
            continue
        if sym in gated_syms:
            continue
        raw = raw_by.get(sym) or top_by.get(sym) or {}
        false_neg.append(
            {
                "symbol": sym,
                "name": name or raw.get("name"),
                "change_pct": round(chg, 2),
                "score": round(sc, 4),
                "score_ui": _ui_pct(sc),
                "source": src,
                "main_net": raw.get("main_net"),
                "main_net_5d": raw.get("main_net_5d"),
                "money_phase_label": raw.get("money_phase_label"),
                "money_warning": raw.get("money_warning"),
                "in_recommend_after_gate": False,
            }
        )

    # 漏风控：在推荐池内却大跌
    false_pos = []
    for it in gated:
        sym = _bare(it.get("symbol"))
        chg = float(it.get("change_pct") or it.get("live_change_pct") or 0)
        if chg > -args.chg_thr:
            continue
        false_pos.append(
            {
                "symbol": sym,
                "name": it.get("name"),
                "change_pct": round(chg, 2),
                "score": round(float(it.get("score") or 0), 4),
                "score_ui": _ui_pct(float(it.get("score") or 0)),
                "main_net_5d": it.get("main_net_5d"),
                "money_phase_label": it.get("money_phase_label"),
            }
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "asof": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "date": day,
        "chg_thr_pct": args.chg_thr,
        "n_raw": len(raw_items),
        "n_gated": len(gated),
        "n_false_negative_big_up": len(false_neg),
        "n_false_positive_big_down": len(false_pos),
        "gate_error": gate_err,
        "false_negatives": false_neg[:30],
        "false_positives": false_pos[:30],
        "note": (
            "false_negative=门控未纳入但当日大涨（误杀候选）；"
            "false_positive=纳入推荐但当日大跌（漏风控）。"
            "不自动改阈值，供周度人工/回测决策。"
        ),
    }
    path = OUT_DIR / f"gate_miss_{day}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {path}")
    print(
        f"false_neg(大涨未入选)={len(false_neg)} "
        f"false_pos(入选大跌)={len(false_pos)} gated={len(gated)}/{len(raw_items)}"
    )
    for x in false_neg[:8]:
        print(
            f"  FN {x['symbol']} {x.get('name')} chg={x['change_pct']:+.2f}% "
            f"ui={x['score_ui']} warn={x.get('money_warning')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
