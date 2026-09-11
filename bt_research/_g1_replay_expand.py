#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
G1 × Track A 扩样扩窗 replay（验证 regime 依赖）

扩样：归档 union(top10_ungated ∪ top10_gated) × 全部可用日（07-26 → 09-11）
口径（生产忠实）：
  label: gap_pct = (open(D)/close(D-1)-1)*100（±0.3% 分高/低/平开）
         走向 = sign(t0), t0 = close(D)/open(D)-1   （与 WB prod_results 字段逐项对齐）
  entry: bar(09:35).close on D
  exit : Track A v2.45(sim) / v2.38(live) 全套（复用 _g1_trackA_replay.full）
评价：逐笔 t + 按天聚类 t + 同日配对 t；并按 regime 分段。
"""
import json, math, os, sys
import pandas as pd
import numpy as np

sys.path.insert(0, "/home/ubuntu/alphapilot")
import _g1_trackA_replay as R

ARCH = "/home/ubuntu/alphapilot/output/daily_picks_archive"
QSCORES = "/home/ubuntu/alphapilot/output/qmt_scores"
GAP_TOL = 0.3   # percent


def load_picks():
    days = sorted(d for d in os.listdir(ARCH)
                  if os.path.isdir(os.path.join(ARCH, d)))
    out = []
    for d in days:
        syms = {}
        for fn in ("top10_ungated.json", "top10_gated.json"):
            p = os.path.join(ARCH, d, fn)
            if not os.path.exists(p):
                continue
            try:
                j = json.load(open(p))
            except Exception:
                continue
            for pk in (j.get("picks") or []):
                s = str(pk.get("symbol") or "").zfill(6)
                if s:
                    syms.setdefault(s, pk.get("name", ""))
        for s, nm in syms.items():
            out.append((d, s, nm))
    return out


def weak_by_day():
    r = {}
    for f in os.listdir(QSCORES):
        if not f.endswith(".candidates.json"):
            continue
        raw = f.split(".")[0]
        day = raw if "-" in raw else f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
        try:
            j = json.load(open(os.path.join(QSCORES, f)))
            env = j.get("market_env") or {}
            if "weak_regime" in env:
                r[day] = bool(env.get("weak_regime"))
        except Exception:
            pass
    return r


def label(code, day):
    g = R._G.get(code)
    if g is None:
        return None
    ds = list(g["date"])
    if day not in ds:
        return None
    i = ds.index(day)
    if i < 1 or i + 1 >= len(g):
        return None
    pc = float(g["close"].iloc[i - 1]); o0 = float(g["open"].iloc[i])
    c0 = float(g["close"].iloc[i]); c1 = float(g["close"].iloc[i + 1])
    if pc <= 0 or o0 <= 0:
        return None
    gap_pct = (o0 / pc - 1) * 100
    gb = "高开" if gap_pct > GAP_TOL else ("低开" if gap_pct < -GAP_TOL else "平开")
    t0 = c0 / o0 - 1
    dr = "走高" if t0 > 0 else ("走低" if t0 < 0 else "平盘")
    return dict(gap_pct=gap_pct, cat=gb + dr, t0=t0, t1=c1 / o0 - 1)


def seg_of(day, weak):
    if day <= "2026-08-19":
        return "强势段(<=08-19)"
    if day <= "2026-09-08":
        return "弱势段(08-20~09-08)"
    return "最新段(09-09~)"


def main():
    R._load()
    picks = load_picks()
    weak = weak_by_day()
    rows = []
    for day, code, nm in picks:
        lb = label(code, day)
        if lb is None:
            continue
        m = R.load_5m(code)
        if m is None:
            continue
        d0 = m[m["ds"] == day]
        eb = d0[d0["hm"] == "09:35"]
        if not len(eb):
            continue
        ob = float(eb["close"].iloc[0])
        # 需要 D+1 的 5m
        nds = sorted(set(m["ds"]))
        if day not in nds or nds.index(day) + 1 >= len(nds):
            continue
        try:
            fs = R.full(ob, code, day, m, sim=True)
            fl = R.full(ob, code, day, m, sim=False)
        except Exception:
            continue
        if fs is None:
            continue
        rows.append(dict(date=day, code=code, name=nm, cat=lb["cat"],
                         gap_pct=lb["gap_pct"], t1=lb["t1"],
                         full_sim=fs, full_live=fl,
                         seg=seg_of(day, weak), weak=weak.get(day)))
    df = pd.DataFrame(rows)
    df.to_parquet("/tmp/g1_expand.parquet", index=False)
    print("n =", len(df), "| days =", df["date"].nunique())
    print("cats:", df["cat"].value_counts().to_dict())

    def report(sub, col):
        if len(sub) < 5:
            print(f"    (n={len(sub)} 太少)"); return
        u = sub[sub["cat"].str.endswith("走高")]
        dn = sub[sub["cat"].str.endswith("走低")]
        def tt(s):
            if len(s) < 2:
                return float('nan'), float('nan'), 0
            g = s.groupby("date")[col].mean().values
            t = g.mean() / (g.std(ddof=1) / np.sqrt(len(g))) if len(g) > 1 else float('nan')
            return g.mean(), t, len(g)
        m1, t1, _ = tt(u); m2, t2, _ = tt(dn)
        pair = (u.groupby("date")[col].mean() - dn.groupby("date")[col].mean()).dropna().values
        tp = pair.mean() / (pair.std(ddof=1) / np.sqrt(len(pair))) if len(pair) > 1 else float('nan')
        print(f"    {col:10s} n={len(sub):4d} 全体={100*sub[col].mean():+6.2f}% 胜={100*(sub[col]>0).mean():5.1f}% | "
              f"走高 n={len(u):3d} {100*m1:+.2f}% t={t1:5.2f} | 走低 n={len(dn):3d} {100*m2:+.2f}% t={t2:6.2f} | "
              f"配对 {100*pair.mean():+.2f}% t={tp:.2f}")

    print("\n=== 全窗口 ===")
    for c in ["full_sim", "full_live"]:
        report(df, c)
    print("\n=== 分段（验证 regime 依赖）===")
    for seg in ["强势段(<=08-19)", "弱势段(08-20~09-08)", "最新段(09-09~)"]:
        sub = df[df["seg"] == seg]
        print(f"  [{seg}] n={len(sub)} days={sub['date'].nunique()}")
        for c in ["full_sim", "full_live"]:
            report(sub, c)
    print("\n=== weak_regime 分层（candidates.json 可得日）===")
    dd = df.dropna(subset=["weak"])
    print("  weak 覆盖: n=%d days=%d | True=%d False=%d" % (
        len(dd), dd["date"].nunique(), int((dd["weak"] == True).sum()), int((dd["weak"] == False).sum())))
    for w in [True, False]:
        sub = df[df["weak"] == w]
        print(f"  [weak={w}] n={len(sub)} days={sub['date'].nunique()}")
        for c in ["full_sim"]:
            report(sub, c)
    print("\n  day list:", sorted(df["date"].unique())[-6:])
    print("\n=== 对照：t1 持到 D+1（原研究口径）===")
    report(df, "t1")


if __name__ == "__main__":
    main()
