# -*- coding: utf-8 -*-
"""
Fetch historical per-tick transaction data for backtest candidates via mootdx
and aggregate active-buy ratio per (symbol, date, 5m bar).

Data source: mootdx.transactions() == TDX get_history_transaction_data
  - free, no L2 permission, historical dates supported (tested 2026-04~08)
  - buyorsell: 0=active buy, 1=active sell, 2=neutral, 5/8=auction
  - 800 rows per page; paginate with start offset

Output: {out_dir}/{symbol}_{date}.json -> {"t5": {"buy": n, "sell": n,
          "abr": f, "vol": n}, ...} keyed by 5m bar minute-of-day (09:35, ...)

We only need active buy/sell volumes, aggregated per 5-minute bar so the
backtest can consume them like another 5m-K-line field.
"""
import argparse
import json
import os
import sys
import time
import warnings

warnings.filterwarnings("ignore")

DEFAULT_OUT = r"D:\alphapilot\data\tick_abr"


def _bare(sym: str) -> str:
    return str(sym).split(".")[0]


def _market(code: str) -> int:
    if code.startswith(("6", "5", "9")):
        return 1  # SH
    if code.startswith(("0", "3", "2")):
        return 0  # SZ
    if code.startswith(("4", "8")):
        return 0  # BJ (TDX market 0)
    return 1


def time_to_tmin(t: str) -> int | None:
    """HH:MM -> minutes since midnight. None if not parseable."""
    try:
        hh, mm = t.split(":")
        return int(hh) * 60 + int(mm)
    except Exception:
        return None


def bucket5(tmin: int) -> int:
    """Map minute-of-day to 5m bucket start (09:35, 09:40, ...)."""
    # trading bars: 09:35..11:30, 13:05..15:00
    # our 5m buckets align to K-line bars in bt_dyn_confirm_long
    return tmin - (tmin % 5)


def fetch_one(client, code: str, date: str, retries=2):
    """Fetch all ticks for one symbol/date. Returns list of dicts or None."""
    rows = []
    start = 0
    for attempt in range(retries + 1):
        try:
            while True:
                df = client.transactions(symbol=code, start=start,
                                         offset=800, date=date)
                if df is None or len(df) == 0:
                    break
                for _, r in df.iterrows():
                    rows.append({
                        "t": str(r.get("time", "")),
                        "p": float(r.get("price", 0) or 0),
                        "v": float(r.get("vol", 0) or 0),
                        "bs": int(r.get("buyorsell", -1)),
                    })
                if len(df) < 800:
                    break
                start += 800
                if start > 100000:
                    break
            return rows
        except Exception as e:
            if attempt >= retries:
                return None
            time.sleep(1.0 * (attempt + 1))
    return None


def aggregate(rows, out):
    """Aggregate rows into per-5m-bucket buy/sell. Writes out."""
    if not rows:
        return None
    agg = {}
    for r in rows:
        tmin = time_to_tmin(r["t"])
        if tmin is None:
            continue
        b5 = bucket5(tmin)
        # continuous session only (09:30-11:30, 13:00-15:00); skip auction
        if tmin < 9 * 60 + 30 or (11 * 60 + 30 < tmin < 13 * 60):
            continue
        bs = r["bs"]
        v = r["v"]
        if v <= 0:
            continue
        a = agg.setdefault(b5, {"buy": 0.0, "sell": 0.0, "vol": 0.0})
        a["vol"] += v
        if bs == 0:
            a["buy"] += v
        elif bs == 1:
            a["sell"] += v
    # finalize: compute abr per bucket
    for b5, a in agg.items():
        tot = a["buy"] + a["sell"]
        a["abr"] = round(a["buy"] / tot, 4) if tot > 0 else None
    with open(out, "w", encoding="utf-8") as f:
        json.dump(agg, f, ensure_ascii=False)
    return agg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dates-json",
                    default=r"C:\Users\elvisq\Projects\alphapilot\production_strategies\track_a\_top10_dates.json")
    ap.add_argument("--out-dir", default=DEFAULT_OUT)
    ap.add_argument("--limit", type=int, default=0,
                    help="limit symbol/date pairs (0=all)")
    ap.add_argument("--start", type=int, default=0,
                    help="start index into the pair list (resume)")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    from mootdx.quotes import Quotes
    client = Quotes.factory(market="std", multithread=True)

    plan = json.load(open(args.dates_json, encoding="utf-8"))
    pairs = []
    for date, info in plan.items():
        for sym in info["symbols"]:
            pairs.append((date, _bare(sym)))
    pairs = pairs[args.start:]
    if args.limit:
        pairs = pairs[:args.limit]

    print(f"[fetch] pairs={len(pairs)} out={args.out_dir}", flush=True)
    t0 = time.time()
    ok = fail = skip = 0
    for i, (date, code) in enumerate(pairs):
        # date in dates-json is like 2026-04-01 -> 20260401
        d = date.replace("-", "")
        out = os.path.join(args.out_dir, f"{code}_{d}.json")
        if os.path.exists(out):
            skip += 1
            continue
        rows = fetch_one(client, code, d)
        if rows is None:
            fail += 1
            print(f"  FAIL {code} {d}", flush=True)
            continue
        agg = aggregate(rows, out)
        if agg:
            ok += 1
        else:
            # write empty marker to avoid refetch
            with open(out, "w", encoding="utf-8") as f:
                json.dump({}, f, ensure_ascii=False)
            skip += 1
        if (i + 1) % 25 == 0 or i == len(pairs) - 1:
            el = time.time() - t0
            print(f"  ... {i+1}/{len(pairs)} ok={ok} fail={fail} skip={skip} "
                  f"el={el:.0f}s", flush=True)
    print(f"[fetch] done ok={ok} fail={fail} skip={skip} "
          f"el={time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
