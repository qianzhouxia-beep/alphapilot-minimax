# -*- coding: utf-8 -*-
"""P2 触发时点 vs 次日表现: 回答"换成9:40/9:45选"是否更好.
关键: P2 的 score 是 9:35 定格的, 实际买入由 VWAP 回踩动态触发 (tmin 字段).
比较: 不同触发时点 tmin 的次日收盘表现 + 时点窗口汇总.
"""
import json
import pandas as pd

NEXTDAY = r"C:\Users\elvisq\Projects\alphapilot\bt_research\_nextday_cache.parquet"
P2 = r"C:\Users\elvisq\Projects\alphapilot\output\bt_dyn_confirm_long.json"

nd = pd.read_parquet(NEXTDAY)
nd["date"] = nd["date"].astype(str)
dd = json.load(open(P2, encoding="utf-8"))
ap = pd.DataFrame(dd["trades"]["P2_dyn_confirm"])
ap["date"] = ap["date"].astype(str)
ap = ap.merge(nd, on=["symbol", "date"], how="left").dropna(subset=["c_next"])
ap["ret_close"] = ap["c_next"] / ap["px"] - 1  # px=实际触发成交价

trg = ap[ap["trigger"] == True]

# tmin 是分钟(570=9:30), 分窗口
def bucket(t):
    if t <= 580:
        return "9:40前(含9:40)"
    if t <= 585:
        return "9:45"
    if t <= 600:
        return "10:00"
    if t <= 615:
        return "10:15"
    if t <= 645:
        return "10:30~10:45"
    if t <= 690:
        return "11:00~11:30"
    return "午后(13:00+)"

trg["win"] = trg["tmin"].apply(bucket)
order = ["9:40前(含9:40)", "9:45", "10:00", "10:15", "10:30~10:45", "11:00~11:30", "午后(13:00+)"]

print("=== P2 触发时点 → 次日收盘表现 (实际成交价 px) ===")
g = trg.groupby("win")["ret_close"].agg(["count", "mean", "median"])
g["wr"] = trg.groupby("win")["ret_close"].apply(lambda x: (x > 0).mean())
g["big_win>7%"] = trg.groupby("win")["ret_close"].apply(lambda x: (x > 0.07).mean())
g["big_lose<-5%"] = trg.groupby("win")["ret_close"].apply(lambda x: (x < -0.05).mean())
g = g.loc[[o for o in order if o in g.index]].round(4)
print(g.to_string())

print("\n=== 对照组: 如果同一批票在 9:40 / 9:45 收盘价买入 ===")
# 从快照缓存取 9:40/9:45 收盘价
SNAP = r"C:\Users\elvisq\Projects\alphapilot\bt_research\_board_snap_cache.parquet"
snap = pd.read_parquet(SNAP)
snap["date"] = snap["date"].astype(str)
for label, sm in [("9:40收盘买", 10), ("9:45收盘买", 15)]:
    px = snap[snap["snap_min"] == sm][["date", "symbol", "close"]].rename(columns={"close": "px_late"})
    m = trg.merge(px, on=["date", "symbol"], how="left").dropna(subset=["px_late"])
    m["ret_late"] = m["c_next"] / m["px_late"] - 1
    r = m["ret_late"]
    print(
        f"{label}: n={len(m):3d} 次日收盘 {r.mean()*100:+5.2f}% | "
        f"wr={(r>0).mean()*100:4.1f}% | 大涨{(r>0.07).mean()*100:4.1f}% | 大跌{(r<-0.05).mean()*100:4.1f}%"
    )
r = trg["ret_close"]
print(
    f"实际触发成交(px): n={len(trg):3d} 次日收盘 {r.mean()*100:+5.2f}% | "
    f"wr={(r>0).mean()*100:4.1f}% | 大涨{(r>0.07).mean()*100:4.1f}% | 大跌{(r<-0.05).mean()*100:4.1f}%"
)

# 触发价 vs 9:35 价 的价差: 说明回踩买在低位
m2 = trg.merge(
    snap[snap["snap_min"] == 5][["date", "symbol", "close"]].rename(columns={"close": "c935"}),
    on=["date", "symbol"], how="left"
).dropna(subset=["c935"])
discount = (m2["px"] / m2["c935"] - 1)
print(f"\n触发成交价 vs 9:35 收盘价: 平均 {discount.mean()*100:+.2f}% (负=回踩买在9:35下方)")
