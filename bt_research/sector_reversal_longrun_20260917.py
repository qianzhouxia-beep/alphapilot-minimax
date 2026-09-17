#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""板块「跌了→次日反弹」的长期稳定性检验（2026-09-17 Cursor）

目的：9 月资金流面板只有 ~30 日，不足以定论。资金流已被证明对价格无增量信息
（见 sector_rotation_reversal_20260917.py 第 10 节），因此把**可执行的那部分**
（板块当日涨跌 → 未来超额）放到 2025-01-02 ~ 2026-09-17 全部 416 个交易日上检验，
看它是稳定效应还是 9 月小样本巧合。

口径：
  · 行业 = 申万二级（stock_industry_map），成分股等权，>=5 只成分
  · 信号日 D 收盘定序；入场 = D+1 开盘
  · T0 = close(D+1)/open(D+1)-1；T1 = close(D+2)/open(D+1)-1
  · 超额 = 行业等权 − 全市场等权（同日同口径）
  · 统计 = 逐日横截面多空差，再对日序列取 t（规避同日截面相关）
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

D = Path(__file__).resolve().parent / "_sector_rotation" / "data"
OUT = Path(__file__).resolve().parent / "_sector_rotation"

TECH_CORE = {"半导体", "消费电子", "元件", "光学光电子", "软件开发",
             "IT服务Ⅱ", "通信设备", "通信服务", "计算机设备"}
TECH_BROAD = TECH_CORE | {"电池", "光伏设备", "电网设备", "自动化设备",
                          "通用设备", "专用设备", "航空装备Ⅱ"}


def build():
    k = pd.read_parquet(D / "kline_long.parquet")
    imap = json.loads((D / "industry_map.json").read_text(encoding="utf-8"))
    k["code"] = k["symbol"].astype(str).str.split(".").str[0].str.zfill(6)
    c2l = {str(c).split(".")[0].zfill(6): (v or {}).get("industry_l2")
           for c, v in imap.items()}
    k["l2"] = k["code"].map(c2l)
    k = k.dropna(subset=["l2", "open", "close"]).sort_values(["code", "date"])

    g = k.groupby("code", sort=False)
    k["ret_D"] = k["close"] / g["close"].shift(1) - 1.0
    k["ret_T0"] = g["close"].shift(-1) / g["open"].shift(-1) - 1.0
    k["ret_T1"] = g["close"].shift(-2) / g["open"].shift(-1) - 1.0
    k = k[np.isfinite(k["ret_D"])]

    mkt = k.groupby("date")[["ret_T0", "ret_T1"]].mean().add_prefix("mkt_")
    sec = k.groupby(["date", "l2"])[["ret_D", "ret_T0", "ret_T1"]].mean()
    sec = sec.join(k.groupby(["date", "l2"]).size().rename("n"), how="left")
    sec = sec.join(mkt, on="date")
    sec["ex_T0"] = sec["ret_T0"] - sec["mkt_ret_T0"]
    sec["ex_T1"] = sec["ret_T1"] - sec["mkt_ret_T1"]
    sec = sec[sec["n"] >= 5].reset_index()
    sec["ym"] = sec["date"].str[:7]
    return sec


def ls_by_day(d, col="ex_T1", q=3):
    """逐日：当日跌组 − 当日涨组的 (col) 差。"""
    rows = []
    for dt, sub in d.dropna(subset=["ret_D", col]).groupby("date"):
        if len(sub) < 3 * q:
            continue
        sub = sub.copy()
        sub["tile"] = pd.qcut(sub["ret_D"].rank(method="first"), q,
                              labels=range(q))
        lo = sub[sub.tile == 0][col].mean()
        hi = sub[sub.tile == q - 1][col].mean()
        rows.append({"date": dt, "d": lo - hi, "n": len(sub)})
    return pd.DataFrame(rows)


