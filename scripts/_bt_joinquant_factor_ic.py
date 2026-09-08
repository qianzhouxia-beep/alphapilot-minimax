# -*- coding: utf-8 -*-
"""聚宽社区候选因子 — A股次日 Rank IC 实测 (服务器跑)
口径: RankIC(因子值, 次日收益) 逐日截面, 输出 IC均值/IC_IR/正IC比例/显著性
数据: kline_all.parquet 2025-01-02 ~ 2026-08-28, 4991 只
候选因子来源: 聚宽社区 260因子检验 + 中金价量手册 + 用户调研
"""
import pandas as pd
import numpy as np
from scipy.stats import spearmanr
import os, sys, json

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

KLINE = "/home/ubuntu/alphapilot/data/kline_cache/kline_all.parquet"
OUT = "/home/ubuntu/alphapilot/output/bt_joinquant_factor_ic.json"
MIN_STOCKS = 200   # 每交易日最少股票数
MIN_DAYS = 20      # 最少有效截面日


def build_factors(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["symbol", "date"]).copy()
    g = df.groupby("symbol", group_keys=False)

    # --- 次日收益 (前瞻 1 日) ---
    df["ret_next"] = g["close"].pct_change().shift(-1)

    # --- 市值 ---
    df["mktcap"] = df["close"] * df["outstanding_share"]
    df["ln_mktcap"] = np.log(df["mktcap"] + 1e-9)

    # --- 反转/动量类 ---
    df["ret_1d"] = g["close"].pct_change(1)
    df["ret_5d"] = g["close"].pct_change(5)
    df["ret_20d"] = g["close"].pct_change(20)

    # --- 量价类 ---
    df["vol_ma_ratio"] = df["volume"] / (g["volume"].transform(lambda x: x.rolling(20).mean()) + 1e-9)
    df["amount_ma_ratio"] = df["amount"] / (g["amount"].transform(lambda x: x.rolling(20).mean()) + 1e-9)
    df["tvstd20"] = g["amount"].transform(lambda x: x.rolling(20).std()) / (g["amount"].transform(lambda x: x.rolling(20).mean()) + 1e-9)
    df["turnover_ratio"] = df["turnover"] / (g["turnover"].transform(lambda x: x.rolling(20).mean()) + 1e-9)

    # --- 波动率类 ---
    tr = pd.concat([df["high"] - df["low"], (df["high"] - df["close"].shift(1)).abs(),
                    (df["low"] - df["close"].shift(1)).abs()], axis=1).max(axis=1)
    df["atr14"] = tr.groupby(df["symbol"]).transform(lambda x: x.rolling(14).mean()) / (df["close"] + 1e-9)
    df["ret_range"] = (df["high"] - df["low"]) / (df["low"] + 1e-9)
    df["ret_range_ma20"] = df["ret_range"].groupby(df["symbol"]).transform(lambda x: x.rolling(20).mean())
    df["vol_20d"] = g["close"].transform(lambda x: x.pct_change().rolling(20).std())

    # --- 量价相关/背离 ---
    df["corr_ret_vol_20"] = (df["ret_1d"] * np.sign(df["volume"].diff())).groupby(df["symbol"]).transform(
        lambda x: x.rolling(20).mean())

    return df


def rank_ic_series(df: pd.DataFrame, factor_col: str) -> dict:
    """逐日截面 RankIC(因子, 次日收益)"""
    ics = []
    for d, sub in df.groupby("date"):
        sub = sub.dropna(subset=[factor_col, "ret_next"])
        if len(sub) < MIN_STOCKS:
            continue
        ic, _ = spearmanr(sub[factor_col], sub["ret_next"])
        if np.isfinite(ic):
            ics.append(ic)
    ics = np.array(ics)
    if len(ics) < MIN_DAYS:
        return {"factor": factor_col, "n_days": len(ics), "error": "too_few_days"}
    mean_ic = ics.mean()
    std_ic = ics.std(ddof=1) if len(ics) > 1 else 0
    t_stat = mean_ic / (std_ic / np.sqrt(len(ics))) if std_ic > 0 else 0
    # 简单 t 检验 p 值
    from scipy.stats import t as tdist
    p_val = 2 * (1 - tdist.cdf(abs(t_stat), df=len(ics) - 1))
    return {
        "factor": factor_col,
        "n_days": len(ics),
        "ic_mean": round(float(mean_ic), 4),
        "ic_std": round(float(std_ic), 4),
        "ic_ir": round(float(mean_ic / std_ic), 3) if std_ic > 0 else 0,
        "pct_positive": round(float((ics > 0).mean() * 100), 1),
        "t_stat": round(float(t_stat), 2),
        "p_value": round(float(p_val), 4),
    }


def main():
    df = pd.read_parquet(KLINE)
    df["date"] = pd.to_datetime(df["date"])
    # 过滤 ST / 低价股 (避免异常)
    df = df[~df["symbol"].astype(str).str.startswith(("ST", "*ST"))]
    print(f"原始: {len(df)} 行, {df['symbol'].nunique()} 只", flush=True)

    fac_df = build_factors(df)
    print(f"因子构建完成: {len(fac_df)} 行", flush=True)

    factors = [
        # 反转/动量
        "ret_1d", "ret_5d", "ret_20d",
        # 量价
        "vol_ma_ratio", "amount_ma_ratio", "tvstd20", "turnover_ratio",
        # 波动率
        "atr14", "ret_range_ma20", "vol_20d",
        # 量价背离
        "corr_ret_vol_20",
        # 市值
        "ln_mktcap",
    ]

    results = []
    for f in factors:
        r = rank_ic_series(fac_df, f)
        results.append(r)
        if "error" in r:
            print(f"  {f}: {r['error']}")
        else:
            print(f"  {f:20s} IC={r['ic_mean']:+.4f} IR={r['ic_ir']:+.3f} "
                  f"正IC%={r['pct_positive']:5.1f} p={r['p_value']:.4f} n={r['n_days']}d")

    with open(OUT, "w", encoding="utf-8") as fp:
        json.dump(results, fp, ensure_ascii=False, indent=2)
    print("saved:", OUT)


if __name__ == "__main__":
    main()
