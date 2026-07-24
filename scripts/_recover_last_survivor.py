#!/usr/bin/env python3
"""重建上次管线资金门控后仅剩的那 1 只，并核对 7/17 涨跌。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path("/home/ubuntu/alphapilot")
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from money_flow_gate import apply_money_flow_gate
from vm25_scorer import VM25Scorer, _bare


def main():
    gc = json.loads((ROOT / "output/volume_gc_pool.json").read_text(encoding="utf-8"))
    if isinstance(gc, dict):
        syms = gc.get("symbols") or gc.get("pool") or []
        if not syms and "data" in gc:
            syms = gc["data"]
    else:
        syms = gc
    syms = [_bare(s) for s in syms]
    print("gc_n", len(syms))

    scorer = VM25Scorer(prefer="opt")
    assert scorer.load()

    kpath = ROOT / "data/kline_cache/kline_all.parquet"
    if not kpath.exists():
        kpath = ROOT / "kline_all.parquet"
    kdf = pd.read_parquet(kpath)
    kdf["date"] = kdf["date"].astype(str).str[:10]
    kdf["symbol"] = kdf["symbol"].astype(str).map(_bare)
    asof = "2026-07-17"

    items = []
    for sym in syms:
        g = kdf[kdf["symbol"] == sym].sort_values("date").reset_index(drop=True)
        if g.empty:
            continue
        idxs = g.index[g["date"] <= asof]
        if len(idxs) == 0:
            continue
        ai = int(idxs[-1])
        if str(g.loc[ai, "date"]) != asof:
            continue
        sub = g.iloc[: ai + 1].copy()
        try:
            r = scorer.score(sub, sym)
        except Exception as e:
            continue
        if "error" in r:
            continue
        prev = float(g.loc[ai - 1, "close"]) if ai >= 1 else None
        c = float(g.loc[ai, "close"])
        chg = (c / prev - 1) * 100 if prev and prev > 0 else None
        items.append(
            {
                "symbol": sym,
                "name": r.get("name") or "",
                "score": float(r["score"]),
                "change_pct": chg,
                "price": c,
            }
        )
    items.sort(key=lambda x: -x["score"])
    print("scored", len(items), "top5", [(x["symbol"], x["name"], round(x["score"], 4), x["change_pct"]) for x in items[:5]])

    # 与管线一致：hard fund
    gated = apply_money_flow_gate(items, hard_main_net_5d=True)
    print("after_money_gate", len(gated))
    for it in gated:
        print("SURVIVOR", json.dumps(it, ensure_ascii=False, default=str))

    # 核对涨跌：信号日 7/17；下一交易日若无数据则说明周末未开市
    for it in gated:
        sym = _bare(it["symbol"])
        g = kdf[kdf["symbol"] == sym].sort_values("date").reset_index(drop=True)
        row = g[g["date"] == asof]
        if row.empty:
            continue
        ai = int(row.index[0])
        prev = float(g.loc[ai - 1, "close"])
        o = float(g.loc[ai, "open"])
        c = float(g.loc[ai, "close"])
        h = float(g.loc[ai, "high"])
        low = float(g.loc[ai, "low"])
        chg = c / prev - 1
        print(
            f"DAY {asof}: open={o} close={c} high={h} low={low} "
            f"chg={chg*100:.2f}% vs_prev={prev}"
        )
        if ai + 1 < len(g):
            nprev = c
            no = float(g.loc[ai + 1, "open"])
            nc = float(g.loc[ai + 1, "close"])
            print(
                f"NEXT {g.loc[ai+1,'date']}: open={no} close={nc} "
                f"open_gap={(no/nprev-1)*100:.2f}% day_ret={(nc/no-1)*100:.2f}% "
                f"vs_signal_close={(nc/nprev-1)*100:.2f}%"
            )
        else:
            print("NEXT: no bar yet (weekend / not traded) — cannot verify T+1 move")

        # 近5日资金
        fh = scorer.fund_flow.get(sym) or {}
        dates = sorted(d for d in fh if str(d)[:10] <= asof)
        main5 = sum(float(fh[d] or 0) for d in dates[-5:]) if dates else None
        print("main_net_5d", main5, "main_today", fh.get(asof))


if __name__ == "__main__":
    main()
