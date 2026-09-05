#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""资金指纹板块方向日更（生产模块 v1，2026-08-25）

核心思路（来自 bt_research/wb_sector_rotation/ 研究，结论卡
2026-08-25-sector-direction-fingerprint）：
  - 用「个股主力净流入 × 行业映射」聚合成每日行业资金流面板
  - 每天的资金状态用「资金指纹」刻画：行业资金 z（1/5/10日三层）+ 集中度 + 广度 + 风格
  - 对目标日（昨天收盘）找历史最相似的 N 天，统计这些相似日之后各行业
    T+1/T+3/T+5 实际涨跌 → 输出今日板块方向预测
  - 同时计算「行业资金动量是否失效」：过去 20 日行业 5d 流入动量的 RankIC
    均值（<0 = 失效，此时相似匹配的防守价值才启用）

输出:
  - output/sector_fingerprint_daily.json   (机器可读，供 morning_live_fund_select 读取)
  - 企业微信晨报推送（send_markdown）

用法:
  python3 scripts/sector_fingerprint_report.py [--date 2026-08-24] [--no-push]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FLOW_RAW = ROOT / "data" / "fund_flow_history.json"
KLINE = ROOT / "data" / "kline_cache" / "kline_all.parquet"
IND_MAP = ROOT / "data" / "stock_industry_map.json"
OUT = ROOT / "output" / "sector_fingerprint_daily.json"
LOG = ROOT / "output" / "logs" / "sector_fingerprint.log"

TOP_K = 20
TOPN = 6
HORIZONS = (1, 3, 5)
MIN_BEST_SIM = 0.10
IC_WIN = 20  # 动量失效判定窗口
IC_LAG = 2   # IC of day T known after T+1 close = morning of T+2

DEFENSIVE = ["银行", "食品饮料", "公用事业", "煤炭", "非银金融", "交通运输", "医药生物", "家用电器"]
GROWTH = ["计算机", "电子", "通信", "电力设备", "机械设备", "国防军工", "汽车", "传媒"]


def log(msg: str):
    line = f"[{pd.Timestamp.now()}] {msg}"
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


def bare(sym: str) -> str:
    s = "".join(ch for ch in str(sym or "") if ch.isdigit())
    return s.zfill(6)[-6:] if s else ""


def build_panels() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, list[str]]:
    """Return (flow_net, flow_pos, ind_ret0, ind_fwd, inds).

    flow_net: date x industry net inflow (d1 cumulative)
    ind_fwd  : date x industry forward returns (fwd1/fwd3/fwd5 prefixed)
    """
    fund = json.loads(FLOW_RAW.read_text(encoding="utf-8"))
    imap: dict[str, str] = {}
    if IND_MAP.exists():
        raw = json.loads(IND_MAP.read_text(encoding="utf-8"))
        for key, val in (raw or {}).items():
            if isinstance(val, dict):
                imap[bare(key)] = val.get("industry_l1") or "其他"

    recs = []
    for code, series in fund.items():
        if not isinstance(series, dict):
            continue
        c = bare(code)
        l1 = imap.get(c)
        if not l1:
            continue
        for d, v in series.items():
            try:
                recs.append((c, str(d)[:10], l1, float(v)))
            except (TypeError, ValueError):
                continue
    f = pd.DataFrame(recs, columns=["symbol", "date", "l1", "main_net"])
    agg = f.groupby(["date", "l1"])["main_net"].sum().rename("net").reset_index()
    flow_net = agg.pivot(index="date", columns="l1", values="net").sort_index()
    flow_net.index = pd.to_datetime(flow_net.index)

    # kline -> industry daily returns + forward
    k = pd.read_parquet(KLINE, columns=["date", "symbol", "close"])
    k["symbol"] = k["symbol"].map(bare)
    k["date"] = pd.to_datetime(k["date"].astype(str).str[:10])
    k = k[k["symbol"].str[0].isin(list("036"))]
    k["l1"] = k["symbol"].map(imap).fillna("其他")
    k = k.sort_values(["symbol", "date"])
    k["ret1"] = k.groupby("symbol")["close"].pct_change()
    ind_daily = k.groupby(["date", "l1"])["ret1"].mean().rename("r0").reset_index()
    ind_ret0 = ind_daily.pivot(index="date", columns="l1", values="r0").sort_index()
    ind_ret0.columns = [f"ret0|{c}" for c in ind_ret0.columns]

    ind_fwd = ind_ret0.copy()
    for h in HORIZONS:
        tmp = (1 + ind_ret0).rolling(h).apply(np.prod, raw=True) - 1.0
        tmp = tmp.shift(-h)
        tmp.columns = [f"fwd{h}|{c.replace('ret0|','')}" for c in tmp.columns]
        ind_fwd = ind_fwd.join(tmp)

    inds = [c[5:] for c in ind_ret0.columns]
    return flow_net, flow_net, ind_ret0, ind_fwd, inds


