#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pair existing QMT/TDX ledgers into fusion_closed_trades.jsonl (FIFO).

Sources (local Windows):
  C:/alphapilot/live_trades_fullchain.json
  C:/alphapilot/sim_trades_fullchain.json
  C:/alphapilot/tdx_trades.json

Fusion scores: if the BUY row already has fusion_scores, use it.
Else reconstruct from archived morning_live_picks (score min-max + tanh fund).
Rows with no fusion signal are skipped (do not pollute IC with 0.5 defaults).
"""
from __future__ import annotations

import json
import math
from collections import defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = Path(r"C:/alphapilot")
OUT_LOCAL = LOCAL / "fusion_closed_trades.jsonl"
OUT_REPO = ROOT / "data" / "fusion_closed_trades.jsonl"
ARCHIVE = ROOT / "data" / "srv_archive" / "rf_score_sync"

LEDGERS = [
    (LOCAL / "live_trades_fullchain.json", "qmt_live"),
    (LOCAL / "sim_trades_fullchain.json", "qmt_sim"),
    (LOCAL / "tdx_trades.json", "tdx_sim"),
]


def _bare(sym: str) -> str:
    s = str(sym or "").upper().replace("SH", "").replace("SZ", "").replace("BJ", "")
    s = s.replace(".", "")
    return s[-6:] if len(s) >= 6 else s


def _tanh01(val) -> float:
    try:
        x = float(val)
    except (TypeError, ValueError):
        return 0.5
    if x == 0:
        return 0.5
    t = math.tanh(x / 10_000_000.0)
    return max(0.0, min(1.0, (t + 1.0) / 2.0))


def _fusion_from_picks(picks: list[dict], symbol: str) -> dict | None:
    by = {_bare(p.get("symbol")): p for p in picks if isinstance(p, dict)}
    hit = by.get(_bare(symbol))
    if not hit:
        return None
    scores = []
    for p in picks:
        try:
            scores.append(float(p.get("score") or 0))
        except (TypeError, ValueError):
            pass
    try:
        sc = float(hit.get("score") or 0)
    except (TypeError, ValueError):
        sc = 0.0
    vm25 = 0.5
    if scores:
        lo, hi = min(scores), max(scores)
        span = (hi - lo) or 1.0
        vm25 = max(0.0, min(1.0, (sc - lo) / span))
    fund = _tanh01(hit.get("live_main_net") or hit.get("main_net") or hit.get("main_net_5d") or 0)
    heat = 0.5
    fs = hit.get("fusion_scores") or hit.get("_fusion_scores")
    if isinstance(fs, dict) and fs.get("vm25") is not None:
        return {
            "vm25": round(float(fs.get("vm25", vm25)), 4),
            "fund_flow": round(float(fs.get("fund_flow", fund)), 4),
            "sector_heat": round(float(fs.get("sector_heat", heat)), 4),
        }
    return {
        "vm25": round(vm25, 4),
        "fund_flow": round(fund, 4),
        "sector_heat": round(heat, 4),
    }


def _picks_for_date(ymd: str) -> list[dict]:
    """ymd: YYYYMMDD or YYYY-MM-DD.

    Prefer the same Top10 QMT actually traded ({date}.candidates.json),
    then archived morning picks.
    """
    day = ymd.replace("-", "")[:8]
    if len(day) != 8:
        return []
    iso = f"{day[:4]}-{day[4:6]}-{day[6:8]}"
    cand = LOCAL / "scores" / f"{day}.candidates.json"
    if cand.exists():
        try:
            d = json.loads(cand.read_text(encoding="utf-8"))
        except Exception:
            d = None
        if isinstance(d, dict):
            arr = d.get("candidates") or d.get("recommendations") or []
        elif isinstance(d, list):
            arr = d
        else:
            arr = []
        rows = [x for x in arr if isinstance(x, dict)]
        if rows:
            return rows
    for p in (
        ARCHIVE / iso / "morning_live_picks.json",
        ARCHIVE / iso / "daily_picks_latest.json",
    ):
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        arr = d.get("picks") or d.get("recommendations") or d.get("items") or []
        if isinstance(arr, list) and arr:
            return [x for x in arr if isinstance(x, dict)]
    return []


def _load_ledger(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [x for x in raw if isinstance(x, dict)] if isinstance(raw, list) else []


def fifo_close(rows: list[dict], source: str) -> list[dict]:
    lots: dict[str, deque] = defaultdict(deque)
    closed: list[dict] = []
    for rec in rows:
        act = str(rec.get("action") or "")
        sym = str(rec.get("symbol") or "")
        if not sym:
            continue
        try:
            px = float(rec.get("price") or 0)
            vol = int(rec.get("volume") or 0)
        except (TypeError, ValueError):
            continue
        if vol <= 0 or px <= 0:
            continue
        t = str(rec.get("time") or "")
        if act == "BUY":
            fs = rec.get("fusion_scores") or rec.get("_fusion_scores")
            if not isinstance(fs, dict) or fs.get("vm25") is None:
                fs = _fusion_from_picks(_picks_for_date(t[:10] or t[:8]), sym)
            lots[_bare(sym)].append(
                {"price": px, "volume": vol, "time": t, "fusion": fs}
            )
            continue
        if not act.startswith("SELL"):
            continue
        remain = vol
        q = lots[_bare(sym)]
        while remain > 0 and q:
            lot = q[0]
            take = min(remain, int(lot["volume"]))
            fs = lot.get("fusion")
            if isinstance(fs, dict) and fs.get("vm25") is not None:
                closed.append(
                    {
                        "source": source,
                        "symbol": rec.get("symbol"),
                        "action": act,
                        "buy_date": str(lot.get("time") or "")[:10],
                        "sell_time": t,
                        "buy_price": round(float(lot["price"]), 4),
                        "sell_price": round(px, 4),
                        "volume": take,
                        "pnl": round((px - float(lot["price"])) * take, 2),
                        "_fusion_scores": fs,
                        "backfill": True,
                    }
                )
            lot["volume"] = int(lot["volume"]) - take
            remain -= take
            if lot["volume"] <= 0:
                q.popleft()
    return closed


def main() -> int:
    all_rows: list[dict] = []
    for path, src in LEDGERS:
        led = _load_ledger(path)
        got = fifo_close(led, src)
        print(f"{src}: ledger={len(led)} closed_with_fusion={len(got)} ({path.name})")
        all_rows.extend(got)
    OUT_REPO.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(r, ensure_ascii=True) + "\n" for r in all_rows)
    OUT_REPO.write_text(text, encoding="utf-8")
    if LOCAL.exists():
        OUT_LOCAL.write_text(text, encoding="utf-8")
        print("wrote", OUT_LOCAL)
    print("wrote", OUT_REPO, "n=", len(all_rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
