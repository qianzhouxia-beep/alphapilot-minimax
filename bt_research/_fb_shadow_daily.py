#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""首板回调 setup 轻量纸面观察池（read-only）

老板 2026-09-11 决策：首板方向 hold，落地「轻量纸面观察池」——
setup 当**额外截面**记录，**不加仓 / 不排序 / 不改生产管线**，只积累证据。

做什么
  1. 每日扫全市场日K，按 bt_firstboard_lift.py 的严格定义识别 setup 票：
       is_lu  = close == round_half_up(prev_close*(1+thr), 0.01) （thr: 30x/68x=20%，其余=10%）
       首板    = 当日涨停 且 前 FB_LOOKBACK(=20) 交易日无涨停收盘
       setup   = 首板出现在最近 1..5 日内 且 今日不涨停
  2. UPSERT 到 output/fb_shadow/fb_shadow.jsonl（key = date|symbol，幂等）
  3. 回填 forward 指标（数据到位后自动补）：
       t1_lu        T+1 收盘涨停（第一步主 label）
       t1_ret_open  买 T+1 开盘 → D+1 收盘
       t1_ret_0935  买 T+1 的 09:35 bar 收盘(≈09:36) → D+1 收盘（5m 可得时）
       abs3_trail   生产出场近似（+3% 锁盈 / −4% 止损，5m，D+1..D+3）
  4. 打印累计统计

只读生产文件；唯一写入：output/fb_shadow/
用法：
  python3 fb_shadow_daily.py                # 最近交易日
  python3 fb_shadow_daily.py 2026-09-10     # 指定日
  python3 fb_shadow_daily.py --backfill 10  # 回填最近 10 个交易日
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd

ROOT = "/home/ubuntu/alphapilot"
KALL = os.path.join(ROOT, "data/kline_cache/kline_all.parquet")
K5 = os.path.join(ROOT, "data/kline5m")
OUTD = os.path.join(ROOT, "output/fb_shadow")
LEDGER = os.path.join(OUTD, "fb_shadow.jsonl")

FB_LOOKBACK = 20
FB_MAX_AGE = 5
EPS = 5e-3
HIST_KEEP = 45          # 判定时每票最多回看 N 根日K


def thr_of(sym: str) -> float:
    """涨跌停幅度：创业板(30x)/科创(68x)=20%，其余=10%。"""
    return 0.20 if sym[:2] in ("30", "68") else 0.10


def round_limit(prev, thr):
    x = np.asarray(prev, dtype=float) * (1.0 + thr) * 100.0
    return np.where(np.isfinite(x), np.floor(x + 0.5 + 1e-9) / 100.0, np.nan)


def load_index():
    """一次性按 symbol 切成 numpy 数组，避免重复全表扫描。"""
    k = pd.read_parquet(KALL, columns=["date", "open", "high", "low", "close", "volume", "symbol"])
    k["symbol"] = k["symbol"].astype(str).str.zfill(6)
    k["date"] = k["date"].astype(str).str[:10]
    k = k.sort_values(["symbol", "date"])
    S = {}
    for sym, g in k.groupby("symbol", sort=False):
        S[sym] = dict(
            dates=g["date"].to_numpy(),
            open=g["open"].to_numpy(float),
            high=g["high"].to_numpy(float),
            low=g["low"].to_numpy(float),
            close=g["close"].to_numpy(float),
            thr=thr_of(sym),
        )
    all_days = sorted(k["date"].unique())
    return S, all_days


def is_lu_arr(cl: np.ndarray, thr: float) -> np.ndarray:
    prev = np.concatenate([[np.nan], cl[:-1]])
    return (np.abs(cl - round_limit(prev, thr)) < EPS) & np.isfinite(prev)


