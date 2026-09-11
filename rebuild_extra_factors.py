#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rebuild_extra_factors.py — 每日重建 RD 因子表 (extra_factors.parquet)

问题: 部署的 116 维 v25 模型在生产推理时, 10 个 RD 因子 (rd_a_*) 全部为 0。
原因: extra_factors.parquet 是训练时从 RD 车间复制的静态文件 (仅 ~400 只、止于 07-31),
且 merge_extra_factors 按日期左连接、缺日期补 0 → 生产推理端 RD 维度失效。

修复: 从最新 K线 + 筹码 + 资金流 + 基本面, 按与训练同源的公式为全市场重算
10 个 RD 因子, 覆盖到最新交易日。由 cron 每天 04:35 运行 (05:00 管线之前)。

用法:
  python3 rebuild_extra_factors.py                # 全市场重建 (默认最近 120 交易日)
  python3 rebuild_extra_factors.py --days 30      # 自定义回看
  python3 rebuild_extra_factors.py --limit 20     # 只处理前 20 只 (测试用)
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/ubuntu/alphapilot")
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

import features_v2 as ft
from auto_factor_engine import derive_factors

KLINE = ROOT / "data" / "kline_cache" / "kline_all.parquet"
FUNDAMENTALS = ROOT / "data" / "fundamental_data.json"
OUT = ROOT / "models" / "extra_factors.parquet"

# RD 因子定义: (输出列, 基础列, 变换)
# 基础列来自 build_full_features_v2 + derive_factors 的输出
RD_DEFS = [
    ("rd_a_ret_range_ma_20__ma3", "ret_range_ma_20", "ma3"),
    ("rd_a_ret_range__ma3", "ret_range", "ma3"),
    ("rd_a_turnover_x_atr_pct", None, "turnover_x_atr"),
    ("rd_a_rd_auction_open_atr_ratio__ma5", "rd_auction_open_atr_ratio", "ma5"),
    ("rd_a_atr_pct__z20", "atr_pct", "z20"),
    ("rd_a_ret_range_ma_20__z20", "ret_range_ma_20", "z20"),
    ("rd_a_ret_range_ma_20__diff3", "ret_range_ma_20", "diff3"),
    ("rd_a_profit_margin__ma5", "profit_margin", "ma5"),
    ("rd_a_ret_20d__z20", "ret_20d", "z20"),
    ("rd_a_macd_hist__ma5", "macd_hist", "ma5"),
]


def _transform(series, kind):
    s = pd.Series(series, dtype=float)
    if kind == "ma3":
        return s.rolling(3).mean()
    if kind == "ma5":
        return s.rolling(5).mean()
    if kind == "z20":
        return (s - s.rolling(20).mean()) / (s.rolling(20).std(ddof=0) + 1e-8)
    if kind == "diff3":
        return s.diff(3)
    return s


def build_symbol_rd(code, kl, fundamentals):
    try:
        feats = ft.build_full_features_v2(
            kl, fundamentals=fundamentals, compute_advanced=True,
        )
        if feats is None or len(feats) < 30:
            return None
        derived = derive_factors(feats)
        full = pd.concat([feats, derived], axis=1)
        full = full.loc[:, ~full.columns.duplicated()]
        if "date" not in full.columns:
            return None
        out = pd.DataFrame({"date": full["date"].astype(str).str[:10], "symbol": code})
        for col, base, kind in RD_DEFS:
            if base is None:
                if "turnover" in full.columns and "atr_pct" in full.columns:
                    v = full["turnover"].astype(float) * full["atr_pct"].astype(float)
                else:
                    v = pd.Series(0.0, index=full.index)
            elif base in full.columns:
                v = _transform(full[base].astype(float), kind)
            else:
                v = pd.Series(0.0, index=full.index)
            out[col] = v.values
        out = out.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        return out
    except Exception as e:
        print(f"  ⚠️ {code}: {e}")
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=120, help="回看交易日数")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 只(测试)")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    t0 = time.time()
    print("=" * 60)
    print("rebuild_extra_factors: 全市场重算 RD 因子")
    print("=" * 60)

    # 1. 读取 K线
    kdf = pd.read_parquet(KLINE)
    kdf["date"] = kdf["date"].astype(str)
    kdf["code"] = kdf["symbol"].astype(str).str.replace(r"(sh|sz|bj)", "", regex=True).str[-6:]
    print(f"K线: {len(kdf):,} 行, 日期 {kdf['date'].min()} ~ {kdf['date'].max()}")

    # 按股票分组, 每只只取最近 days 天
    groups = {}
    for code, g in kdf.groupby("code"):
        g = g.sort_values("date")
        if len(g) > 30:
            groups[code] = g.tail(args.days).reset_index(drop=True)
    print(f"股票数: {len(groups)}")

    # 2. 基本面
    fundamentals = {}
    if FUNDAMENTALS.exists():
        try:
            fundamentals = {str(k).zfill(6)[-6:]: v for k, v in json_load(FUNDAMENTALS).items() if isinstance(v, dict)}
        except Exception as e:
            print(f"基本面加载失败: {e}")
    print(f"基本面: {len(fundamentals)} 只")

    # 3. 并行构建
    codes = list(groups.keys())
    if args.limit:
        codes = codes[: args.limit]
    print(f"开始构建 {len(codes)} 只 (workers={args.workers})...")

    frames = []
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {
            ex.submit(build_symbol_rd, code, groups[code], fundamentals.get(code)): code
            for code in codes
        }
        for f in as_completed(futs):
            code = futs[f]
            try:
                r = f.result()
                if r is not None and len(r) > 0:
                    frames.append(r)
            except Exception as e:
                print(f"  ⚠️ {code}: {e}")
            done += 1
            if done % 500 == 0:
                print(f"  {done}/{len(codes)} ({(time.time()-t0)/60:.1f}min)")

    if not frames:
        print("❌ 无结果, 退出")
        return 1

    out = pd.concat(frames, ignore_index=True)
    out["date"] = out["date"].astype(str).str[:10]
    out["symbol"] = out["symbol"].astype(str)
    out = out.sort_values(["symbol", "date"]).drop_duplicates(["symbol", "date"], keep="last")

    # 4. 备份旧文件 → 保存
    if OUT.exists():
        bak = OUT.with_name(f"extra_factors.parquet.bak_{time.strftime('%Y%m%d_%H%M%S')}")
        os.replace(OUT, bak)
        print(f"备份旧文件 → {bak.name}")
    OUT.parent.mkdir(exist_ok=True)
    out.to_parquet(OUT, index=False)

    print("=" * 60)
    print(f"✅ 完成: {len(out):,} 行 x {len(out.columns)} 列")
    print(f"   股票数: {out['symbol'].nunique()}")
    print(f"   日期: {out['date'].min()} ~ {out['date'].max()}")
    print(f"   最新日股票数: {out[out['date'] == out['date'].max()]['symbol'].nunique()}")
    print(f"   耗时: {(time.time()-t0)/60:.1f} min")
    print("=" * 60)
    return 0


def json_load(path):
    import json
    with open(path, encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    sys.exit(main())
