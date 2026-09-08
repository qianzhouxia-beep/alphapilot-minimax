#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Top2 每日选股 T+5 超额（相对全 A 等权）累计 —— 零侵入，不改 accumulate_top2_t1t5.py
==========================================================================
目的：把 Issue#5 的"对冲证据 n=26 → 持续累计"落地。每次运行读取主脚本累积的
output/top2_t1t5.json（生产每日 16:25 更新），用与 wb_xval_issue5.py 一致的后复权
全 A 等权口径补算每只 pick 的 T+5 超额，输出 output/top2_t1t5_excess.json。

产出：
  rows[i] = {asof, symbol, name, rank, ret5_raw_pct, mkt5_pct, ret5_exc_pct, f1_pass}
  summary = n, mean_raw, mean_exc, win_raw, win_exc, f1_pass_share,
            按 f1_pass 分组 mean_exc/win；time 分组（每 10 天桶）看衰减

用法：
  python scripts/accumulate_top2_excess.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

# import bt_research/wb_breakout_monitor.py 的 build_panel（同目录加载，避免包结构依赖）
import importlib.util  # noqa: E402

_MON_PATH = os.path.join(ROOT, "bt_research", "wb_breakout_monitor.py")
_spec = importlib.util.spec_from_file_location("wb_breakout_monitor", _MON_PATH)
_mon = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mon)  # type: ignore[union-attr]
build_panel = _mon.build_panel

SRC_JSON = os.path.join(ROOT, "output", "top2_t1t5.json")
OUT_JSON = os.path.join(ROOT, "output", "top2_t1t5_excess.json")


def main() -> int:
    if not os.path.exists(SRC_JSON):
        print(f"缺 {SRC_JSON}，先跑 accumulate_top2_t1t5.py")
        return 2

    src = json.load(open(SRC_JSON, encoding="utf-8"))
    rows_in = src.get("rows", [])

    # build panel once (~10s)
    ev, cal, G, Cn, M, syms, j_of, date2g = build_panel()
    cal_idx = {d: i for i, d in enumerate(cal)}

    out_rows = []
    for rec in rows_in:
        asof = pd.Timestamp(rec["asof"])
        if asof not in cal_idx:
            continue
        g = cal_idx[asof]
        for dp in rec.get("picks", []):
            sym = str(dp.get("symbol") or "")[-6:]
            j = j_of.get(sym)
            ret5 = (dp.get("rets") or {}).get("5")
            if j is None or ret5 is None or g + 5 >= G:
                continue
            # 后复权口径股票 T+5 收益率
            c0, c5 = Cn[g, j], Cn[g + 5, j]
            if not (np.isfinite(c0) and np.isfinite(c5) and c0 > 0):
                continue
            stock_ret = c5 / c0 - 1.0
            mkt_ret = M[g + 5] / M[g] - 1.0
            # f1_pass: 该 asof 该股票是否处周线多头方向
            # 需要周线状态 → 从 events 表带出的 f1 不适用（只有事件日）；这里用更简单的
            # 20 周线判定在 build 时未保留，故此处用 60 日均线上方+斜率 近似，标注口径差异。
            # 为避免口径混乱，先记录 f1 为 None，仅累计 raw/exc。f1 拆分留给 wb_xval 的事件级分析。
            out_rows.append({
                "asof": rec["asof"],
                "symbol": sym,
                "name": dp.get("name") or "",
                "rank": dp.get("rank"),
                "ret5_raw_pct": round(float(ret5), 2),
                "stock_ret_adj": round(float(stock_ret * 100), 2),
                "mkt5_pct": round(float(mkt_ret * 100), 4),
                "ret5_exc_pct": round(float((stock_ret - mkt_ret) * 100), 2),
                "f1_pass": None,
            })

    if not out_rows:
        print("无可用 picks（可能都未到 T+5）")
        return 3

    df = pd.DataFrame(out_rows)
    exc = df["ret5_exc_pct"]
    raw = df["ret5_raw_pct"]

    # 时间分桶（每 ~10 交易日）看选股层超额是否也衰减
    uniq = sorted(df["asof"].unique())
    buckets = {}
    for i, a in enumerate(uniq):
        buckets[a] = f"bucket{min(i // 10 + 1, 99)}"
    df["bucket"] = df["asof"].map(buckets)

    summary = {
        "n_picks": int(len(df)),
        "date_span": [df["asof"].min(), df["asof"].max()],
        "mean_raw_pct": round(float(raw.mean()), 2),
        "win_raw": round(float((raw > 0).mean()), 4),
        "mean_exc_pct": round(float(exc.mean()), 2),
        "win_exc": round(float((exc > 0).mean()), 4),
        "median_exc_pct": round(float(exc.median()), 2),
        "by_bucket": {
            b: {"n": int(len(g)), "mean_exc_pct": round(float(g["ret5_exc_pct"].mean()), 2),
                "win_exc": round(float((g["ret5_exc_pct"] > 0).mean()), 4)}
            for b, g in df.groupby("bucket")
        },
        "note": "ret5_exc_pct=后复权口径股票T+5 − 全A等权M; f1_pass 见 wb_xval 事件级分析",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    payload = {"summary": summary, "rows": out_rows}
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print(f"\nsaved {OUT_JSON}  (n={len(out_rows)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