def fingerprint_feats(flow_net: pd.DataFrame) -> pd.DataFrame:
    net_cols = [c for c in flow_net.columns]
    layers = {}
    for w, tag in ((1, "d1"), (5, "d5"), (10, "d10")):
        cum = flow_net[net_cols].rolling(w, min_periods=1).sum()
        cum.columns = [f"net_{tag}|{c}" for c in cum.columns]
        layers[tag] = cum
    layered = layers["d1"].join(layers["d5"]).join(layers["d10"])
    zcols = []
    z = pd.DataFrame(index=layered.index)
    for tag in ("d1", "d5", "d10"):
        sub = [c for c in layered.columns if c.startswith(f"net_{tag}|")]
        zz = layered[sub].apply(lambda r: (r - r.mean()) / (r.std() + 1e-9), axis=1)
        zz.columns = [f"z_{tag}|{c.split('|')[1]}" for c in zz.columns]
        z = z.join(zz)
        zcols += list(zz.columns)
    d1 = [c for c in layered.columns if c.startswith("net_d1|")]
    conc = layered[d1].apply(lambda r: r.sort_values(ascending=False).head(5).sum() / (r.abs().sum() + 1e-9), axis=1).rename("conc")
    breadth = (flow_net > 0).sum(axis=1) / len(net_cols)
    inds = [c.split("|")[1] for c in d1]
    gz = z[[f"z_d1|{c}" for c in inds if c in GROWTH]].mean(axis=1)
    dz = z[[f"z_d1|{c}" for c in inds if c in DEFENSIVE]].mean(axis=1)
    style = (gz - dz).rename("style_growth_minus_def")
    feats = z.join(conc).join(breadth.rename("breadth")).join(style)
    return feats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="指纹日期 YYYY-MM-DD（默认：数据最后一日）")
    ap.add_argument("--no-push", action="store_true", help="不推送企业微信")
    args = ap.parse_args()

    log("▶ 资金指纹板块方向日更开始")
    flow_net, _, ind_ret0, ind_fwd, inds = build_panels()
    log(f"  面板: flow={flow_net.shape} fwd={ind_fwd.shape} inds={len(inds)}")

    feats = fingerprint_feats(flow_net)
    # align with kline window
    feats = feats[feats.index >= ind_fwd.index.min()]
    df = feats.join(ind_fwd)

    # fingerprint date
    if args.date:
        fp_date = pd.Timestamp(args.date)
        if fp_date not in df.index:
            fp_date = df.index[-1]
            log(f"  ⚠️ {args.date} 不在面板，回退到 {str(fp_date)[:10]}")
    else:
        fp_date = df.index[-1]
    log(f"  指纹日期: {str(fp_date)[:10]}")

    # momentum health: industry 5d-inflow momentum RankIC vs T+1 (lag2, walk-forward)
    ic_vals = []
    fwd1_cols = [c for c in ind_fwd.columns if c.startswith("fwd1|")]
    inds_ic = [c[5:] for c in fwd1_cols]
    d5_cols = [f"z_d5|{c}" for c in inds_ic]
    for dt in df.index:
        if str(dt)[:10] < "2025-06-01":
            continue
        xs = []
        ys = []
        for c in inds_ic:
            av = df.at[dt, f"z_d5|{c}"]
            bv = df.at[dt, f"fwd1|{c}"]
            if pd.notna(av) and pd.notna(bv):
                xs.append(float(av))
                ys.append(float(bv))
        if len(xs) < 10:
            continue
        a = pd.Series(xs)
        b = pd.Series(ys)
        ic = a.corr(b, method="spearman")
        if pd.notna(ic):
            ic_vals.append((dt, float(ic)))
    ic_df = pd.DataFrame(ic_vals, columns=["date", "ic"]).set_index("date").sort_index()
    # IC known after T+1 close
    ic_df["ic_known"] = ic_df["ic"].shift(IC_LAG)
    health = ic_df.loc[ic_df.index <= fp_date, "ic_known"].dropna().tail(IC_WIN).mean()
    momentum_fail = bool(pd.notna(health) and health < 0)
    log(f"  动量健康: RankIC(5d流入,T+1) 近{IC_WIN}日均值 = {health if pd.notna(health) else 'n/a'}"
        f" {'→ 失效' if momentum_fail else '→ 有效'}")

    # analog matching
    tvec = df.loc[fp_date, list(feats.columns)].values.astype(float)
    sim_days = df.loc[df.index < fp_date].index
    if len(sim_days) < TOP_K:
        log("  历史样本不足，退出")
        return 1
    X = df.loc[sim_days, list(feats.columns)].values.astype(float)
    xm = X - X.mean(axis=1, keepdims=True)
    xsd = X.std(axis=1) + 1e-9
    tv = tvec - tvec.mean()
    tsd = tvec.std() + 1e-9
    corr = (xm @ tv) / (xsd * tsd) / max(len(tv) - 1, 1)
    sim = np.nan_to_num(corr)
    order = np.argsort(-sim)[:TOP_K]
    best_sim = float(sim[order[0]])

    similar = [{"date": str(sim_days[i])[:10], "sim": round(float(sim[i]), 3)} for i in order]

    sector_pred = {}
    for h in HORIZONS:
        fwd_cols = [c for c in ind_fwd.columns if c.startswith(f"fwd{h}|")]
        an_fwd = df.loc[sim_days[order], fwd_cols].mean(axis=0).sort_values(ascending=False)
        top = an_fwd.head(TOPN)
        sector_pred[f"H+{h}"] = {
            "sectors": [c.split("|")[1] for c in top.index],
            "avg_fwd_pct": [round(float(v) * 100, 2) for v in top.values],
        }

    # regime now
    style_now = float(feats.loc[fp_date, "style_growth_minus_def"])
    breadth_now = float(feats.loc[fp_date, "breadth"])
    conc_now = float(feats.loc[fp_date, "conc"])

    out = {
        "asof": str(fp_date)[:10],
        "generated_at": str(pd.Timestamp.now()),
        "momentum": {
            "rankic_5d_flow_t1": round(health, 4) if pd.notna(health) else None,
            "window": IC_WIN,
            "fail": momentum_fail,
            "mode": "soft_active" if momentum_fail else "inactive",
            "note": "动量失效才按指纹加减分（保守模式）；有效时不干预",
        },
        "best_sim": round(best_sim, 3),
        "top_similar_days": similar,
        "sector_prediction": sector_pred,
        "regime_now": {
            "style_growth_minus_def": round(style_now, 3),
            "breadth": round(breadth_now, 3),
            "top5_conc": round(conc_now, 3),
        },
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    log("  wrote " + str(OUT))
    log(f"  预测: H+5 领涨 {sector_pred['H+5']['sectors'][:5]}")

    # WeCom push (markdown)
    if not args.no_push:
        try:
            from scripts.wecom_push import send_markdown
        except ImportError:
            try:
                sys.path.insert(0, str(ROOT / "scripts"))
                from wecom_push import send_markdown
            except ImportError:
                send_markdown = None
        if send_markdown:
            h5 = sector_pred["H+5"]
            h3 = sector_pred["H+3"]
            mode_tag = "⚠️ 动量失效 → 指纹加减分启用" if momentum_fail else "✅ 动量有效 → 不干预"
            md = (
                "### 板块方向晨报（资金指纹）\n"
                f"**{str(fp_date)[:10]} 收盘指纹 → 今日方向**\n\n"
                f"**{mode_tag}**\n\n"
                f"**H+5 领涨**: " + "、".join(
                    f"{s}({p}%)" for s, p in zip(h5["sectors"][:5], h5["avg_fwd_pct"][:5])
                ) + "\n"
                f"**H+3 领涨**: " + "、".join(
                    f"{s}({p}%)" for s, p in zip(h3["sectors"][:5], h3["avg_fwd_pct"][:5])
                ) + "\n\n"
                f"**风格**: 成长-防御差 {style_now:+.2f} · 资金广度 {breadth_now:.0%} · "
                f"集中度 {conc_now:.0%}\n"
                f"**最相似历史日**: " + "、".join(f"{d['date']}({d['sim']:.2f})" for d in similar[:5]) + "\n"
            )
            ok, err = send_markdown(md)
            log(f"  wecom push -> ok={ok} err={err}")
        else:
            log("  wecom_push 不可用，跳过推送")
    log("✔ 完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
