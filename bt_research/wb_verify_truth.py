# -*- coding: utf-8 -*-
"""真值核查: 确认 §3.1 各口径真实数字 + 混合策略分季/7月稳健性.
目的: 找到 §3.1 表 (+4.53/+4.05/+3.94) 的真实来源, 并算出可复现的替代口径.
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

col = p2[["date", "symbol", "trigger", "px", "tmin", "mode"]].rename(
    columns={"trigger": "trg_p2", "px": "px_p2", "tmin": "tmin_p2", "mode": "mode_p2"}
)
ap = p0.merge(col, on=["date", "symbol"], how="left")
ap = ap.merge(nd, on=["symbol", "date"], how="left").dropna(subset=["c_next"])

px935 = snap[snap["snap_min"] == 5][["date", "symbol", "close", "chg"]].rename(
    columns={"close": "c935", "chg": "chg_935"}
)
px940o = snap[snap["snap_min"] == 10][["date", "symbol", "open"]].rename(columns={"open": "o940"})
px940c = snap[snap["snap_min"] == 10][["date", "symbol", "close"]].rename(columns={"close": "c940"})
px945c = snap[snap["snap_min"] == 15][["date", "symbol", "close"]].rename(columns={"close": "c945"})
for df in (px935, px940o, px940c, px945c):
    ap = ap.merge(df, on=["date", "symbol"], how="left")

ap["lim"] = ap["symbol"].apply(limit_pct)
ap["near_limit"] = ap["chg_935"] >= ap["lim"] * 0.97
ap_clean = ap[~ap["near_limit"]]


def pick_top2(day):
    return day.sort_values("score", ascending=False).head(2)


# 口径1: 全候选池 top2 (与 bt_compare 一致) — §4.1 引用脚本
all_top2 = pd.concat([pick_top2(d) for _, d in ap_clean.groupby("date")])
print("=== 口径1: 全候选池每日Top2 (bt_compare_935_vs_dynconfirm.py) ===")
print(f"n={len(all_top2)}, 天数={all_top2['date'].nunique()}")
for col_px, name in [("c935", "9:35 close"), ("o940", "9:36/9:37(o940 open)"), ("c940", "9:40 close"), ("c945", "9:45 close")]:
    m = all_top2.dropna(subset=[col_px])
    r = m["c_next"] / m[col_px] - 1
    print(f"  {name:22s}: n={len(m):3d} 次日 {r.mean()*100:+5.2f}% 胜率{(r>0).mean()*100:4.1f}% 大跌{(r<-0.05).mean()*100:4.1f}%")

# 口径2: 仅触发子集内 top2 (与 bt_top2_time.py 一致) — §3.1 表来源
trg = ap_clean[ap_clean["trg_p2"]]
trg_top2 = pd.concat([pick_top2(d) for _, d in trg.groupby("date")])
print("\n=== 口径2: 触发子集内每日Top2 (bt_top2_time.py) — §3.1 表真实来源 ===")
print(f"n={len(trg_top2)}, 天数={trg_top2['date'].nunique()}")
for col_px, name in [("c935", "9:35 close"), ("c940", "9:40 close"), ("c945", "9:45 close"), ("px_p2", "触发价")]:
    m = trg_top2.dropna(subset=[col_px])
    r = m["c_next"] / m[col_px] - 1
    print(f"  {name:16s}: n={len(m):3d} 次日 {r.mean()*100:+5.2f}% 胜率{(r>0).mean()*100:4.1f}% 大跌{(r<-0.05).mean()*100:4.1f}%")

# 口径3: 当日收盘口径 (WB 猜最接近 70.4%/11.8%)
print("\n=== 口径3: 触发子集 top2, 当日15:00收盘卖 (对照) ===")
trg_top2["ret_day"] = (trg_top2["ret_day_close"].astype(float)) / 100  # json 是百分比×100
r = trg_top2["ret_day"].dropna()
print(f"  n={len(r)} 当日收盘 {r.mean()*100:+5.2f}% 胜率{(r>0).mean()*100:4.1f}% 大跌{(r<-0.05).mean()*100:4.1f}%")

# 混合策略分季/分月稳健性 (阈值3%)
print("\n=== 混合策略 M3% 分季/分月 (vs 现网全确认) ===")
def hybrid_daily(day, thresh):
    rets = []
    for _, row in day.iterrows():
        if row["chg_935"] < thresh:
            if row["o940"] is not None and np.isfinite(row["o940"]):
                rets.append(row["c_next"] / row["o940"] - 1)
        else:
            if row["trg_p2"]:
                rets.append(row["c_next"] / row["px_p2"] - 1)
    return float(np.mean(rets)) if len(rets) else 0.0

def all_confirm_daily(day):
    trg = day[day["trg_p2"]]
    if len(trg) == 0:
        return 0.0
    return float((trg["c_next"] / trg["px_p2"] - 1).mean())

for col_px in ["o940"]:
    all_top2 = pd.concat([pick_top2(d) for _, d in ap_clean.groupby("date")])
    dates = all_top2["date"].unique()
    df_m = pd.DataFrame({"date": dates})
    df_m["hyb"] = [hybrid_daily(all_top2[all_top2["date"] == d], 0.03) for d in dates]
    df_m["base"] = [all_confirm_daily(all_top2[all_top2["date"] == d]) for d in dates]
    df_m["month"] = df_m["date"].str[:7]
    for mo, g in df_m.groupby("month"):
        print(f"  {mo}: M3% 累计 {g['hyb'].sum()*100:+7.1f}pp | 现网 {g['base'].sum()*100:+7.1f}pp | 差 {(g['hyb']-g['base']).sum()*100:+7.1f}pp")
    q1 = df_m[df_m["date"] <= "2026-05-31"]
    q2 = df_m[df_m["date"] >= "2026-06-01"]
    for name, g in [("Q1(4-5月)", q1), ("Q2(6-7月)", q2)]:
        print(f"  {name}: M3% 累计 {g['hyb'].sum()*100:+7.1f}pp | 现网 {g['base'].sum()*100:+7.1f}pp | 差 {(g['hyb']-g['base']).sum()*100:+7.1f}pp")
