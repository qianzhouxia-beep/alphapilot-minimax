#!/usr/bin/env python3
"""重放：recommend ∩ GC → 资金门控，找出上次漏斗仅剩的那只，并核对 7/17 涨跌。"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pandas as pd

ROOT = Path("/home/ubuntu/alphapilot")
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

REC = ROOT / "output/daily_recommend.json"
BAK = ROOT / "output/daily_recommend.json.bak_before_survivor_probe"


def main():
    if REC.exists():
        shutil.copy2(REC, BAK)

    from recommend import run_daily_recommend
    from money_flow_gate import apply_money_flow_gate
    from vm25_scorer import _bare

    print("running recommend...", flush=True)
    out = run_daily_recommend(top_n=5)
    items = out.get("recommendations") or []
    print("recommend_n", len(items), flush=True)

    gc = json.loads((ROOT / "output/volume_gc_pool.json").read_text(encoding="utf-8"))
    gc_set = {_bare(s) for s in (gc if isinstance(gc, list) else gc.get("symbols") or [])}
    inter = [it for it in items if _bare(it.get("symbol")) in gc_set]
    print("after_gc", len(inter), flush=True)

    gated = apply_money_flow_gate(inter, top_n=None)
    print("after_money", len(gated), flush=True)

    kpath = ROOT / "data/kline_cache/kline_all.parquet"
    if not kpath.exists():
        kpath = ROOT / "kline_all.parquet"
    kdf = pd.read_parquet(kpath)
    kdf["date"] = kdf["date"].astype(str).str[:10]
    kdf["symbol"] = kdf["symbol"].astype(str).map(_bare)
    asof = "2026-07-17"

    report = []
    for it in gated:
        sym = _bare(it.get("symbol"))
        g = kdf[kdf["symbol"] == sym].sort_values("date").reset_index(drop=True)
        idxs = g.index[g["date"] == asof]
        day = {}
        if len(idxs):
            ai = int(idxs[0])
            prev = float(g.loc[ai - 1, "close"]) if ai >= 1 else None
            c = float(g.loc[ai, "close"])
            o = float(g.loc[ai, "open"])
            day = {
                "date": asof,
                "open": o,
                "close": c,
                "chg_pct": round((c / prev - 1) * 100, 2) if prev else None,
            }
            if ai + 1 < len(g):
                n = g.loc[ai + 1]
                day["next_date"] = str(n["date"])
                day["next_open"] = float(n["open"])
                day["next_close"] = float(n["close"])
                day["t1_from_signal_close"] = round((float(n["close"]) / c - 1) * 100, 2)
            else:
                day["next"] = "no_bar_yet"
        report.append(
            {
                "symbol": sym,
                "name": it.get("name"),
                "score": it.get("score"),
                "main_net_5d": it.get("main_net_5d"),
                "money_phase": it.get("money_phase_label") or it.get("money_phase"),
                "day": day,
            }
        )
        print("SURVIVOR", json.dumps(report[-1], ensure_ascii=False), flush=True)

    (ROOT / "output/funnel_survivor_probe.json").write_text(
        json.dumps({"n": len(report), "survivors": report}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 恢复空仓产物（severe 日网站不应展示临时 recommend）
    if BAK.exists():
        shutil.copy2(BAK, REC)
        print("restored", REC, flush=True)


if __name__ == "__main__":
    main()
