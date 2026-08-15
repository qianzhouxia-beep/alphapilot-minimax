# -*- coding: utf-8 -*-
"""正式回测 v2: P0 9:35定格出票后买入 vs P2 动态确认 (生产现行)

关键修正(用户指出): 9:35 不能实时出 Top2, 管线 09:35 开跑→09:35:18→09:36 下单.
因此 "直接买" 的真实可成交价不是 9:35 close, 而是 9:36/9:37 时点价格.
数据只有 5m 粒度, 用 9:40 bar 的 open (9:35-9:40区间第一笔) 作最接近的近似.

口径:
  - 样本: 每日 score Top2 (76天), 剔除 9:35 接近涨停(买不进)
  - 方案A' (9:36/9:37 直接买): px = 9:40 bar open (管线出票后立即市价单)
  - 方案B  (动态确认): px = 触发价, 未触发空仓
  - 卖出: 次日收盘
  - 同时给出 9:35 close 买 / 9:40 close 买 作上下界参考
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


def limit_pct(symbol: str) -> float:
    if symbol.startswith(("300", "301", "688")):
        return 0.20
    if symbol.startswith(("8", "4")):
        return 0.30
    return 0.10


dd = json.load(open(P2, encoding="utf-8"))
p0 = pd.DataFrame(dd["trades"]["P0_direct"])
p2 = pd.DataFrame(dd["trades"]["P2_dyn_confirm"])
p0["date"] = p0["date"].astype(str)
p2["date"] = p2["date"].astype(str)
p2["tmin"] = pd.to_numeric(p2["tmin"], errors="coerce")

# 对齐 P2 触发
col = p2[["date", "symbol", "trigger", "px", "tmin", "mode"]].rename(
    columns={"trigger": "trg_p2", "px": "px_p2", "tmin": "tmin_p2", "mode": "mode_p2"}
)
ap = p0.merge(col, on=["date", "symbol"], how="left")
ap = ap.merge(nd, on=["symbol", "date"], how="left").dropna(subset=["c_next"])

# 各时点价格: snap_min=5(9:35 close), snap_min=10 的 open(≈9:36/9:37成交) 和 close(9:40)
px935 = snap[snap["snap_min"] == 5][["date", "symbol", "close", "chg"]].rename(
    columns={"close": "c935", "chg": "chg_935"}
)
px940o = snap[snap["snap_min"] == 10][["date", "symbol", "open"]].rename(columns={"open": "o940"})
px940c = snap[snap["snap_min"] == 10][["date", "symbol", "close"]].rename(columns={"close": "c940"})
for df in (px935, px940o, px940c):
    ap = ap.merge(df, on=["date", "symbol"], how="left")

# 涨停过滤
ap["lim"] = ap["symbol"].apply(limit_pct)
ap["near_limit"] = ap["chg_935"] >= ap["lim"] * 0.97
ap = ap[~ap["near_limit"]]


def pick_top2(day):
    return day.sort_values("score", ascending=False).head(2)


top2 = pd.concat([pick_top2(d) for _, d in ap.groupby("date")])
print(f"样本: {len(top2)} ({top2['date'].nunique()}天 Top2), 剔除涨停 {ap['near_limit'].sum()}")

# 收益
top2["trg_p2"] = top2["trg_p2"].astype(bool)
top2["ret_c935"] = top2["c_next"] / top2["c935"] - 1          # 9:35 close 买 (理想下界)
top2["ret_o940"] = top2["c_next"] / top2["o940"] - 1          # 9:36/9:37 市价单买 (真实可成交)
top2["ret_c940"] = top2["c_next"] / top2["c940"] - 1          # 9:40 close 买 (保守上界)
top2["ret_p2"] = np.where(top2["trg_p2"], top2["c_next"] / top2["px_p2"] - 1, np.nan)  # 触发才买
top2["o940_valid"] = top2["o940"].notna()


def show(tag, r):
    if len(r) == 0:
        print(f"  {tag:32s}: n=0")
        return
    print(
        f"  {tag:32s}: n={len(r):3d} | 次日收盘 {r.mean()*100:+5.2f}% | 中位 {r.median()*100:+5.2f}% | "
        f"胜率 {(r>0).mean()*100:4.1f}% | 大涨>7% {(r>0.07).mean()*100:4.1f}% | 大跌<-5% {(r<-0.05).mean()*100:4.1f}%"
    )


print("\n===== 成交样本口径 (有 o940 的样本) =====")
ok = top2[top2["o940_valid"]]
show("9:35 close 买 (理想)", ok["ret_c935"])
show("9:36/9:37 市价买 (o940)", ok["ret_o940"])
show("9:40 close 买 (保守)", ok["ret_c940"])
trg_ok = ok[ok["trg_p2"]]
show("触发样本 9:36/9:37买", trg_ok["ret_o940"])
show("触发样本 触发价买", trg_ok["ret_p2"])
nontrg_ok = ok[~ok["trg_p2"]]
show("未触发样本 9:36/9:37买", nontrg_ok["ret_o940"])
print(f"\n  o940 vs c935: {((ok['o940']/ok['c935']-1).mean()*100):+.2f}% (9:36/9:37 相对 9:35 close)")
print(f"  px_p2 vs o940: {((trg_ok['px_p2']/trg_ok['o940']-1).mean()*100):+.2f}% (触发价相对 9:36/9:37 市价)")

print("\n===== 组合口径 (每日 Top2) =====")
comb = {}
comb["A. 9:36/9:37市价全买"] = top2.groupby("date")["ret_o940"].mean()
comb["B. 触发才买(空仓)"] = top2.groupby("date").apply(
    lambda d: d[d["trg_p2"]]["ret_p2"].mean() if d["trg_p2"].any() else 0.0
)
comb["C. 触发才买(未触发按市价)"] = top2.groupby("date").apply(
    lambda d: d[d["trg_p2"]]["ret_p2"].mean() if d["trg_p2"].any() else d["ret_o940"].mean()
)
for name, s in comb.items():
    s = s.dropna()
    print(f"  {name:24s}: 日均 {s.mean()*100:+.2f}% | 累计 {s.sum()*100:+7.1f}pp | 正收益天数 {(s>0).mean()*100:.0f}%")

# 触发时点
print(f"\n  触发时点中位 {top2[top2['trg_p2']]['tmin_p2'].median()} 分 (570=9:30)")
