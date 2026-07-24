#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""评分 Top10 当日涨跌评判：开盘后/收盘后快照。

用法:
  python3 scripts/audit_score_top10_day.py --phase open
  python3 scripts/audit_score_top10_day.py --phase close
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

ROOT = Path("/home/ubuntu/alphapilot")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parents[1]

TOP_PATH = ROOT / "output/score_top10.json"
OUT_DIR = ROOT / "output/score_top10_day"


def bare(s: str) -> str:
    x = str(s or "")
    for p in ("sh", "sz", "bj", "SH", "SZ", "BJ"):
        x = x.replace(p, "")
    return x[-6:] if len(x) >= 6 else x


def load_universe() -> list[dict]:
    if not TOP_PATH.exists():
        raise SystemExit(f"missing {TOP_PATH}")
    d = json.loads(TOP_PATH.read_text(encoding="utf-8"))
    items = list(d.get("items") or [])[:10]
    if len(items) < 1:
        raise SystemExit("score_top10 empty")
    return items


def fetch_quotes(symbols: list[str]) -> dict:
    import sys

    sys.path.insert(0, str(ROOT))
    try:
        from enriched_data import get_quotes_batch

        return get_quotes_batch(symbols) or {}
    except Exception as e:
        print("quotes failed:", e)
        return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["open", "close", "now"], default="now")
    args = ap.parse_args()

    day = time.strftime("%Y-%m-%d")
    items = load_universe()
    syms = [bare(x.get("symbol")) for x in items]
    quotes = fetch_quotes(syms)

    rows = []
    up = down = flat = miss = 0
    for it in items:
        code = bare(it.get("symbol"))
        q = quotes.get(code) or quotes.get(f"sh{code}") or quotes.get(f"sz{code}") or {}
        chg = q.get("change_pct")
        if chg is None:
            chg = it.get("change_pct")
        try:
            chg_f = float(chg) if chg is not None else None
        except Exception:
            chg_f = None
        if chg_f is None:
            miss += 1
            tag = "na"
        elif chg_f > 0:
            up += 1
            tag = "up"
        elif chg_f < 0:
            down += 1
            tag = "down"
        else:
            flat += 1
            tag = "flat"
        rows.append(
            {
                "rank": it.get("rank"),
                "symbol": code,
                "name": it.get("name"),
                "score": it.get("score"),
                "price": q.get("price", it.get("price")),
                "change_pct": chg_f,
                "tag": tag,
            }
        )

    n = len(rows)
    known = up + down + flat
    summary = {
        "day": day,
        "phase": args.phase,
        "asof": time.strftime("%Y-%m-%d %H:%M:%S"),
        "n": n,
        "up": up,
        "down": down,
        "flat": flat,
        "missing_quote": miss,
        "up_ratio": round(up / known, 4) if known else None,
        "avg_change_pct": round(
            sum(r["change_pct"] for r in rows if r["change_pct"] is not None) / known, 4
        )
        if known
        else None,
        "items": rows,
        "source_score_top10_asof": json.loads(TOP_PATH.read_text(encoding="utf-8")).get("asof"),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{day}_{args.phase}.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 60)
    print(f"评分 Top10 日评判 | {day} | phase={args.phase}")
    print(f"上涨 {up}/{n}  下跌 {down}/{n}  平盘 {flat}/{n}  无报价 {miss}")
    if summary["avg_change_pct"] is not None:
        print(f"平均涨跌 {summary['avg_change_pct']:+.2f}%")
    print("-" * 60)
    for r in rows:
        chg = r["change_pct"]
        chg_s = f"{chg:+.2f}%" if chg is not None else "—"
        mark = {"up": "↑", "down": "↓", "flat": "→", "na": "?"}[r["tag"]]
        print(f"  #{r['rank']:<2} {r['symbol']} {r.get('name') or '':<8} {chg_s:>8} {mark}")
    print("=" * 60)
    print("saved", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
