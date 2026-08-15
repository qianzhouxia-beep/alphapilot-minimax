# -*- coding: utf-8 -*-
"""补充: 触发 vs 未触发样本 在 9:35 定格时可预判吗?
关键问题: 动态确认用"9:35后的价格行为"确认质量, 付了追涨成本(触发价高3.14%).
如果 9:35 定格时就有特征能区分好坏, 那可以直接 9:35 价买, 省掉追涨成本.
检查触发/未触发在 9:35 时点的 score / chg_935 / 量比 / 排名 差异.
"""
import json
import numpy as np
import pandas as pd

SNAP = r"C:\Users\elvisq\Projects\alphapilot\bt_research\_board_snap_cache.parquet"
NEXTDAY = r"C:\Users\elvisq\Projects\alphapilot\bt_research\_nextday_cache.parquet"
P2 = r"C:\Users\elvisq\Projects\alphapilot\output\bt_dyn_confirm_long.json"

nd = pd.read_parquet(NEXTDAY)
nd["date"] = nd["date"].astype(str)
snap = pd.read_parquet(SNAP)
snap["date"] = snap["date"].astype(str)
pc = snap[snap["snap_min"] == 330][["symbol", "date", "close"]].sort_values(["symbol", "date"])
pc["prev_close"] = pc.groupby("symbol")["close"].shift(1)
pc = pc[["symbol", "date", "prev_close"]].drop_duplicates()
snap = snap.merge(pc, on=["symbol", "date"], how="left").dropna(subset=["prev_close"])
snap["chg"] = snap["close"] / snap["prev_close"] - 1

dd = json.load(open(P2, encoding="utf-8"))
p0 = pd.DataFrame(dd["trades"]["P0_direct"])
p2 = pd.DataFrame(dd["trades"]["P2_dyn_confirm"])
p0["date"] = p0["date"].astype(str)
p2["date"] = p2["date"].astype(str)
p2["trigger"] = p2["trigger"].astype(bool)
col = p2[["date", "symbol", "trigger", "px", "tmin", "mode"]].rename(
    columns={"trigger": "trg_p2", "px": "px_p2", "tmin": "tmin_p2", "mode": "mode_p2"}
)
ap = p0.merge(col, on=["date", "symbol"], how="left")
ap = ap.merge(nd, on=["symbol", "date"], how="left").dropna(subset=["c_next"])

# 9:35 特征: 涨幅, 开盘缺口, 首根量比(open_px附近?), 用快照的 cum_amount
d935 = snap[snap["snap_min"] == 5][["date", "symbol", "chg", "cum_amount"]].rename(
    columns={"chg": "chg_935", "cum_amount": "amt_935"}
)
ap = ap.merge(d935, on=["date", "symbol"], how="left")
ap["ret_A"] = ap["c_next"] / ap["p935"] - 1

# 每日排名 (score)
ap["rank_in_day"] = ap.groupby("date")["score"].rank(ascending=False)
# 每日成交额排名
ap["amt_rank"] = ap.groupby("date")["amt_935"].rank(ascending=False, pct=True)

trg = ap[ap["trg_p2"]]
nontrg = ap[~ap["trg_p2"]]
print("=== 触发 vs 未触发: 9:35 定格时可观测特征 ===")
for f in ["score", "chg_935", "rank_in_day", "amt_rank"]:
    t = trg[f]
    nt = nontrg[f]
    print(f"  {f:12s}: 触发中位 {t.median():.4f} | 未触发中位 {nt.median():.4f} | 均值差 {t.mean()-nt.mean():+.4f}")

# 9:35 涨幅分组 → 触发率 + 次日收益
print("\n=== 按 9:35 涨幅分组的触发率 ===")
ap["chg_bin"] = pd.cut(ap["chg_935"], [-1, 0, 0.02, 0.04, 1], labels=["<0%", "0~2%", "2~4%", ">4%"])
g = ap.groupby("chg_bin", observed=True).agg(
    n=("chg_935", "size"),
    trg_rate=("trg_p2", "mean"),
    retA=("ret_A", "mean"),
)
print(g.round(4).to_string())

# 触发率 vs score 分位
print("\n=== 按 score 四分位触发率 ===")
ap["score_q"] = pd.qcut(ap["score"], 4, labels=["Q1低", "Q2", "Q3", "Q4高"])
g2 = ap.groupby("score_q", observed=True).agg(
    n=("score", "size"), trg_rate=("trg_p2", "mean"), retA=("ret_A", "mean")
)
print(g2.round(4).to_string())

# 逐日对比: 触发日 vs 未触发日 的 9:35 特征差
print("\n=== 关键检验: 若 9:35 就买触发样本 (6.33%), 未触发样本 (亏2.36%) ===")
print(f"触发率: {trg['trg_p2'].mean()*100:.0f}% ({len(trg)}/{len(ap)})")
print(f"触发样本 A口径(9:35买): {trg['ret_A'].mean()*100:+.2f}% | 未触发: {nontrg['ret_A'].mean()*100:+.2f}%")
print(f"若用 9:35 价买所有 Top2: {ap['ret_A'].mean()*100:+.2f}%")