def setup_for_date(S: dict, D: str) -> list[dict]:
    rows = []
    for sym, d in S.items():
        dates_all = d["dates"]
        # 定位 D 在该票序列中的位置（支持历史回填，不只最后一天）
        pos = int(np.searchsorted(dates_all, D, side="right")) - 1
        if pos < 5 or pos >= len(dates_all) or dates_all[pos] != D:
            continue
        lo = max(0, pos - HIST_KEEP + 1)
        dates = dates_all[lo:pos + 1]
        cl = d["close"][lo:pos + 1]
        if len(dates) < 6:
            continue
        lu = is_lu_arr(cl, d["thr"])
        n = len(dates)
        pref = np.concatenate([[0], np.cumsum(lu.astype(np.int64))])
        i = np.arange(n)
        a = np.maximum(0, i - FB_LOOKBACK)
        fb = lu & ~((pref[i] - pref[a]) > 0)
        fbi = np.nonzero(fb)[0]
        if len(fbi) == 0:
            continue
        pos = np.searchsorted(fbi, i, side="left") - 1
        has = pos >= 0
        u = np.where(has, fbi[np.clip(pos, 0, None)], -1)
        ds = np.where(has, i - u, -1)
        j = n - 1
        if not (has[j] and 1 <= ds[j] <= FB_MAX_AGE and not lu[j]):
            continue
        fi = int(u[j])
        if cl[fi] <= 0:
            continue
        rows.append(dict(
            date=D, symbol=sym,
            days_since_fb=int(ds[j]),
            pullback=round(float(cl[j] / cl[fi] - 1.0), 6),
            fb_date=str(dates[fi]),
            close=round(float(cl[j]), 4),
        ))
    return rows


_K5CACHE: dict = {}


def bars_5m(sym: str, days: list[str]):
    if sym not in _K5CACHE:
        p = os.path.join(K5, sym + ".parquet")
        if not os.path.exists(p) or os.path.getsize(p) == 0:
            _K5CACHE[sym] = None
        else:
            try:
                m = pd.read_parquet(p, columns=["datetime", "high", "low", "close"])
                m["ds"] = m["datetime"].astype(str).str[:10]
                m["hm"] = m["datetime"].astype(str).str[11:16]
                m = m.sort_values("datetime")
                _K5CACHE[sym] = m
            except Exception:
                _K5CACHE[sym] = None
    m = _K5CACHE[sym]
    if m is None:
        return {}
    sub = m[m["ds"].isin(days)]
    out = {}
    for ds, g in sub.groupby("ds"):
        out[ds] = list(zip(g["hm"].tolist(), g["high"].to_numpy(float),
                           g["low"].to_numpy(float), g["close"].to_numpy(float)))
    return out


def abs3_trail(entry: float, bars: list):
    if not bars or entry <= 0:
        return None
    armed = False
    for _hm, h, l, c in bars:
        if l <= entry * 0.96:
            return -0.04
        if h >= entry * 1.03:
            armed = True
        if armed and l <= entry * 1.03:
            return 0.03
    return bars[-1][2] / entry - 1.0


def forward(S: dict, rec: dict) -> dict:
    sym, D = rec["symbol"], rec["date"]
    d = S.get(sym)
    if d is None:
        return rec
    ds = d["dates"]
    idx = np.nonzero(ds == D)[0]
    if not len(idx):
        return rec
    i = int(idx[0])
    if i + 1 >= len(ds):
        return rec
    o1, c1 = float(d["open"][i + 1]), float(d["close"][i + 1])
    d1 = str(ds[i + 1])
    prev1 = float(d["close"][i])
    lim1 = round_limit(np.array([prev1]), d["thr"])[0]
    rec["t1_date"] = d1
    rec["t1_open"] = round(o1, 4)
    rec["t1_close"] = round(c1, 4)
    rec["t1_lu"] = bool(np.isfinite(lim1) and abs(c1 - lim1) < EPS)
    if o1 > 0:
        rec["t1_ret_open"] = round(c1 / o1 - 1.0, 6)
    bm = bars_5m(sym, [d1])
    if bm.get(d1):
        bar935 = [b for b in bm[d1] if b[0] == "09:35"]
        if bar935:
            e935 = bar935[0][3]
            rec["t1_entry_0935"] = round(e935, 4)
            if e935 > 0:
                rec["t1_ret_0935"] = round(c1 / e935 - 1.0, 6)
        if i + 4 <= len(ds):
            days3 = [str(ds[i + 1 + j]) for j in range(3)]
            b3 = bars_5m(sym, days3)
            allb = []
            for dd in days3:
                allb += b3.get(dd, [])
            r = abs3_trail(rec.get("t1_entry_0935", o1), allb)
            if r is not None:
                rec["abs3_trail"] = round(r, 6)
    return rec


