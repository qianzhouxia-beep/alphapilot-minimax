# -*- coding: utf-8 -*-
"""直接回答用户问题: P2 每日 Top2, 换成 9:40 / 9:45 时点买, 表现如何?
对比 4 种入场:
  A. 9:35 收盘价买 (score Top2 后立即市价)
  B. 9:40 收盘价买
  C. 9:45 收盘价买
  D. 实际触发价 px 买 (现网动态确认)
注意: 9:40/9:45 买需剔除"涨停买不进"(用当日 15:00 close 判断是否涨停? 简化用 9:40/9:45 价格相对涨跌幅)
"""
import json
import pandas as pd

SNAP = r"C:\Users\elvisq\Projects\alphapilot\bt_research\_board_snap_cache.parquet"
NEXTDAY = r"C:\Users\elvisq\Projects\alphapilot\bt_research\_nextday_cache.parquet"
P2 = r"C:\Users\elvisq\Projects\alphapilot\output\bt_dyn_confirm_long.json"

nd = pd.read_parquet(NEXTDAY)
nd["date"] = nd["date"].astype(str)
snap = pd.read_parquet(SNAP)
snap["date"] = snap["date"].astype(str)

dd = json.load(open(P2, encoding="utf-8"))
ap = pd.DataFrame(dd["trades"]["P2_dyn_confirm"])
ap["date"] = ap["date"].astype(str)
ap = ap.merge(nd, on=["symbol", "date"], how="left").dropna(subset=["c_next"])

# 各时点价格
pc = snap[snap["snap_min"] == 330][["symbol", "date", "close"]].sort_values(["symbol", "date"])
pc["prev_close"] = pc.groupby("symbol")["close"].shift(1)
pc = pc[["symbol", "date", "prev_close"]].drop_duplicates()
snap = snap.merge(pc, on=["symbol", "date"], how="left").dropna(subset=["prev_close"])
snap["chg"] = snap["close"] / snap["prev_close"] - 1

for sm, col in [(5, "c935"), (10, "c940"), (15, "c945")]:
    t = snap[snap["snap_min"] == sm][["date", "symbol", "close"]].rename(columns={"close": col})
    ap = ap.merge(t, on=["date", "symbol"], how="left")
# 涨停判断: 9:40 时涨幅>=9.5% 视为买不进 (主板), 简化统一用 >=9%
for sm, col in [(10, "c940"), (15, "c945")]:
    t = snap[snap["snap_min"] == sm][["date", "symbol", "chg"]].rename(columns={"chg": f"chg_{col}"})
    ap = ap.merge(t, on=["date", "symbol"], how="left")

ap["buy_px"] = ap["px"].fillna(ap["p935"])
trg = ap[ap["trigger"] == True]


def score_top2(day):
    return day.sort_values("score", ascending=False).head(2)


top2 = pd.concat([score_top2(d) for _, d in trg.groupby("date")])
print(f"Top2 样本: {len(top2)}, 天数 {top2['date'].nunique()}")

# 入场 A/B/C/D
def show(tag, px_col, extra_filter=None):
    m = top2.dropna(subset=[px_col]).copy()
    if extra_filter is not None:
        m = m[extra_filter(m)]
    m["ret"] = m["c_next"] / m[px_col] - 1
    r = m["ret"]
    print(
        f"{tag:34s}: n={len(m):3d} 次日收盘 {r.mean()*100:+5.2f}% | "
        f"wr={(r>0).mean()*100:4.1f}% | 大涨{(r>0.07).mean()*100:4.1f}% | 大跌{(r<-0.05).mean()*100:4.1f}%"
    )

print("\n=== P2 Top2: 入场时点对比 ===")
show("A. 9:35 收盘价买", "c935")
show("B. 9:40 收盘价买", "c940")
show("C. 9:45 收盘价买", "c945")
show("D. 实际触发价 px (现网)", "px")

print("\n=== B/C 剔除疑似涨停买不进 (时点涨幅>=9%) ===")
show("B'. 9:40 买 (剔涨停)", "c940", lambda m: m["chg_c940"] < 0.09)
show("C'. 9:45 买 (剔涨停)", "c945", lambda m: m["chg_c945"] < 0.09)

# 触发价 vs 各时点价差
print("\n=== 入场价相对 9:35 收盘价 (负=更便宜) ===")
for col, name in [("c935", "9:35"), ("c940", "9:40"), ("c945", "9:45"), ("px", "触发价")]:
    d = (top2[col] / top2["c935"] - 1).dropna()
    print(f"  {name}: {d.mean()*100:+.2f}%")
