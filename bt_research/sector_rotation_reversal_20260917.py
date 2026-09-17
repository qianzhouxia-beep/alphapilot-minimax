#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""板块资金流 → 未来收益 反转检验（2026-09-17 Cursor）

老板问题：9 月板块轮动很快，今天资金流出的板块，明天/后天它对应的股票会不会涨？
重点：经常轮动的热门板块，尤其科技方向。

数据（服务器只读切片 → bt_research/_sector_rotation/data/）：
  sector_flow.csv   申万二级行业日度主力净流入（32 行业，2026-08-07 起完整）
  kline.parquet     个股日线 open/close（2026-06-01 起）
  industry_map.json 个股 → 申万二级行业（与上表同口径）

口径（与仓内既有研究一致，防前视）：
  · 信号日 D 的资金流在 D 收盘后可得；
  · 入场 = D+1 开盘（贴近生产 09:36 入场）；
  · T0 = close(D+1)/open(D+1) - 1（当日）
  · T1 = close(D+2)/open(D+1) - 1（隔日）
  · 板块收益 = 成分股等权；超额 = 板块 − 全市场等权（同口径）
  · 归一化用**日内横截面分位**（免成交额口径），并附行业内 z-score 稳健性

统计：按日做横截面配对，再对日序列取 t 值（规避同日内截面相关）。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

D = Path(__file__).resolve().parent / "_sector_rotation" / "data"
OUT = Path(__file__).resolve().parent / "_sector_rotation"

# 科技方向：先窄后宽两档（都在 32 个可用二级行业之内）
TECH_CORE = {"半导体", "消费电子", "元件", "光学光电子", "软件开发",
             "IT服务Ⅱ", "通信设备", "通信服务", "计算机设备"}
TECH_BROAD = TECH_CORE | {"电池", "光伏设备", "电网设备", "自动化设备",
                          "通用设备", "专用设备", "航空装备Ⅱ"}


def load():
    k = pd.read_parquet(D / "kline.parquet")
    flow = pd.read_csv(D / "sector_flow.csv")
    imap = json.loads((D / "industry_map.json").read_text(encoding="utf-8"))

    k["code"] = k["symbol"].astype(str).str.split(".").str[0].str.zfill(6)
    code2l2 = {str(c).split(".")[0].zfill(6): (v or {}).get("industry_l2")
               for c, v in imap.items()}
    k["l2"] = k["code"].map(code2l2)
    k = k.dropna(subset=["l2", "open", "close"]).sort_values(["code", "date"])

    g = k.groupby("code", sort=False)
    k["nopen"] = g["open"].shift(-1)
    k["nclose"] = g["close"].shift(-1)
    k["nnclose"] = g["close"].shift(-2)
    k["ret_D"] = k["close"] / g["close"].shift(1) - 1.0
    k["ret_T0"] = k["nclose"] / k["nopen"] - 1.0
    k["ret_T1"] = k["nnclose"] / k["nopen"] - 1.0
    k = k[np.isfinite(k["ret_D"])]

    # 全市场等权基准（同口径）
    mkt = (k.groupby("date")[["ret_D", "ret_T0", "ret_T1"]].mean()
           .add_prefix("mkt_"))

    sec = k.groupby(["date", "l2"])[["ret_D", "ret_T0", "ret_T1"]].mean()
    sec = sec.join(mkt, on="date")
    for c in ("D", "T0", "T1"):
        sec["ex_" + c] = sec["ret_" + c] - sec["mkt_ret_" + c]
    sec = sec.reset_index()

    f = flow.rename(columns={"trade_date": "date", "sector_name": "l2"})
    df = sec.merge(f[["date", "l2", "main_net"]], on=["date", "l2"], how="inner")
    df = df.sort_values(["date", "l2"])

    # 信号：日内横截面分位（0=最流出, 1=最流入）
    df["flow_rank"] = df.groupby("date")["main_net"].rank(pct=True)
    # 行业内时序 z-score（稳健性口径）
    mu = df.groupby("l2")["main_net"].transform("mean")
    sd = df.groupby("l2")["main_net"].transform("std")
    df["flow_z"] = (df["main_net"] - mu) / sd.replace(0, np.nan)
    # 连续流出天数（含当日）
    df = df.sort_values(["l2", "date"]).reset_index(drop=True)
    df["is_out"] = (df["main_net"] <= 0).astype(int)
    streaks = []
    for _, sub in df.groupby("l2", sort=False):
        st = 0
        for v in sub["is_out"]:
            st = st + 1 if v == 1 else 0
            streaks.append(st)
    df["out_streak"] = streaks
    return df


