#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""可交易 Top2 + 大盘降仓 / 科技硬过滤 验收回测。

相对 backtest_v3_tradable_top3.py：
  A0            baseline：严格金叉 + 资金硬门控 + Top2
  A1_cur        旧口径：severe→expo=0
  A1_ladder     阶梯 v2：severe+crash→0；severe→0.25
  A1_permission 许可门：宽度+sustained_in；nuclear 仅 crash+rotation_dead
  A2            跟 A1_permission；仅 expo=0 可走袖套研究

协议同可交易口径：T 信号 → T+1 开盘买（非涨停）→ T+2 收盘卖 → 成本 15bp → ≥3%。

行业×概念 dual 用当日资金流，历史不可 as-of；本回测用指数 as-of 代理风格门控。
生产仍跑 sector_rotation_gate dual。
"""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/ubuntu/alphapilot")
os.chdir(ROOT)

from vm25_scorer import VM25Scorer, _bare
from backtest_v3_pipeline import volume_gc_asof, fund_gate_ok
from market_env_gate import (
    apply_market_env_gate,
    build_env_asof,
    fetch_all_index_klines,
    position_exposure_ladder,
    position_exposure_legacy,
    recommend_top_n,
    stock_board,
)
from permission_gate import enrich_env_with_permission, position_exposure_permission
from weak_rotation_sleeve import (
    MAX_EXPOSURE as SLEEVE_EXPO,
    build_strong_universe,
    load_industry_map,
    scan_sleeve,
)


def limit_pct(symbol: str) -> float:
    s = _bare(symbol)
    if s.startswith(("300", "301", "688")):
        return 0.20
    if s.startswith(("8", "4")):
        return 0.30
    return 0.10


def day_chg(g: pd.DataFrame, ai: int) -> float | None:
    if ai < 1:
        return None
    prev = float(g.loc[ai - 1, "close"])
    cur = float(g.loc[ai, "close"])
    if prev <= 0:
        return None
    return cur / prev - 1


def near_limit(chg: float | None, lim: float, frac: float = 0.97) -> bool:
    if chg is None:
        return False
    return chg >= lim * frac


def settle_tradable(g: pd.DataFrame, signal_ai: int, cost_rt: float):
    bi = signal_ai + 1
    si = signal_ai + 2
    if si >= len(g):
        return None
    sym = str(g.loc[signal_ai, "symbol"]) if "symbol" in g.columns else ""
    lim = limit_pct(sym)
    buy_open = float(g.loc[bi, "open"])
    prev_close = float(g.loc[signal_ai, "close"])
    if prev_close <= 0 or buy_open <= 0:
        return None
    open_gap = buy_open / prev_close - 1
    if open_gap >= lim * 0.97:
        return {"skip": "open_limit", "buy_date": str(g.loc[bi, "date"])}
    sell_close = float(g.loc[si, "close"])
    gross = sell_close / buy_open - 1
    net = gross - cost_rt
    return {
        "skip": None,
        "buy_date": str(g.loc[bi, "date"]),
        "sell_date": str(g.loc[si, "date"]),
        "buy": buy_open,
        "sell": sell_close,
        "gross_ret": gross,
        "ret": net,
        "open_gap": open_gap,
    }


def max_drawdown(day_rets: np.ndarray) -> float:
    if len(day_rets) == 0:
        return 0.0
    eq = np.cumprod(1.0 + day_rets)
    peak = np.maximum.accumulate(eq)
    dd = eq / peak - 1.0
    return float(dd.min())


def summarize(trades: list, name: str, thr: float, calendar_days: list[str], day_expo: dict) -> dict:
    filled = [t for t in trades if not t.get("skipped")]
    skipped = [t for t in trades if t.get("skipped")]
    by = defaultdict(list)
    for t in filled:
        by[t["date"]].append(float(t["ret"]))

    # 含空仓日：exposure=0 或无成交 → 日收益 0
    day = []
    for d in calendar_days:
        expo = float(day_expo.get(d, 1.0))
        if expo <= 0 or d not in by:
            day.append(0.0)
        else:
            day.append(float(np.mean(by[d])))
    day_arr = np.array(day, float)

    if not filled:
        return {
            "arm": name,
            "n_signals": len(trades),
            "n_filled": 0,
            "n_skipped": len(skipped),
            "fill_rate": 0.0,
            "n_days": len(calendar_days),
            "empty_days": int(sum(1 for d in calendar_days if float(day_expo.get(d, 1.0)) <= 0)),
            "avg_exposure": float(np.mean([float(day_expo.get(d, 1.0)) for d in calendar_days])),
            "day_avg_return": float(day_arr.mean()) if len(day_arr) else 0.0,
            "max_drawdown": max_drawdown(day_arr),
            "total_return": float(np.prod(1.0 + day_arr) - 1.0) if len(day_arr) else 0.0,
        }

    rets = np.array([t["ret"] for t in filled], float)
    trade_days = sorted(by)
    return {
        "arm": name,
        "n_signals": len(trades),
        "n_filled": len(filled),
        "n_skipped": len(skipped),
        "fill_rate": float(len(filled) / max(len(trades), 1)),
        "n_days": len(calendar_days),
        "n_trade_days": len(trade_days),
        "empty_days": int(sum(1 for d in calendar_days if float(day_expo.get(d, 1.0)) <= 0)),
        "avg_exposure": float(np.mean([float(day_expo.get(d, 1.0)) for d in calendar_days])),
        "win_rate": float((rets > 0).mean()),
        "hit_3pct_rate": float((rets >= thr).mean()),
        "avg_return": float(rets.mean()),
        "median_return": float(np.median(rets)),
        "day_win_rate": float((day_arr > 0).mean()),
        "day_avg_return": float(day_arr.mean()),
        "max_drawdown": max_drawdown(day_arr),
        "total_return": float(np.prod(1.0 + day_arr) - 1.0),
        "skip_reasons": {
            k: int(sum(1 for t in skipped if t.get("skip_reason") == k))
            for k in sorted({t.get("skip_reason") for t in skipped if t.get("skip_reason")})
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-04-01")
    ap.add_argument("--end", default="2026-07-17")
    ap.add_argument("--top-n", type=int, default=2)
    ap.add_argument("--threshold", type=float, default=0.03)
    ap.add_argument("--cost-rt", type=float, default=0.0015)
    ap.add_argument("--prefer", default="opt")
    ap.add_argument("--limit-frac", type=float, default=0.97)
    ap.add_argument("--sleeve-top-n", type=int, default=2)
    args = ap.parse_args()

    print("=== 可交易 Top2 + 大盘降仓 + 弱市袖套验收 ===")
    print(
        f"{args.start}~{args.end} top_n={args.top_n} sleeve_top_n={args.sleeve_top_n} "
        f"thr={args.threshold} cost_rt={args.cost_rt} | buy=T+1 open sell=T+2 close"
    )
    os.environ.setdefault("WEAK_TRADE_ON_COLLAPSE", "0")
    os.environ.setdefault("ENABLE_WEAK_ROTATION_SLEEVE", "1")

    scorer = VM25Scorer(prefer=args.prefer)
    assert scorer.load()

    imap_path = ROOT / "data/stock_industry_map.json"
    industry_map = {}
    if imap_path.exists():
        industry_map = json.loads(imap_path.read_text(encoding="utf-8"))
        print(f"industry_map={len(industry_map)}")

    print("fetch index history for as-of env...", flush=True)
    index_hist = fetch_all_index_klines(lmt=160)
    for k, v in index_hist.items():
        print(f"  {k}: {len(v)} bars", flush=True)

    kpath = ROOT / "data/kline_cache/kline_all.parquet"
    if not kpath.exists():
        kpath = ROOT / "kline_all.parquet"
    kdf = pd.read_parquet(kpath)
    kdf["date"] = kdf["date"].astype(str).str[:10]
    kdf["symbol"] = kdf["symbol"].astype(str).map(_bare)
    kdf = kdf[~kdf["symbol"].str.startswith(("8", "4"))]
    groups = {s: g.sort_values("date").reset_index(drop=True) for s, g in kdf.groupby("symbol")}

    cal_sym = "600519" if "600519" in groups else next(iter(groups))
    dates = sorted(d for d in groups[cal_sym]["date"].unique() if args.start <= d <= args.end)
    print(f"stocks={len(groups)} signal_days={len(dates)} calendar={cal_sym}")

    arms = {
        "A0_baseline": [],
        "A1_cur": [],
        "A1_ladder": [],
        "A1_permission": [],
        "A2_gated_plus_sleeve": [],
    }
    day_expo = {
        "A0_baseline": {},
        "A1_cur": {},
        "A1_ladder": {},
        "A1_permission": {},
        "A2_gated_plus_sleeve": {},
    }
    sleeve_days = []
    t0 = time.time()

    # 袖套用强势股宇宙：覆盖窗口前若干日
    sleeve_imap = load_industry_map() or industry_map
    all_cal = sorted(groups[cal_sym]["date"].unique())
    pre = [d for d in all_cal if d < args.start][-5:]
    strong_days = pre + dates
    print("building strong>=3% universe for sleeve...", flush=True)
    strong_by_day = build_strong_universe(kdf, sleeve_imap, strong_days, thr_pct=3.0)

    for di, date in enumerate(dates):
        env = build_env_asof(index_hist, date)
        env = enrich_env_with_permission(dict(env), asof=date, kdf=kdf)
        flags = env.get("flags") or {}
        perm = env.get("permission") or {}
        expo_ladder = float(position_exposure_ladder(flags))
        expo_cur = float(position_exposure_legacy(flags))
        expo_perm = float(position_exposure_permission(flags, perm))
        env["position_exposure"] = expo_perm
        day_expo["A0_baseline"][date] = 1.0
        day_expo["A1_cur"][date] = expo_cur
        day_expo["A1_ladder"][date] = expo_ladder
        day_expo["A1_permission"][date] = expo_perm
        # A2 跟 permission；仅 nuclear 可走袖套
        day_expo["A2_gated_plus_sleeve"][date] = expo_perm

        strict_pool = []
        for sym, g in groups.items():
            idxs = g.index[g["date"] <= date]
            if len(idxs) == 0:
                continue
            ai = int(idxs[-1])
            if str(g.loc[ai, "date"]) != date:
                continue
            if ai + 2 >= len(g):
                continue

            lim = limit_pct(sym)
            chg = day_chg(g, ai)
            if near_limit(chg, lim, args.limit_frac):
                continue
            if not volume_gc_asof(g, ai):
                continue

            sub = g.iloc[: ai + 1].copy()
            try:
                r = scorer.score(sub, sym)
            except Exception:
                continue
            if "error" in r:
                continue

            fh = scorer.fund_flow.get(sym, {})
            if not fund_gate_ok(fh, date, 5):
                continue

            ind = industry_map.get(sym) or {}
            strict_pool.append(
                {
                    "symbol": sym,
                    "ai": ai,
                    "score": float(r["score"]),
                    "signal_chg": chg,
                    "industry_l1": ind.get("industry_l1"),
                    "board": stock_board(sym),
                }
            )

        def push(pool, arm: str, use_gate: bool, expo_override: float | None = None):
            cands = list(pool)
            cur_expo = 1.0
            if use_gate:
                cur_expo = float(day_expo[arm][date] if expo_override is None else expo_override)
                if cur_expo <= 0:
                    return len(cands), 0
                cands = apply_market_env_gate(
                    cands, env=env, hard_filter=True, mode="soft_demote", industry_map=industry_map
                )
            elif expo_override is not None:
                cur_expo = float(expo_override)
            n_pick = recommend_top_n(cur_expo, default=args.top_n)
            picks = sorted(cands, key=lambda x: -x["score"])[:n_pick]
            for p in picks:
                g = groups[p["symbol"]]
                st = settle_tradable(g, p["ai"], args.cost_rt)
                if st is None:
                    arms[arm].append(
                        {
                            "date": date,
                            "symbol": p["symbol"],
                            "skipped": True,
                            "skip_reason": "no_bar",
                            "score": p.get("score"),
                            "exposure": cur_expo,
                            "source": p.get("source", "main"),
                        }
                    )
                    continue
                if st.get("skip"):
                    arms[arm].append(
                        {
                            "date": date,
                            "symbol": p["symbol"],
                            "skipped": True,
                            "skip_reason": st["skip"],
                            "buy_date": st.get("buy_date"),
                            "score": p.get("score"),
                            "exposure": cur_expo,
                            "source": p.get("source", "main"),
                        }
                    )
                    continue
                raw = float(st["ret"])
                scaled = raw * cur_expo
                arms[arm].append(
                    {
                        "date": date,
                        "symbol": p["symbol"],
                        "skipped": False,
                        "ret_raw": raw,
                        "ret": scaled,
                        "gross_ret": st["gross_ret"],
                        "buy": st["buy"],
                        "sell": st["sell"],
                        "buy_date": st["buy_date"],
                        "sell_date": st["sell_date"],
                        "score": p.get("score"),
                        "exposure": cur_expo,
                        "win": scaled > 0,
                        "hit_3pct": scaled >= args.threshold,
                        "signal_chg": p.get("signal_chg"),
                        "open_gap": st["open_gap"],
                        "industry_l1": p.get("industry_l1"),
                        "board": p.get("board"),
                        "source": p.get("source", "main"),
                    }
                )
            return len(cands), len(picks)

        p0, n0 = push(strict_pool, "A0_baseline", use_gate=False)
        p1c, n1c = push(strict_pool, "A1_cur", use_gate=True)
        # ladder / permission 需各自 expo 写回 env 供 hard gate 日志用
        env["position_exposure"] = expo_ladder
        p1, n1 = push(strict_pool, "A1_ladder", use_gate=True)
        env["position_exposure"] = expo_perm
        p1p, n1p = push(strict_pool, "A1_permission", use_gate=True)

        # A2：跟 permission；仅 nuclear（expo=0）日尝试袖套
        n2 = 0
        sleeve_note = ""
        expo = expo_perm
        if expo > 0:
            _, n2 = push(strict_pool, "A2_gated_plus_sleeve", use_gate=True)
        else:
            strong_asof = {k: v for k, v in strong_by_day.items() if k <= date}
            sleeve = scan_sleeve(
                asof_signal=date,
                trade_day=None,
                kdf=kdf,
                strong_by_day=strong_asof,
                top_n=args.sleeve_top_n,
            )
            picked = sleeve.get("picked") or []
            if not picked:
                day_expo["A2_gated_plus_sleeve"][date] = 0.0
                sleeve_note = f"sleeve_skip={sleeve.get('skip_reason') or 'empty'}"
            else:
                cur_expo = float(SLEEVE_EXPO)
                day_expo["A2_gated_plus_sleeve"][date] = cur_expo
                sleeve_pool = []
                for p in picked:
                    sym = _bare(p["symbol"])
                    g = groups.get(sym)
                    if g is None:
                        continue
                    idxs = g.index[g["date"] == date]
                    if len(idxs) == 0:
                        continue
                    ai = int(idxs[0])
                    if ai + 2 >= len(g):
                        continue
                    sleeve_pool.append(
                        {
                            "symbol": sym,
                            "ai": ai,
                            "score": float(p.get("score") or 0),
                            "signal_chg": p.get("chg"),
                            "industry_l1": p.get("industry_l1"),
                            "board": p.get("board"),
                            "source": "weak_sleeve",
                        }
                    )
                # 袖套池不再走指数硬删（已是 severe 卫星）
                for p in sleeve_pool[: args.sleeve_top_n]:
                    g = groups[p["symbol"]]
                    st = settle_tradable(g, p["ai"], args.cost_rt)
                    if st is None:
                        arms["A2_gated_plus_sleeve"].append(
                            {
                                "date": date,
                                "symbol": p["symbol"],
                                "skipped": True,
                                "skip_reason": "no_bar",
                                "score": p["score"],
                                "exposure": cur_expo,
                                "source": "weak_sleeve",
                            }
                        )
                        continue
                    if st.get("skip"):
                        arms["A2_gated_plus_sleeve"].append(
                            {
                                "date": date,
                                "symbol": p["symbol"],
                                "skipped": True,
                                "skip_reason": st["skip"],
                                "buy_date": st.get("buy_date"),
                                "score": p["score"],
                                "exposure": cur_expo,
                                "source": "weak_sleeve",
                            }
                        )
                        continue
                    raw = float(st["ret"])
                    scaled = raw * cur_expo
                    arms["A2_gated_plus_sleeve"].append(
                        {
                            "date": date,
                            "symbol": p["symbol"],
                            "skipped": False,
                            "ret_raw": raw,
                            "ret": scaled,
                            "gross_ret": st["gross_ret"],
                            "buy": st["buy"],
                            "sell": st["sell"],
                            "buy_date": st["buy_date"],
                            "sell_date": st["sell_date"],
                            "score": p["score"],
                            "exposure": cur_expo,
                            "win": scaled > 0,
                            "hit_3pct": scaled >= args.threshold,
                            "signal_chg": p.get("signal_chg"),
                            "open_gap": st["open_gap"],
                            "industry_l1": p.get("industry_l1"),
                            "board": p.get("board"),
                            "source": "weak_sleeve",
                        }
                    )
                    n2 += 1
                sleeve_days.append(
                    {
                        "date": date,
                        "n_picked": n2,
                        "hot": sleeve.get("hot_industries"),
                        "breadth": sleeve.get("breadth"),
                        "skip": sleeve.get("skip_reason"),
                    }
                )
                sleeve_note = f"sleeve_n={n2} expo={cur_expo}"

        print(
            f"  {date}: pool={len(strict_pool)} A0={p0}->{n0} "
            f"cur={p1c}->{n1c}(e={expo_cur}) lad={p1}->{n1}(e={expo_ladder}) "
            f"perm={p1p}->{n1p}(e={expo_perm}) A2={n2} "
            f"sev={flags.get('market_severe')} crash={flags.get('market_crash_day')} "
            f"up3={perm.get('up3_count')} sus={perm.get('n_sustained_in')} "
            f"tech_sev={flags.get('tech_severe')} {sleeve_note}",
            flush=True,
        )
        if (di + 1) % 5 == 0:
            print(f"  ... {int(time.time() - t0)}s", flush=True)

    kpis = [
        summarize(arms[k], k, args.threshold, dates, day_expo[k]) for k in arms
    ]
    out = {
        "protocol": {
            "signal": "T close as-of",
            "entry": "T+1 open if not limit-up",
            "exit": "T+2 close (A-share T+1)",
            "success": f"net_return >= {args.threshold} (after exposure scale)",
            "cost_rt": args.cost_rt,
            "exclude_signal_near_limit": True,
            "gc": "strict cross",
            "fund": "hard 5d net>0",
            "A1_cur": "legacy severe→0 + hard gate",
            "A1_ladder": "severe+crash_day→0; severe→0.25 Top1; weak/tech→0.5",
            "A1_permission": "breadth+sustained_in; nuclear only crash+rotation_dead; else floor 0.25",
            "A2_extra": "A1_permission + weak_rotation_sleeve only when nuclear expo=0",
            "sector_dual_note": "live dual gate not replayed historically (no as-of sector/concept flow)",
            "note": "VM2.5 trained_at ~2026-07-18; window may be partly in-sample",
        },
        "config": {
            "start": args.start,
            "end": args.end,
            "top_n": args.top_n,
            "sleeve_top_n": args.sleeve_top_n,
            "sleeve_exposure": SLEEVE_EXPO,
            "threshold": args.threshold,
            "prefer": args.prefer,
        },
        "kpi": kpis,
        "sleeve_days": sleeve_days,
        "trades": {k: arms[k] for k in arms},
        "recommendation": {
            "production_arm": "A1_permission",
            "baseline_compare": "A1_ladder",
            "reason": "Permission gate: don't empty when cross-section rotation still alive",
        },
    }
    path = Path(
        os.environ.get("ALPHAPILOT_GATED_OUT")
        or (ROOT / "output/v3_tradable_gated_sleeve_backtest.json")
    )
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n======== 可交易 + 降仓 结果 ========")
    for k in kpis:
        print(
            f"{k['arm']}: filled={k.get('n_filled', 0)}/{k.get('n_signals', 0)} "
            f"fill={k.get('fill_rate', 0)*100:.0f}% empty_days={k.get('empty_days')} "
            f"avg_expo={k.get('avg_exposure', 1):.2f} "
            f"win={k.get('win_rate', 0)*100:.1f}% hit3%={k.get('hit_3pct_rate', 0)*100:.1f}% "
            f"avg={k.get('avg_return', 0)*100:.2f}% day_avg={k.get('day_avg_return', 0)*100:.2f}% "
            f"maxDD={k.get('max_drawdown', 0)*100:.1f}% total={k.get('total_return', 0)*100:.1f}%"
        )
        if k.get("skip_reasons"):
            print(f"  skips: {k['skip_reasons']}")
    print("saved", path)


if __name__ == "__main__":
    main()