def stat(s):
    if isinstance(s, pd.DataFrame):
        s = s["d"] if "d" in s.columns else s.iloc[:, 0]
    s = pd.Series(s).dropna()
    if len(s) < 5:
        return None
    m, sd = s.mean(), s.std(ddof=1)
    return {"n_days": len(s), "mean": m,
            "t": m / (sd / np.sqrt(len(s))) if sd else np.nan,
            "hit": float((s > 0).mean())}


def main():
    sec = build()
    L = []
    P = L.append
    P("=" * 78)
    P("板块反转效应长期稳定性检验（2025-01-02 ~ 2026-09-17）  Cursor")
    P(f"面板: {sec.date.nunique()} 交易日 × {sec.l2.nunique()} 个申万二级行业 "
      f"= {len(sec)} 观测")
    P("=" * 78)

    P("\n【1】全样本：当日跌组 − 当日涨组（等权超额，D+1 开盘入场）")
    for col in ("ex_T0", "ex_T1"):
        for q in (3, 5):
            r = stat(ls_by_day(sec, col, q))
            if r:
                P(f"  {col}  {q}分组: Δ={r['mean']*100:+.3f}%  t={r['t']:+.2f}  "
                  f"胜日 {r['hit']:.0%}  n_days={r['n_days']}")

    P("\n【2】分月稳定性（T1，3 分组）")
    dd = ls_by_day(sec, "ex_T1", 3)
    dd["ym"] = dd["date"].str[:7]
    for ym, g in dd.groupby("ym"):
        r = stat(g["d"])
        if r:
            bar = "█" * min(20, int(abs(r["mean"]) * 100 * 8))
            P(f"  {ym}: Δ={r['mean']*100:+.3f}% t={r['t']:+.2f} "
              f"胜日{r['hit']:.0%} n={r['n_days']:>2}  {bar}")

    P("\n【3】科技行业子集（T1，3 分组）")
    for lab, s in (("科技·窄", sec[sec.l2.isin(TECH_CORE)]),
                   ("科技·宽", sec[sec.l2.isin(TECH_BROAD)])):
        for col in ("ex_T0", "ex_T1"):
            r = stat(ls_by_day(s, col, 3))
            if r:
                P(f"  {lab} {col}: Δ={r['mean']*100:+.3f}% t={r['t']:+.2f} "
                  f"胜日 {r['hit']:.0%} n_days={r['n_days']}")

    P("\n【4】幅度依赖：当日跌幅越大，反弹越强？（T1）")
    for thr in (0.0, -0.01, -0.02, -0.03, -0.05):
        g = sec[sec.ret_D < thr]
        if len(g) < 50:
            P(f"  当日跌>={-thr*100:.0f}%: n={len(g)} 不足")
            continue
        x = g["ex_T1"].dropna()
        t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
        P(f"  当日跌幅 > {abs(thr)*100:.0f}%: n={len(x)} "
          f"T1超额={x.mean()*100:+.3f}% t={t:+.2f}")

    P("\n【5】2026 年 9 月切片 vs 其余时段（对照老板关切）")
    for lab, mask in (("2026-09", sec.date >= "2026-09-01"),
                      ("2026-08", (sec.date >= "2026-08-01") & (sec.date < "2026-09-01")),
                      ("2026-01~07", (sec.date >= "2026-01-01") & (sec.date < "2026-08-01")),
                      ("2025 全年", sec.date < "2026-01-01")):
        s = sec[mask]
        if not len(s):
            continue
        r0 = stat(ls_by_day(s, "ex_T0", 3))
        r1 = stat(ls_by_day(s, "ex_T1", 3))
        if r0 and r1:
            P(f"  {lab}: T0 Δ={r0['mean']*100:+.3f}% t={r0['t']:+.2f} | "
              f"T1 Δ={r1['mean']*100:+.3f}% t={r1['t']:+.2f} "
              f"(n_days={r1['n_days']})")

    txt = "\n".join(L)
    print(txt)
    (OUT / "longrun_report.txt").write_text(txt, encoding="utf-8")
    dd.to_csv(OUT / "longrun_daily_ls.csv", index=False)
    print(f"\n[written] {OUT/'longrun_report.txt'}")


if __name__ == "__main__":
    main()