def daily_pair(df, mask_a, mask_b, col):
    """逐日横截面均值差 + 日序列 t 值。"""
    a = df[mask_a].groupby("date")[col].mean()
    b = df[mask_b].groupby("date")[col].mean()
    d = (a - b).dropna()
    if len(d) < 3:
        return {"n_days": len(d), "mean": None, "t": None, "win": None}
    m, s = d.mean(), d.std(ddof=1)
    return {"n_days": len(d), "mean": float(m),
            "t": float(m / (s / np.sqrt(len(d)))) if s else None,
            "win": float((d > 0).mean()),
            "pos_days": int((d > 0).sum())}


def describe(df, col, label):
    x = df[col].dropna()
    if not len(x):
        return f"{label}: n=0"
    m, s = x.mean(), x.std(ddof=1)
    t = m / (s / np.sqrt(len(x))) if s and len(x) > 1 else float("nan")
    return (f"{label}: n={len(x)} mean={m*100:+.3f}% med={x.median()*100:+.3f}% "
            f"t={t:+.2f}")


def rank_ic(df, col, sig="flow_rank"):
    ics = []
    for _, sub in df.groupby("date"):
        s = sub[[sig, col]].dropna()
        if len(s) >= 8:
            ics.append(s[sig].corr(s[col], method="spearman"))
    ics = pd.Series(ics).dropna()
    if len(ics) < 3:
        return {"n": len(ics)}
    return {"n": int(len(ics)), "ic": float(ics.mean()),
            "t": float(ics.mean() / (ics.std(ddof=1) / np.sqrt(len(ics)))),
            "hit": float((ics > 0).mean())}


