#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""周末补测：用最近交易日（默认上周五）做 as-of 烟测。"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(os.environ.get("ALPHAPILOT_ROOT", "/home/ubuntu/alphapilot"))
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))


def last_friday(today: datetime | None = None) -> str:
    d = (today or datetime.now()).date()
    # Mon=0 ... Sun=6; Friday=4
    delta = (d.weekday() - 4) % 7
    if delta == 0 and d.weekday() != 4:
        delta = 7
    # if today is Fri, use today; if Sat/Sun/Mon.. use previous Fri
    if d.weekday() == 4:
        fri = d
    else:
        # days since last Friday
        fri = d - timedelta(days=(d.weekday() - 4) % 7 or 7)
    return fri.isoformat()


def main() -> int:
    asof = sys.argv[1] if len(sys.argv) > 1 else last_friday()
    print(f"ROOT={ROOT}")
    print(f"ASOF={asof} (weekday check / Friday smoke)")
    report: dict = {"asof": asof, "ok": [], "warn": [], "fail": []}

    def ok(m):
        report["ok"].append(m)
        print(f"  ✅ {m}", flush=True)

    def warn(m):
        report["warn"].append(m)
        print(f"  ⚠️ {m}", flush=True)

    def fail(m):
        report["fail"].append(m)
        print(f"  ❌ {m}", flush=True)

    # 1) market env as-of
    print("\n== 大盘环境 as-of ==", flush=True)
    try:
        from market_env_gate import (
            apply_market_env_gate,
            build_env_asof,
            fetch_all_index_klines,
            position_exposure,
        )

        hist = fetch_all_index_klines(lmt=80)
        for k, v in hist.items():
            print(f"  index {k}: {len(v)} bars last={v[-1]['date'] if v else None}", flush=True)
        env = build_env_asof(hist, asof)
        flags = env.get("flags") or {}
        expo = float(env.get("position_exposure", position_exposure(flags)))
        ok(f"flags={flags} exposure={expo}")
        for k, st in (env.get("indexes") or {}).items():
            print(
                f"    {st.get('name', k)}: 5d={st.get('ret_5d')}% 10d={st.get('ret_10d')}% "
                f"weak={st.get('weak')} severe={st.get('severe')} last={st.get('last_date')}",
                flush=True,
            )
        report["market_env"] = {"flags": flags, "position_exposure": expo, "indexes": env.get("indexes")}

        demo = [
            {"symbol": "300750", "score": 0.70, "name": "宁德时代"},
            {"symbol": "688981", "score": 0.68, "name": "中芯国际"},
            {"symbol": "600519", "score": 0.65, "name": "贵州茅台"},
            {"symbol": "000001", "score": 0.60, "name": "平安银行"},
        ]
        imap = {}
        ip = ROOT / "data/stock_industry_map.json"
        if ip.exists():
            imap = json.loads(ip.read_text(encoding="utf-8"))
        gated = apply_market_env_gate(demo, env=env, hard_filter=True, industry_map=imap)
        ok(f"market_env gate kept {len(gated)}/{len(demo)}: {[x['symbol'] for x in gated]}")
        report["market_env"]["kept"] = [x["symbol"] for x in gated]
    except Exception as e:
        fail(f"market_env asof: {e}")
        import traceback

        traceback.print_exc()

    # 2) VM2.5 score as-of Friday bar
    print("\n== VM2.5 as-of 打分 ==", flush=True)
    try:
        import pandas as pd
        from vm25_scorer import VM25Scorer
        from backtest_v3_pipeline import volume_gc_asof, fund_gate_ok
        from vm25_scorer import _bare

        scorer = VM25Scorer(prefer="opt")
        assert scorer.load()
        kpath = ROOT / "data/kline_cache/kline_all.parquet"
        if not kpath.exists():
            kpath = ROOT / "kline_all.parquet"
        df = pd.read_parquet(kpath)
        df["date"] = df["date"].astype(str).str[:10]
        df["symbol"] = df["symbol"].astype(str).map(_bare)
        # calendar: does asof exist?
        cal = sorted(df.loc[df["symbol"] == "600519", "date"].unique())
        if asof not in set(cal):
            # nearest trading day <= asof
            prev = [d for d in cal if d <= asof]
            if not prev:
                fail(f"no calendar day <= {asof}")
                raise SystemExit(1)
            warn(f"{asof} not in kline; use {prev[-1]}")
            asof = prev[-1]
            report["asof_effective"] = asof

        samples = ["600519", "300750", "688981", "000001"]
        rows = []
        for sym in samples:
            g = df[df["symbol"] == sym].sort_values("date").reset_index(drop=True)
            idxs = g.index[g["date"] <= asof]
            if len(idxs) == 0:
                warn(f"{sym}: no bars <= {asof}")
                continue
            ai = int(idxs[-1])
            if str(g.loc[ai, "date"]) != asof:
                warn(f"{sym}: last bar {g.loc[ai, 'date']} != {asof}")
            sub = g.iloc[: ai + 1]
            r = scorer.score(sub, sym, sector_heat=0.5)
            gc = bool(volume_gc_asof(g, ai))
            fh = scorer.fund_flow.get(sym, {})
            fund_ok = bool(fund_gate_ok(fh, asof, 5))
            rows.append(
                {
                    "symbol": sym,
                    "date": str(g.loc[ai, "date"]),
                    "score": r.get("score"),
                    "gc": gc,
                    "fund_ok": fund_ok,
                    "close": float(g.loc[ai, "close"]),
                }
            )
            print(
                f"  {sym}: score={r.get('score')} gc={gc} fund_ok={fund_ok} close={g.loc[ai, 'close']}",
                flush=True,
            )
        if rows:
            ok(f"scored {len(rows)} samples on {asof}")
        else:
            fail("no samples scored")
        report["scores"] = rows
    except Exception as e:
        fail(f"score asof: {e}")
        import traceback

        traceback.print_exc()

    # 3) one-day tradable Top3 replay (A1 style, cheap)
    print("\n== 可交易 Top3 单日重放 ==", flush=True)
    try:
        import numpy as np
        import pandas as pd
        from vm25_scorer import VM25Scorer, _bare
        from backtest_v3_pipeline import volume_gc_asof, fund_gate_ok
        from market_env_gate import (
            apply_market_env_gate,
            build_env_asof,
            fetch_all_index_klines,
            stock_board,
        )
        from backtest_v3_tradable_gated import limit_pct, day_chg, near_limit, settle_tradable

        asof_eff = report.get("asof_effective", asof)
        scorer = VM25Scorer(prefer="opt")
        scorer.load()
        kpath = ROOT / "data/kline_cache/kline_all.parquet"
        if not kpath.exists():
            kpath = ROOT / "kline_all.parquet"
        kdf = pd.read_parquet(kpath)
        kdf["date"] = kdf["date"].astype(str).str[:10]
        kdf["symbol"] = kdf["symbol"].astype(str).map(_bare)
        kdf = kdf[~kdf["symbol"].str.startswith(("8", "4"))]
        groups = {s: g.sort_values("date").reset_index(drop=True) for s, g in kdf.groupby("symbol")}

        imap = {}
        ip = ROOT / "data/stock_industry_map.json"
        if ip.exists():
            imap = json.loads(ip.read_text(encoding="utf-8"))

        hist = fetch_all_index_klines(lmt=80)
        env = build_env_asof(hist, asof_eff)
        expo = float(env.get("position_exposure", 1.0))

        pool = []
        for sym, g in groups.items():
            idxs = g.index[g["date"] <= asof_eff]
            if len(idxs) == 0:
                continue
            ai = int(idxs[-1])
            if str(g.loc[ai, "date"]) != asof_eff:
                continue
            if ai + 2 >= len(g):
                continue
            lim = limit_pct(sym)
            chg = day_chg(g, ai)
            if near_limit(chg, lim, 0.97):
                continue
            if not volume_gc_asof(g, ai):
                continue
            fh = scorer.fund_flow.get(sym, {})
            if not fund_gate_ok(fh, asof_eff, 5):
                continue
            sub = g.iloc[: ai + 1]
            try:
                r = scorer.score(sub, sym)
            except Exception:
                continue
            if "error" in r:
                continue
            ind = imap.get(sym) or {}
            pool.append(
                {
                    "symbol": sym,
                    "ai": ai,
                    "score": float(r["score"]),
                    "signal_chg": chg,
                    "industry_l1": ind.get("industry_l1"),
                    "board": stock_board(sym),
                }
            )

        print(f"  strictGC+fund pool={len(pool)} expo={expo}", flush=True)
        if expo <= 0:
            ok("A1 empty book (market_severe) — no trades Friday")
            picks = []
        else:
            cands = apply_market_env_gate(pool, env=env, hard_filter=True, industry_map=imap)
            picks = sorted(cands, key=lambda x: -x["score"])[:3]
            ok(f"A1 candidates after env={len(cands)} Top3={[p['symbol'] for p in picks]}")

        trades = []
        for p in picks:
            st = settle_tradable(groups[p["symbol"]], p["ai"], 0.0015)
            if not st or st.get("skip"):
                trades.append({"symbol": p["symbol"], "skipped": True, "reason": (st or {}).get("skip")})
                continue
            raw = float(st["ret"])
            trades.append(
                {
                    "symbol": p["symbol"],
                    "score": p["score"],
                    "industry_l1": p.get("industry_l1"),
                    "buy_date": st["buy_date"],
                    "sell_date": st["sell_date"],
                    "ret_raw": raw,
                    "ret_scaled": raw * expo,
                    "hit_3pct": raw * expo >= 0.03,
                }
            )
            print(
                f"  {p['symbol']}: score={p['score']:.4f} ret_raw={raw*100:.2f}% "
                f"scaled={raw*expo*100:.2f}% buy={st['buy_date']} sell={st['sell_date']}",
                flush=True,
            )

        report["day_replay"] = {
            "asof": asof_eff,
            "pool": len(pool),
            "exposure": expo,
            "picks": picks,
            "trades": trades,
        }
        if picks and not trades:
            warn("picks exist but no settled trades (need T+2 bars)")
    except Exception as e:
        fail(f"day replay: {e}")
        import traceback

        traceback.print_exc()

    # 4) sector dual note (live snapshot = not Friday as-of)
    print("\n== 板块 dual 说明 ==", flush=True)
    try:
        from sector_rotation_gate import build_snapshot

        snap = build_snapshot()
        warn(
            "sector/concept flow snapshot is live/latest cache, NOT historical Friday as-of; "
            f"industry_allow={len((snap.get('classes') or {}).get('allow', []))} "
            f"deny={len((snap.get('classes') or {}).get('deny', []))}"
        )
        report["sector_dual_note"] = "live snapshot only"
    except Exception as e:
        warn(f"sector snapshot: {e}")

    out = ROOT / "output" / "friday_asof_smoke.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    report["pass"] = len(report["fail"]) == 0
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("\n======== SUMMARY ========", flush=True)
    print(f"OK={len(report['ok'])} WARN={len(report['warn'])} FAIL={len(report['fail'])}", flush=True)
    print(f"saved {out}", flush=True)
    print("FRIDAY_SMOKE_PASS" if report["pass"] else "FRIDAY_SMOKE_FAIL", flush=True)
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
