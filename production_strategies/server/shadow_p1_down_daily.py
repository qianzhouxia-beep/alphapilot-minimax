# -*- coding: utf-8 -*-
"""[A] P1-DOWN gate read-only shadow (2 weeks, review 2026-09-21).

Issue#6 boss decision c5573698661 / WB review c5573654880:
  P1 DOWN gate is NOT installed live. It runs as a READ-ONLY shadow for two
  weeks: every trading day after close we compute TrendState over the SAME
  pool the cross-validation used (archive top10_ungated, the pre-gate
  candidate list) and append one ledger event per pool stock whose
  confirm-lagged state is DOWN ("would-have-been-vetoed"). Each event is
  settled open-base at T+5 (event-day open as base, matching the 09:35
  decision point; no future leak). Review on 2026-09-21 requires cumulative
  n>=30 before promoting the gate.

A is read-only: never writes orders, never touches daily_recommend /
candidates / scores. It only appends markers + events.

Outputs:
  output/p1_down_shadow.jsonl         daily marker (one line per trading day,
                                      n_pool / n_down / running stats) - read by
                                      shadow_daily_health to detect idling
  rd_workshop/shadow_p1_down/events.jsonl  per-DOWN-event ledger (append)
  rd_workshop/shadow_p1_down/ledger.csv    settlement summary (rewritten)

Usage:
  python3 -u rd_workshop/shadow_p1_down_daily.py [--asof YYYY-MM-DD]
  default asof = latest archive day with a top10_ungated.json AND kline that
  covers it (idempotent: rerun just re-settles already-logged events).

Engine: imports wb_trend_state_calc (the exact reference implementation the
cross-validation reused, commit b66ddfc) - identical states by construction.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

ROOT = Path(os.environ.get("ALPHAPILOT_ROOT") or Path(__file__).resolve().parents[1])
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "_wb_trendstate"))

import pandas as pd  # noqa: E402
import wb_trend_state_calc as wb  # noqa: E402  (reference TrendState calc)

ARCH = ROOT / "output" / "daily_picks_archive"
KLINE = ROOT / "data" / "kline_cache" / "kline_all.parquet"
EVENTS = ROOT / "rd_workshop" / "shadow_p1_down" / "events.jsonl"
LEDGER = ROOT / "rd_workshop" / "shadow_p1_down" / "ledger.csv"
MARKER = ROOT / "output" / "p1_down_shadow.jsonl"
LOG = ROOT / "output" / "logs" / "p1_down_shadow.log"


def _log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def bare(sym) -> str:
    s = str(sym or "").split(".")[0].upper()
    for pre in ("SH", "SZ", "BJ"):
        s = s.replace(pre, "")
    return s.zfill(6)[-6:] if s else ""


def load_kline():
    df = pd.read_parquet(KLINE, columns=["symbol", "date", "open", "close",
                                         "high", "low", "volume"])
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df["symbol"] = df["symbol"].map(bare)
    return df.sort_values(["symbol", "date"]).reset_index(drop=True)


def last_archive_day() -> str:
    days = sorted(p.name for p in ARCH.iterdir() if p.is_dir())
    for dd in reversed(days):
        if (ARCH / dd / "top10_ungated.json").exists():
            return dd
    return ""


def pick_pool(dd: str):
    up = ARCH / dd / "top10_ungated.json"
    if not up.exists():
        return []
    x = json.loads(up.read_text(encoding="utf-8"))
    picks = x.get("picks", []) if isinstance(x, dict) else x
    out = []
    for it in picks:
        s = bare(it.get("symbol"))
        if s:
            out.append({"symbol": s, "name": it.get("name", ""),
                        "rank": it.get("rank")})
    return out


def event_day_state(df, symbol, asof: pd.Timestamp):
    """Return compute_series state/score/raw + previous day state for `symbol`
    at asof day using the reference calc over ascending rows INCLUDING asof's
    completed bar. The caller runs after close, so asof bar is complete (same
    as cross-validation backfill). None on short history."""
    sub = df[df["symbol"] == symbol]
    if len(sub) < 70:
        return None
    sub = sub[sub["date"] <= asof]
    if len(sub) < 70:
        return None
    rows = [(r["date"].strftime("%Y-%m-%d"), float(r["open"]), float(r["close"]),
             float(r["high"]), float(r["low"]), float(r["volume"]))
            for _, r in sub.iterrows()]
    try:
        ser = wb.compute_series(rows)
    except Exception:
        return None
    if not ser:
        return None
    last = ser[-1]
    if last.get("state") is None:
        return None
    prev_state = None
    for rec in reversed(ser[:-1]):
        if rec.get("state") is not None:
            prev_state = rec["state"]
            break
    return {"state": last["state"], "score": last["score"],
            "raw": last.get("raw"), "date": last["date"],
            "prev_state": prev_state}


def t5_settle(df, symbol, asof: pd.Timestamp):
    """open-base T+5 from event day. Returns dict or None when not yet
    settleable (needs 5 more trading days in kline)."""
    sub = df[df["symbol"] == symbol].reset_index(drop=True)
    dates = sub["date"].tolist()
    if asof not in dates:
        return None
    pos = dates.index(asof)
    if pos + 5 >= len(dates):
        return None
    base = float(sub.iloc[pos]["open"])
    if base <= 0:
        return None
    t5 = float(sub.iloc[pos + 5]["close"]) / base - 1.0
    return {"base_open": round(base, 3),
            "t5_close": round(float(sub.iloc[pos + 5]["close"]), 3),
            "ret_t5": round(t5, 4),
            "t5_date": dates[pos + 5].strftime("%Y-%m-%d")}


def read_events():
    if not EVENTS.exists():
        return []
    return [json.loads(ln) for ln in
            EVENTS.read_text(encoding="utf-8").splitlines() if ln.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", default="")
    args = ap.parse_args()

    EVENTS.parent.mkdir(parents=True, exist_ok=True)
    kdf = load_kline()
    kline_max = kdf["date"].max()

    if args.asof:
        asof_str = args.asof
    else:
        asof_str = last_archive_day()
    if not asof_str:
        _log("p1_down: no archive day with top10_ungated -> SKIP")
        return 0
    asof = pd.Timestamp(asof_str)
    if asof > kline_max:
        _log(f"p1_down: asof {asof_str} > kline max {kline_max.date()} -> SKIP")
        return 0

    pool = pick_pool(asof_str)
    _log(f"p1_down asof={asof_str} pool={len(pool)}")

    # ---------- 1) log DOWN events for this asof (append once) ----------
    events = read_events()
    already = {e["asof"] for e in events}
    newly = 0
    if asof_str not in already:
        for it in pool:
            st = event_day_state(kdf, it["symbol"], asof)
            if st is None:
                continue
            if st["state"] == "DOWN":
                events.append({
                    "asof": asof_str, "symbol": it["symbol"],
                    "name": it["name"], "rank": it.get("rank"),
                    "state": st["state"], "score": st["score"],
                    "raw": st.get("raw"),
                    "prev_state": st.get("prev_state"),
                    "is_switch": st.get("prev_state") != "DOWN",
                })
                newly += 1
        with EVENTS.open("w", encoding="utf-8") as f:
            for e in events:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        _log(f"p1_down: appended {newly} DOWN event(s) for {asof_str}")
    else:
        _log(f"p1_down: {asof_str} already logged ({len(events)} total)")

    # ---------- 2) settle all events that now have 5 future bars ----------
    settle = {"done": 0, "pending": 0}
    for e in events:
        if "ret_t5" in e:
            continue
        ed = pd.Timestamp(e["asof"])
        if ed > kline_max:
            settle["pending"] += 1
            continue
        s5 = t5_settle(kdf, e["symbol"], ed)
        if s5 is None:
            settle["pending"] += 1
        else:
            e.update(s5)
            settle["done"] += 1
    with EVENTS.open("w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    _log(f"p1_down settle: done={settle['done']} pending={settle['pending']}")

    # ---------- 3) rewrite ledger.csv + daily marker ----------
    down = [e for e in events if e.get("state") == "DOWN"]
    settled = [e for e in down if "ret_t5" in e]
    rows = []
    for e in down:
        rows.append({"asof": e["asof"], "symbol": e["symbol"], "name": e["name"],
                     "score": e.get("score"), "ret_t5": e.get("ret_t5")})
    with LEDGER.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["asof", "symbol", "name", "score",
                                          "ret_t5"])
        w.writeheader()
        for r in rows:
            w.writerow(r)

    rets = [e["ret_t5"] for e in settled]
    marker = {
        "asof": asof_str,
        "n_pool": len(pool),
        "n_down_total": len(down),
        "n_settled": len(rets),
        "ret_t5_mean": round(sum(rets) / len(rets), 4) if rets else None,
        "win": round(sum(1 for r in rets if r > 0) / len(rets), 3) if rets else None,
    }
    # idempotent marker: skip when this asof already has a marker line
    existing_markers = set()
    if MARKER.exists():
        for ln in MARKER.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            try:
                existing_markers.add(json.loads(ln).get("asof"))
            except Exception:
                pass
    if asof_str not in existing_markers:
        with MARKER.open("a", encoding="utf-8") as f:
            f.write(json.dumps(marker, ensure_ascii=False) + "\n")
    _log(f"p1_down marker: n_down_total={len(down)} settled={len(rets)}"
         f" mean_t5={marker['ret_t5_mean']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