def main():
    df = load()
    df = df[df["date"] >= "2026-08-07"].copy()   # 32 行业完整窗口起点
    s_all = df
    s_sep = df[df["date"] >= "2026-09-01"]
    tech = df[df["l2"].isin(TECH_CORE)]
    techb = df[df["l2"].isin(TECH_BROAD)]

    L = []
    P = L.append
    P("=" * 78)
    P("板块资金流 → 未来收益（反转?）检验   Cursor 2026-09-17")
    P(f"面板: {df.date.nunique()} 交易日 × {df.l2.nunique()} 行业 = {len(df)} 观测 "
      f"（{df.date.min()} ~ {df.date.max()}）")
    P(f"9 月窗口: {s_sep.date.nunique()} 日 × {s_sep.l2.nunique()} 行业 = {len(s_sep)}")
    P("=" * 78)

    P("\n【0】基准水平（等权，D+1 开盘入场）")
    for lab, d in (("全窗口", s_all), ("9月", s_sep)):
        P(f"  {lab} T0={d.ex_T0.mean()*100:+.3f}%  T1={d.ex_T1.mean()*100:+.3f}%  "
          f"(相对全市场等权超额)")

    P("\n【1】核心问题：D 日【流出】板块，D+1/D+2 表现如何？")
    for lab, d in (("全窗口", s_all), ("9月", s_sep),
                   ("科技·窄", tech), ("科技·宽", techb)):
        out = d[d.main_net < 0]
        inn = d[d.main_net > 0]
        P(f"\n  {lab}:  流出 n={len(out)} / 流入 n={len(inn)}")
        P("    " + describe(out, "ex_T0", "流出 T0"))
        P("    " + describe(out, "ex_T1", "流出 T1"))
        P("    " + describe(inn, "ex_T0", "流入 T0"))
        P("    " + describe(inn, "ex_T1", "流入 T1"))
        for col in ("ex_T0", "ex_T1"):
            r = daily_pair(d, d.main_net < 0, d.main_net > 0, col)
            if r["mean"] is not None:
                P(f"    Δ(流出−流入) {col}: {r['mean']*100:+.3f}% "
                  f"t={r['t']:+.2f} 胜日 {r['pos_days']}/{r['n_days']}")

    P("\n【2】分位分组（0=最流出 … 3=最流入，按日内横截面）")
    for lab, d in (("全窗口", s_all), ("9月", s_sep), ("科技·宽", techb)):
        dd = d.dropna(subset=["flow_rank"]).copy()
        dd["q"] = pd.qcut(dd["flow_rank"], 4, labels=[0, 1, 2, 3],
                          duplicates="drop")
        P(f"\n  {lab}")
        P("    " + "  ".join(
            f"Q{q}:T1={g.ex_T1.mean()*100:+.2f}%(n={len(g)})"
            for q, g in dd.groupby("q", observed=True)))

    P("\n【3】秩相关（flow_rank vs 未来超额；正=越流入越涨）")
    for lab, d in (("全窗口", s_all), ("9月", s_sep), ("科技·宽", techb)):
        P(f"  {lab} T0: {rank_ic(d,'ex_T0')}")
        P(f"  {lab} T1: {rank_ic(d,'ex_T1')}")

    P("\n【4】连续流出（out_streak）分层：T1 超额")
    for lab, d in (("全窗口", s_all), ("9月", s_sep), ("科技·宽", techb)):
        dd = d[d.main_net < 0]
        P(f"  {lab}")
        for lo, hi in ((1, 1), (2, 2), (3, 99)):
            g = dd[(dd.out_streak >= lo) & (dd.out_streak <= hi)]
            if len(g):
                P(f"    流出{lo}{'+' if hi == 99 else ''}日: "
                  f"T1={g.ex_T1.mean()*100:+.3f}% n={len(g)}")

    P("\n【5】热门度（按资金流日间翻转换手频率 = 轮动速度）")
    flip = {}
    for l2, sub in s_all.sort_values("date").groupby("l2"):
        s = np.sign(sub["main_net"].values)
        flip[l2] = float(np.mean(s[1:] != s[:-1])) if len(s) > 2 else np.nan
    fr = pd.Series(flip).dropna().sort_values(ascending=False)
    P("    轮动最快 8 个行业: " + ", ".join(
        f"{k}({v:.0%})" for k, v in fr.head(8).items()))
    hot = set(fr.head(len(fr) // 2).index)
    P("    轮动最慢 5 个行业: " + ", ".join(f"{k}({v:.0%})" for k, v in fr.tail(5).items()))
    for lab, d in (("全窗口", s_all), ("9月", s_sep)):
        h = d[d.l2.isin(hot)]
        P(f"\n  {lab} · 高轮动行业 (n={len(h)})")
        P("    " + describe(h[h.main_net < 0], "ex_T1", "高轮动·流出 T1"))
        P("    " + describe(h[h.main_net > 0], "ex_T1", "高轮动·流入 T1"))
        r = daily_pair(h, h.main_net < 0, h.main_net > 0, "ex_T1")
        if r["mean"] is not None:
            P(f"    Δ(流出−流入) T1: {r['mean']*100:+.3f}% t={r['t']:+.2f} "
              f"胜日 {r['pos_days']}/{r['n_days']}")

    P("\n【6】行业内 z-score 口径（剔行业规模效应）")
    for lab, d in (("全窗口", s_all), ("9月", s_sep)):
        dd = d.dropna(subset=["flow_z"])
        lo = dd[dd.flow_z <= -1]
        hi = dd[dd.flow_z >= 1]
        P(f"  {lab}:  z≤-1 T1={lo.ex_T1.mean()*100:+.3f}%(n={len(lo)})  "
          f"z≥+1 T1={hi.ex_T1.mean()*100:+.3f}%(n={len(hi)})")

    # ── 关键控制：流出日≈下跌日 ⇒ 必须区分「资金流信息」与「短期价格反转」──
    P("\n【7】混淆诊断：资金流 vs 当日涨跌")
    for lab, d in (("全窗口", s_all), ("9月", s_sep)):
        dd = d.dropna(subset=["main_net", "ret_D"])
        r = dd["flow_rank"].corr(dd["ret_D"], method="spearman")
        neg = dd[dd.ret_D < 0]
        P(f"  {lab}: spearman(flow_rank, 当日板块涨跌)={r:+.3f}；"
          f"当日下跌板块中流出占比={((neg.main_net<0).mean()):.0%}")

    P("\n【8】双排序：控制「当日涨跌」后，流出还有没有增量？（T1 超额 %）")
    for lab, d in (("全窗口", s_all), ("9月", s_sep), ("科技·宽", techb)):
        dd = d.dropna(subset=["flow_rank", "ret_D", "ex_T1"]).copy()
        if len(dd) < 30:
            continue
        dd["rq"] = dd.groupby("date")["ret_D"].transform(
            lambda s: pd.qcut(s.rank(method="first"), 3, labels=[0, 1, 2]))
        dd["fq"] = dd.groupby("date")["flow_rank"].transform(
            lambda s: pd.qcut(s.rank(method="first"), 3, labels=[0, 1, 2]))
        pv = dd.pivot_table(index="rq", columns="fq", values="ex_T1",
                            aggfunc="mean", observed=True) * 100
        cnt = dd.pivot_table(index="rq", columns="fq", values="ex_T1",
                             aggfunc="size", observed=True)
        P(f"  {lab}   列=资金流(0最流出→2最流入) 行=当日涨跌(0跌→2涨)")
        for rq in pv.index:
            P("    " + "  ".join(
                f"{pv.loc[rq, fq]:+.2f}%(n={cnt.loc[rq, fq]})"
                for fq in pv.columns if pd.notna(pv.loc[rq, fq])))

    P("\n【9】Fama-MacBeth：ex_T1 ~ flow_z + 当日涨跌（逐日回归，看流量是否仍有增量）")
    for lab, d in (("全窗口", s_all), ("9月", s_sep), ("科技·宽", techb)):
        dd = d.dropna(subset=["flow_z", "ret_D", "ex_T1"]).copy()
        cs = []
        for _, sub in dd.groupby("date"):
            if len(sub) < 10:
                continue
            X = np.column_stack([np.ones(len(sub)), sub["flow_z"].values,
                                 sub["ret_D"].values])
            b, *_ = np.linalg.lstsq(X, sub["ex_T1"].values, rcond=None)
            cs.append(b)
        if len(cs) < 5:
            P(f"  {lab}: 交易日不足"); continue
        c = np.array(cs)
        mu = c.mean(0)
        se = c.std(0, ddof=1) / np.sqrt(len(c))
        tt = mu / se
        P(f"  {lab} (n_days={len(c)})  intercept={mu[0]*100:+.3f}%(t={tt[0]:+.2f})"
          f"  flow_z={mu[1]*100:+.3f}%(t={tt[1]:+.2f})"
          f"  ret_D={mu[2]*100:+.3f}%(t={tt[2]:+.2f})")

    P("\n【10】正交化：剔除「当日涨跌」后的资金流残差（= 纯资金流信息）")
    for lab, d in (("全窗口", s_all), ("9月", s_sep), ("科技·宽", techb)):
        dd = d.dropna(subset=["flow_z", "ret_D", "ex_T0", "ex_T1"]).copy()
        parts = []
        for _, sub in dd.groupby("date"):
            if len(sub) < 8:
                continue
            b = np.polyfit(sub["ret_D"].values, sub["flow_z"].values, 1)
            s = sub.copy()
            s["flow_resid"] = sub["flow_z"].values - (
                b[0] * sub["ret_D"].values + b[1])
            parts.append(s)
        if not parts:
            continue
        o = pd.concat(parts)
        P(f"  {lab}  (正交化后有效 n={len(o)}, {o.date.nunique()} 日)")
        for col in ("ex_T0", "ex_T1"):
            ics = []
            for _, sub in o.groupby("date"):
                if len(sub) >= 8:
                    ics.append(sub["flow_resid"].corr(sub[col], method="spearman"))
            ics = pd.Series(ics).dropna()
            if len(ics) < 3:
                continue
            tt = ics.mean() / (ics.std(ddof=1) / np.sqrt(len(ics)))
            P(f"    残差 vs {col}: IC={ics.mean():+.3f} t={tt:+.2f} 日数={len(ics)}")
        o["hi"] = o.groupby("date")["flow_resid"].transform(
            lambda s: s.rank(pct=True) > 0.5)
        for col in ("ex_T0", "ex_T1"):
            r = daily_pair(o, ~o["hi"], o["hi"], col)
            if r["mean"] is not None:
                P(f"    残差高半−低半 {col}: {r['mean']*100:+.3f}% t={r['t']:+.2f} "
                  f"胜日 {r['pos_days']}/{r['n_days']}")

    P("\n【11】纯价格反转：按「当日板块涨跌」分组看未来超额（可执行版）")
    for lab, d in (("全窗口", s_all), ("9月", s_sep), ("科技·宽", techb)):
        dd = d.dropna(subset=["ret_D", "ex_T0", "ex_T1"]).copy()
        dd["rq"] = dd.groupby("date")["ret_D"].transform(
            lambda s: pd.qcut(s.rank(method="first"), 3, labels=[0, 1, 2]))
        P(f"  {lab}")
        for q, g in dd.groupby("rq", observed=True):
            nm = {0: "跌", 1: "平", 2: "涨"}[q]
            P(f"    当日{nm}: T0={g.ex_T0.mean()*100:+.3f}%  "
              f"T1={g.ex_T1.mean()*100:+.3f}%  n={len(g)}")
        for col in ("ex_T0", "ex_T1"):
            r = daily_pair(dd, dd.rq == 0, dd.rq == 2, col)
            if r["mean"] is not None:
                P(f"    Δ(跌−涨) {col}: {r['mean']*100:+.3f}% t={r['t']:+.2f} "
                  f"胜日 {r['pos_days']}/{r['n_days']}")

    txt = "\n".join(L)
    print(txt)
    (OUT / "reversal_report.txt").write_text(txt, encoding="utf-8")
    df.to_csv(OUT / "panel.csv", index=False)
    (OUT / "hot_sectors.json").write_text(
        json.dumps({"rotation_freq": {k: round(v, 4) for k, v in fr.items()},
                    "hot_half": sorted(hot)}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(f"\n[written] {OUT/'reversal_report.txt'} / panel.csv / hot_sectors.json")


if __name__ == "__main__":
    main()
