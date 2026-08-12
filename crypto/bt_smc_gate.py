# -*- coding: utf-8 -*-
"""SMC trend-gate backtest on full crypto history.

Replays the trained model's prob_long/prob_short over every historical 2h bar,
then compares three arms:
  A0_nogate      : current behavior — enter when prob > threshold (long or short)
  A1_smc_dynamic : SMC Layer-1 trend gate — long only in uptrend, short only in
                   downtrend, chop blocks all (dynamic, per-symbol, per-bar)
  A2_static_labels: the WRONG approach — static per-symbol direction bans from
                   recent pnl (for comparison; proves dynamic beats static)

Protocol mirrors paper_trader: entry at bar close, exits by TP/SL/max_hold,
slippage + maker/taker fees, ATR batch sizing.
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crypto.smc_gate import direction_allowed, counter_trend_min_signal, is_counter_trend
from crypto import config as C

MODEL_DIR = ROOT / "output" / "crypto"
DATA = ROOT / "data" / "crypto"

# ─── config mirrors ───
BATCHES = 3
BATCH_SPREAD = 0.005
MAKER_FEE = C.MAKER_FEE
TAKER_FEE = C.TAKER_FEE
SLIP = C.SLIPPAGE_BY_SYMBOL
THR_L = C.PAPER.min_signal_score
THR_S = C.PAPER.min_signal_score_short
ATR_RISK = C.PAPER.atr_risk_pct
ATR_MAX_BATCH = C.PAPER.atr_max_batch_pct
INITIAL = 1000.0

# Static labels from observed pnl (the WRONG approach, for comparison only)
STATIC_BAN_LONG = set()
STATIC_BAN_SHORT = {"ADA", "AVAX", "LTC", "ETH", "BNB"}


def load_history() -> pd.DataFrame:
    p = DATA / "history.parquet"
    if not p.exists():
        raise FileNotFoundError(f"{p} missing")
    return pd.read_parquet(p)


def compute_all_features(df: pd.DataFrame) -> pd.DataFrame:
    from crypto.features import compute_features
    return compute_features(df, forward=None, threshold=None)


def load_models():
    import xgboost as xgb
    ml, ms = None, None
    mp = MODEL_DIR / "model_long.ubj"
    sp = MODEL_DIR / "model_short.ubj"
    if mp.exists():
        ml = xgb.Booster()
        ml.load_model(str(mp))
    if sp.exists():
        ms = xgb.Booster()
        ms.load_model(str(sp))
    mf = MODEL_DIR / "model_factors.json"
    if mf.exists():
        factors = json.loads(mf.read_text()).get("factors", [])
    else:
        factors = []
    return ml, ms, factors


def fill_nan(df: pd.DataFrame, factors: list[str]):
    for col in factors:
        if col in df.columns:
            df[col] = df.groupby(["symbol", "timeframe"])[col].transform(
                lambda s: s.fillna(s.median())
            )


# ─── vectorized trend precompute ───
def _ema(s, span):
    return s.ewm(span=span, adjust=False).mean()


def precompute_trends(df: pd.DataFrame) -> dict:
    """For every (symbol, 2h-bar), precompute the multi-TF trend label.

    Returns {sym: {pd.Timestamp: "up"|"down"|"chop"}} — computed ONCE
    for the whole history instead of per-bar inside the backtest loop.
    """
    out = {}
    for sym, g in df[df["timeframe"] == "2h"].groupby("symbol"):
        g = g.sort_values("timestamp").reset_index(drop=True)
        # gather the 4h / 1d as-of series per symbol
        per_tf = {}
        for tf in ("4h", "1d"):
            sub = df[(df["symbol"] == sym) & (df["timeframe"] == tf)].sort_values("timestamp")
            if len(sub) >= 30:
                sub = sub.reset_index(drop=True)
                e20 = _ema(sub["close"], 20)
                e50 = _ema(sub["close"], 50)
                per_tf[tf] = {
                    "ts": sub["timestamp"].values,
                    "close": sub["close"].values,
                    "e20": e20.values,
                    "e50": e50.values,
                }
        # 2h own series
        e20_2 = _ema(g["close"], 20)
        e50_2 = _ema(g["close"], 50)
        ts_arr = g["timestamp"].values
        close_arr = g["close"].values
        res = {}
        for i in range(30, len(g)):
            ts = g["timestamp"].iloc[i]
            # 2h score
            px = close_arr[i]
            roc20 = px / close_arr[i - 20] - 1 if i >= 20 else 0.0
            s2 = 0.0
            s2 += 1.0 if px > e20_2.iloc[i] else -1.0
            s2 += 1.0 if e20_2.iloc[i] > e50_2.iloc[i] else -1.0
            s2 += 1.0 if px > e50_2.iloc[i] else -1.0
            s2 += np.clip(roc20 * 40, -1, 1)
            # total = weighted 1d/4h + 2h
            total = s2 * 1.0
            breakdown_ok = False
            for tf, w in (("1d", 1.5), ("4h", 1.2)):
                ser = per_tf.get(tf)
                if ser is None:
                    continue
                # last index <= ts
                idx = np.searchsorted(ser["ts"], np.datetime64(ts), side="right") - 1
                if idx < 20:
                    continue
                cpx = ser["close"][idx]
                c20 = ser["e20"][idx]
                c50 = ser["e50"][idx]
                stf = 0.0
                stf += 1.0 if cpx > c20 else -1.0
                stf += 1.0 if c20 > c50 else -1.0
                stf += 1.0 if cpx > c50 else -1.0
                roc_tf = cpx / ser["close"][idx - 20] - 1 if idx >= 20 else 0.0
                stf += np.clip(roc_tf * 40, -1, 1)
                total += stf * w
                breakdown_ok = True
            if not breakdown_ok:
                continue
            if total >= 2.0:
                res[ts] = "up"
            elif total <= -2.0:
                res[ts] = "down"
            else:
                res[ts] = "chop"
        out[sym] = res
    return out


class Sim:
    def __init__(self, name: str, tp_levels=None, sl_levels=None, max_hold_bars=24,
                 ct_min: float = 0.65, chop_min: float | None = None):
        self.name = name
        self.capital = INITIAL
        self.positions = []
        self.trades = []
        self.skipped = {"chop": 0, "counter_trend": 0, "static_ban": 0}
        self.tp_levels = tp_levels or [0.01, 0.02, 0.03]
        self.sl_levels = sl_levels or [-0.015, -0.025, -0.04]
        self.max_hold_bars = max_hold_bars
        self.ct_min = ct_min          # counter-trend min signal (selective gate)
        self.chop_min = chop_min      # None=block all chop, else allow chop if sig >= this

    def equity(self, last_px):
        cap = self.capital + sum(
            p["size"] * (last_px.get(p["symbol"], p["entry"]) / p["entry"] - 1)
            * (1 if p["dir"] == "long" else -1)
            for p in self.positions
        )
        return cap

    def close_positions(self, sym, px, ts):
        still_open = []
        for p in self.positions:
            if p["symbol"] != sym:
                still_open.append(p)
                continue
            pnl_pct = (px / p["entry"] - 1) * (1 if p["dir"] == "long" else -1)
            level = min(p["level"], len(self.tp_levels) - 1)
            tp = self.tp_levels[level]
            sl = self.sl_levels[level]
            reason = None
            if pnl_pct >= tp:
                reason = "take_profit"
            elif pnl_pct <= sl:
                reason = "stop_loss"
            elif p["bars"] >= self.max_hold_bars:
                reason = "max_hold"
            if reason:
                fee = p["size"] * (MAKER_FEE if reason == "take_profit" else TAKER_FEE)
                slip = p["size"] * SLIP.get(p["symbol"], 0.001) * (1 if reason != "take_profit" else 0.5)
                net = p["size"] * pnl_pct - fee - slip
                self.capital += net
                self.trades.append({
                    "symbol": sym, "dir": p["dir"], "pnl_usdt": round(net, 4),
                    "pnl_pct": round(pnl_pct, 4), "exit": reason, "ts": str(ts),
                    "cls": p.get("cls"), "sig": p.get("sig"),
                })
            else:
                p["bars"] += 1
                still_open.append(p)
        self.positions = still_open

    def enter(self, sym, px, prob_l, prob_s, atr_pct, ts, gate_mode, trend, cls=None, sig=None):
        if len([p for p in self.positions if p["symbol"] == sym]) >= C.PAPER.max_positions * BATCHES:
            return
        best_dir, best_sig = None, 0.0
        if prob_l > THR_L:
            best_dir, best_sig = "long", prob_l
        if prob_s > THR_S and prob_s > best_sig:
            best_dir, best_sig = "short", prob_s
        if best_dir is None:
            return

        if gate_mode == "smc_dynamic":
            if not direction_allowed(best_dir, trend):
                self.skipped["counter_trend" if trend != "chop" else "chop"] += 1
                return
        elif gate_mode == "selective":
            # SMC selective gate: with-trend keeps original threshold,
            # counter-trend requires a stronger signal.
            if not direction_allowed(best_dir, trend):
                if trend == "chop":
                    # default: block all chop; optional: allow strong signals in chop
                    if self.chop_min is None or best_sig < self.chop_min:
                        self.skipped["chop"] += 1
                        return
                elif best_sig < self.ct_min:
                    self.skipped["counter_trend"] += 1
                    return
        elif gate_mode == "static":
            sym_s = str(sym).replace("/USDT:USDT", "")
            banned = STATIC_BAN_LONG if best_dir == "long" else STATIC_BAN_SHORT
            if sym_s in banned:
                self.skipped["static_ban"] += 1
                return

        if atr_pct and atr_pct > 1e-6:
            raw = self.capital * ATR_RISK / (atr_pct * BATCHES)
            size = min(raw, self.capital * ATR_MAX_BATCH)
        else:
            size = self.capital * C.PAPER.per_trade_risk / BATCHES
        fee = size * MAKER_FEE
        self.capital -= fee
        for lvl in range(BATCHES):
            px_lvl = px * (1 - lvl * BATCH_SPREAD) if best_dir == "long" else px * (1 + lvl * BATCH_SPREAD)
            self.positions.append({
                "symbol": sym, "dir": best_dir, "entry": px_lvl,
                "size": size / BATCHES, "bars": 0, "level": lvl,
                "cls": cls, "sig": sig if sig is not None else best_sig,
            })


def run_backtest(df, models, factors, gate_mode, trends, start="2026-01-01", end=None,
                 tp_levels=None, sl_levels=None, max_hold_bars=24,
                 ct_min: float = 0.65, chop_min: float | None = None):
    ml, ms, _ = models
    sim = Sim(gate_mode, tp_levels=tp_levels, sl_levels=sl_levels, max_hold_bars=max_hold_bars,
              ct_min=ct_min, chop_min=chop_min)
    last_px = {}

    df2 = df[df["timeframe"] == "2h"].copy().sort_values(["symbol", "timestamp"])
    symbols = sorted(df2["symbol"].unique())
    all_bars = df2.groupby("symbol")
    ts_list = sorted(df2["timestamp"].unique())
    ts_list = [t for t in ts_list if str(t)[:10] >= start]
    if end is not None:
        ts_list = [t for t in ts_list if str(t)[:10] <= end]

    import xgboost as xgb
    t0 = time.time()
    for bi, ts in enumerate(ts_list):
        rows, idxs = [], []
        for sym in symbols:
            sub = all_bars.get_group(sym)
            sub = sub[sub["timestamp"] == ts]
            if sub.empty:
                continue
            rows.append(sub.iloc[0])
            idxs.append(sym)
        if not rows:
            continue
        latest = pd.DataFrame(rows)
        need = [c for c in factors if c in latest.columns]
        dmat = xgb.DMatrix(latest[need].values)
        pl = ml.predict(dmat)
        ps = ms.predict(dmat) if ms is not None else np.zeros(len(rows))

        for i, sym in enumerate(idxs):
            px = float(latest.iloc[i]["close"])
            last_px[sym] = px
            sim.close_positions(sym, px, ts)
        for i, sym in enumerate(idxs):
            px = float(latest.iloc[i]["close"])
            atr = float(latest.iloc[i].get("atr_pct", 0)) if "atr_pct" in latest.columns else None
            trend = "chop"
            if gate_mode in ("smc_dynamic", "selective"):
                trend = trends.get(sym, {}).get(ts, "chop")
            sim.enter(sym, px, float(pl[i]), float(ps[i]), atr, ts, gate_mode, trend)

        if (bi + 1) % 500 == 0:
            print(f"  [{gate_mode}] bar {bi+1}/{len(ts_list)} eq={sim.equity(last_px):.0f} "
                  f"{time.time()-t0:.0f}s", flush=True)

    eq = sim.equity(last_px)
    wins = sum(1 for t in sim.trades if t["pnl_usdt"] > 0)
    n = len(sim.trades)
    # by-direction stats
    longs = [t for t in sim.trades if t["dir"] == "long"]
    shorts = [t for t in sim.trades if t["dir"] == "short"]
    def _wr(ts):
        return 100 * sum(1 for t in ts if t["pnl_usdt"] > 0) / len(ts) if ts else 0
    def _pnl(ts):
        return sum(t["pnl_usdt"] for t in ts)
    # by-exit stats
    by_exit = {}
    for t in sim.trades:
        by_exit.setdefault(t["exit"], []).append(t)
    exit_stats = {k: {"n": len(v), "wr": round(_wr(v), 1), "pnl": round(_pnl(v), 2)} for k, v in by_exit.items()}
    return {
        "arm": gate_mode,
        "trades": n,
        "win_rate": 100 * wins / n if n else 0,
        "total_return_pct": (eq / INITIAL - 1) * 100,
        "final_equity": round(eq, 2),
        "skipped": sim.skipped,
        "avg_pnl": round(sum(t["pnl_usdt"] for t in sim.trades) / n, 4) if n else 0,
        "long": {"n": len(longs), "wr": round(_wr(longs), 1), "pnl": round(_pnl(longs), 2)},
        "short": {"n": len(shorts), "wr": round(_wr(shorts), 1), "pnl": round(_pnl(shorts), 2)},
        "by_exit": exit_stats,
    }


def main():
    print("=== SMC trend-gate backtest (vectorized trends) ===", flush=True)
    df = load_history()
    print(f"history rows: {len(df)}, symbols: {df['symbol'].nunique()}, "
          f"tfs: {df['timeframe'].unique()}, range: {df['timestamp'].min()} ~ {df['timestamp'].max()}", flush=True)

    print("computing features...", flush=True)
    df = compute_all_features(df)
    models = load_models()
    ml, ms, factors = models
    if ml is None:
        print("FATAL: no long model")
        return
    print(f"models: long={ml is not None} short={ms is not None} factors={len(factors)}", flush=True)
    fill_nan(df, factors)
    df = df.dropna(subset=[f for f in factors if f in df.columns])

    print("precomputing multi-TF trends (once)...", flush=True)
    trends = precompute_trends(df)
    n_up = sum(1 for s in trends for v in trends[s].values() if v == "up")
    n_dn = sum(1 for s in trends for v in trends[s].values() if v == "down")
    n_ch = sum(1 for s in trends for v in trends[s].values() if v == "chop")
    print(f"trend labels: up={n_up} down={n_dn} chop={n_ch}", flush=True)

    results = []
    for mode in ["nogate", "smc_dynamic", "selective", "static"]:
        r = run_backtest(df, models, factors, mode, trends)
        print(f"  RESULT {r['arm']}: trades={r['trades']} win={r['win_rate']:.1f}% "
              f"ret={r['total_return_pct']:+.2f}% skipped={r['skipped']}", flush=True)
        results.append(r)

    out = ROOT / "output" / "crypto" / "smc_gate_bt.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved", out)


if __name__ == "__main__":
    main()