def load_ledger() -> dict:
    d = {}
    if os.path.exists(LEDGER):
        for ln in open(LEDGER, encoding="utf-8"):
            ln = ln.strip()
            if not ln:
                continue
            try:
                r = json.loads(ln)
                d[r["date"] + "|" + r["symbol"]] = r
            except Exception:
                pass
    return d


def save_ledger(led: dict) -> None:
    os.makedirs(OUTD, exist_ok=True)
    tmp = LEDGER + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for key in sorted(led):
            f.write(json.dumps(led[key], ensure_ascii=False) + "\n")
    os.replace(tmp, LEDGER)


def summarize(led: dict) -> None:
    rows = list(led.values())
    if not rows:
        print("[fb] empty", flush=True)
        return
    df = pd.DataFrame(rows)
    print(f"[fb] ledger n={len(df)} days={df['date'].nunique()} "
          f"range={df['date'].min()}..{df['date'].max()}", flush=True)
    for col, nm in (("t1_lu", "T+1收盘涨停率"), ("t1_ret_open", "买T+1开盘→D+1收"),
                    ("t1_ret_0935", "买T+1 09:35→D+1收"), ("abs3_trail", "abs3_trail出场")):
        if col not in df:
            continue
        s = pd.to_numeric(df[col], errors="coerce").dropna()
        if not len(s):
            continue
        if col == "t1_lu":
            print(f"    {nm}: n={len(s)} rate={100*s.mean():.2f}%", flush=True)
        else:
            print(f"    {nm}: n={len(s)} mean={100*s.mean():+.2f}% 胜={100*(s>0).mean():.1f}%", flush=True)
    if "days_since_fb" in df and "t1_ret_open" in df:
        s = pd.to_numeric(df["t1_ret_open"], errors="coerce")
        g = df.assign(_r=s).dropna(subset=["_r"]).groupby("days_since_fb")["_r"]
        print("    by days_since_fb:", {int(k): f"{100*v.mean():+.2f}%(n{len(v)})"
                                        for k, v in g}, flush=True)


def main():
    args = sys.argv[1:]
    S, all_days = load_index()
    led = load_ledger()
    today = datetime.now().strftime("%Y-%m-%d")

    if args and args[0] == "--backfill":
        n = int(args[1]) if len(args) > 1 else 10
        days = [d for d in all_days if d <= today][-n:]
        for d in days:
            c = 0
            for rec in setup_for_date(S, d):
                key = rec["date"] + "|" + rec["symbol"]
                if key not in led:
                    c += 1
                led[key] = rec
            print(f"[fb] {d} new={c}", flush=True)
    else:
        D = args[0] if args else (all_days[-1] if all_days[-1] <= today else all_days[-2])
        c = 0
        for rec in setup_for_date(S, D):
            key = rec["date"] + "|" + rec["symbol"]
            if key not in led:
                c += 1
            led[key] = rec
        print(f"[fb] {D} new={c}", flush=True)

    # forward 回填一次（幂等）
    for key in list(led.keys()):
        led[key] = forward(S, led[key])

    save_ledger(led)
    summarize(led)
    print(f"[fb] wrote {LEDGER}", flush=True)


if __name__ == "__main__":
    main()
