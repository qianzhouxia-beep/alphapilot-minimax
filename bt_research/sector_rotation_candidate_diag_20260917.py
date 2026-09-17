#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""诊断：模型的 Top10 候选是不是买在「当日已经走强」的板块/个股上？

动机：老板观察「今天买了第二天就跌」。板块层研究已证：快速轮动阶段板块存在
显著短期反转（当日跌 → 次日反弹）。若模型的候选系统性偏向「当日已涨」的板块，
则它结构性地站在反转的错误一侧——这才是「次日就跌」的机制，而非运气。

数据：output/qmt_scores/{date}.candidates.json（Top10，score/rank 序）
口径：入场 = D+1 开盘（贴近生产 09:36）
      T0 = close(D+1)/open(D+1)-1；T1 = close(D+2)/open(D+1)-1
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

D = Path(__file__).resolve().parent / "_sector_rotation" / "data"
CAND = D / "sr_cand"
OUT = Path(__file__).resolve().parent / "_sector_rotation"


def main():
    k = pd.read_parquet(D / "kline_long.parquet")
    imap = json.loads((D / "industry_map.json").read_text(encoding="utf-8"))
    k["code"] = k["symbol"].astype(str).str.split(".").str[0].str.zfill(6)
    c2l = {str(c).split(".")[0].zfill(6): (v or {}).get("industry_l2")
           for c, v in imap.items()}
    k["l2"] = k["code"].map(c2l)
    k = k.sort_values(["code", "date"])
    g = k.groupby("code", sort=False)
    k["ret_D"] = k["close"] / g["close"].shift(1) - 1.0
    k["ret_T0"] = g["close"].shift(-1) / g["open"].shift(-1) - 1.0
    k["ret_T1"] = g["close"].shift(-2) / g["open"].shift(-1) - 1.0
    km = k.set_index(["code", "date"])

    # 行业当日收益（等权），用于判断候选所处板块当天是涨是跌
    sec_ret = (k.dropna(subset=["l2", "ret_D"]).groupby(["date", "l2"])["ret_D"]
               .mean().rename("sec_ret_D"))
    mkt = k.groupby("date")[["ret_T0", "ret_T1"]].mean().add_prefix("mkt_")

    rows = []
    for f in sorted(CAND.glob("*.candidates.json")):
        d8 = f.name.split(".")[0]
        iso = f"{d8[:4]}-{d8[4:6]}-{d8[6:]}"
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for r in (doc.get("candidates") or []):
            code = str(r.get("symbol") or "").split(".")[0].zfill(6)
            try:
                kk = km.loc[(code, iso)]
            except KeyError:
                continue
            L2 = str(r.get("industry_l2") or c2l.get(code) or "")
            rows.append({
                "date": iso, "code": code, "rank": r.get("rank"),
                "l2": L2,
                "stock_ret_D": kk["ret_D"],
                "sec_ret_D": sec_ret.get((iso, L2), np.nan),
                "ret_T0": kk["ret_T0"], "ret_T1": kk["ret_T1"],
            })
    df = pd.DataFrame(rows)
    df["ex_T0"] = df["ret_T0"] - df["date"].map(mkt["mkt_ret_T0"])
    df["ex_T1"] = df["ret_T1"] - df["date"].map(mkt["mkt_ret_T1"])

    L = []
    P = L.append
    P("=" * 78)
    P("诊断：模型 Top10 候选 是否买在「当日已走强」的板块/个股上")
    P(f"样本: {df.date.nunique()} 日 × ~10 = {len(df)} 笔（{df.date.min()} ~ {df.date.max()}）")
    P("=" * 78)

    P("\n【1】候选所处板块在 D 日（选股日）的表现分布")
    sd = df.dropna(subset=["sec_ret_D"])
    P(f"  板块当日收益均值 {sd.sec_ret_D.mean()*100:+.3f}%  "
      f"中位 {sd.sec_ret_D.median()*100:+.3f}%")
    P(f"  所处板块当日【上涨】占比 {(sd.sec_ret_D>0).mean():.0%} "
      f"（全市场基准 ≈ 50%）")
    P(f"  个股自身当日收益均值 {df.stock_ret_D.mean()*100:+.3f}%  "
      f"【上涨】占比 {(df.stock_ret_D>0).mean():.0%}")

    P("\n【2】次日表现（绝对 / 相对全市场等权超额）")
    for c in ("ret_T0", "ex_T0", "ret_T1", "ex_T1"):
        x = df[c].dropna()
        t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
        P(f"  {c}: mean={x.mean()*100:+.3f}%  med={x.median()*100:+.3f}%  t={t:+.2f}  n={len(x)}")

    P("\n【3】关键：次日超额 与「板块当日涨跌」的关系（反转检验）")
    for lab, col in (("板块当日收益", "sec_ret_D"), ("个股当日收益", "stock_ret_D")):
        s = df.dropna(subset=[col, "ex_T1"])
        if len(s) < 20:
            continue
        ic = s[col].corr(s["ex_T1"], method="spearman")
        # 逐日配对：当日涨 vs 当日跌
        per = []
        for _, sub in s.groupby("date"):
            sub = sub.copy()
            sub["pos"] = sub[col] > 0
            if sub["pos"].nunique() < 2:
                continue
            per.append(sub[sub.pos]["ex_T1"].mean() - sub[~sub.pos]["ex_T1"].mean())
        per = pd.Series(per).dropna()
        tt = (per.mean() / (per.std(ddof=1) / np.sqrt(len(per)))
              if len(per) > 3 and per.std(ddof=1) else np.nan)
        P(f"  {lab}: spearman(with ex_T1)={ic:+.3f} | "
          f"逐日Δ(涨−跌)={per.mean()*100:+.3f}% t={tt:+.2f} n_days={len(per)}")

    P("\n【4】按「板块当日涨跌」分组看候选收益")
    sd = df.dropna(subset=["sec_ret_D"])
    for lab, m in (("板块当日跌", sd.sec_ret_D <= 0), ("板块当日涨", sd.sec_ret_D > 0)):
        g2 = sd[m]
        if len(g2) < 10:
            continue
        P(f"  {lab}: n={len(g2)}  T0={g2.ex_T0.mean()*100:+.3f}%  "
          f"T1={g2.ex_T1.mean()*100:+.3f}%（超额）")

    P("\n【5】分月（T1 超额）")
    df["ym"] = df["date"].str[:7]
    for ym, g2 in df.groupby("ym"):
        x = g2["ex_T1"].dropna()
        if len(x) < 10:
            continue
        t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
        P(f"  {ym}: T1超额={x.mean()*100:+.3f}% t={t:+.2f} n={len(x)}")

    txt = "\n".join(L)
    print(txt)
    (OUT / "candidate_diag.txt").write_text(txt, encoding="utf-8")
    df.to_csv(OUT / "candidate_panel.csv", index=False)
    print(f"\n[written] {OUT/'candidate_diag.txt'}")


if __name__ == "__main__":
    main()
