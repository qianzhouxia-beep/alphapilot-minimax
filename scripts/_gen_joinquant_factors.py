# -*- coding: utf-8 -*-
"""聚宽社区候选因子 → rd_workshop 标准因子宽表 (date/symbol/rd_*)
服务器跑：python3 scripts/_gen_joinquant_factors.py
输出：rd_workshop/data_support/inbound/joinquant_factors_20260830.parquet
因子：
  首选: rd_tvstd20 / rd_corr_ret_vol_20 / rd_vol_ma_ratio
  候选: rd_turnover_vol_ratio
口径与 IC 验证脚本一致（kline_all.parquet 全市场分组滚动）。
"""
import os, sys
import pandas as pd
import numpy as np
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
ROOT = Path(os.environ.get("ALPHAPILOT_ROOT") or "/home/ubuntu/alphapilot")
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
from rd_workshop.normalize_factors import bare_code

KLINE = ROOT / "data" / "kline_cache" / "kline_all.parquet"
OUT = ROOT / "rd_workshop" / "data_support" / "inbound" / "joinquant_factors_20260830.parquet"


def main() -> int:
    df = pd.read_parquet(KLINE)
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df["symbol"] = df["symbol"].map(bare_code)
    df = df.sort_values(["symbol", "date"]).reset_index(drop=True)
    print(f"rows={len(df)} symbols={df['symbol'].nunique()} span={df['date'].min()}~{df['date'].max()}", flush=True)

    g = df.groupby("symbol", group_keys=False)

    # --- 首选 1: tvstd20 = amount 20日 std / amount 20日 mean ---
    amt_mean = g["amount"].transform(lambda x: x.rolling(20, min_periods=10).mean())
    amt_std = g["amount"].transform(lambda x: x.rolling(20, min_periods=10).std())
    df["rd_tvstd20"] = amt_std / (amt_mean + 1e-9)

    # --- 首选 2: corr_ret_vol_20 = 量价背离 (ret_1d * sign(vol diff)) 20日均 ---
    ret1 = g["close"].pct_change()
    vol_sign = np.sign(g["volume"].diff())
    df["rd_corr_ret_vol_20"] = (ret1 * vol_sign).groupby(df["symbol"]).transform(
        lambda x: x.rolling(20, min_periods=10).mean())

    # --- 首选 3: vol_ma_ratio = volume / volume 20日 mean ---
    vol_mean = g["volume"].transform(lambda x: x.rolling(20, min_periods=10).mean())
    df["rd_vol_ma_ratio"] = df["volume"] / (vol_mean + 1e-9)

    # --- 候选: turnover_vol_ratio = turnover / turnover 20日 std (加eps防爆) ---
    to_std = g["turnover"].transform(lambda x: x.rolling(20, min_periods=10).std())
    df["rd_turnover_vol_ratio"] = df["turnover"] / (to_std + 1e-9)

    # --- 候选: turnover_ratio = turnover / turnover 20日 mean (实测 IC=-0.030) ---
    to_mean = g["turnover"].transform(lambda x: x.rolling(20, min_periods=10).mean())
    df["rd_turnover_ratio"] = df["turnover"] / (to_mean + 1e-9)

    keep = ["date", "symbol", "rd_tvstd20", "rd_corr_ret_vol_20", "rd_vol_ma_ratio",
            "rd_turnover_vol_ratio", "rd_turnover_ratio"]
    out = df[keep].replace([np.inf, -np.inf], np.nan)
    out["symbol"] = out["symbol"].astype(str)
    out = out.dropna(subset=["date", "symbol"])
    out = out.sort_values(["symbol", "date"]).drop_duplicates(["symbol", "date"], keep="last")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    print(f"factor cols: {list(out.columns)[2:]}")
    for c in keep[2:]:
        print(f"  {c}: nonnull={out[c].notna().mean():.2%} mean={out[c].mean():.4f} std={out[c].std():.4f}")
    print(f"wrote {OUT} rows={len(out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
