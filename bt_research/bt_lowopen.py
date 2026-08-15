# -*- coding: utf-8 -*-
"""深挖 P2 低开组 (9:35 涨幅 <0%)。

核心问题:
  1. 低开组的特征: score / 开盘gap / 9:35位置 / 板块分布
  2. 为什么强? 低开=清洗 还是 低吸入场?
  3. 是全市场所有低开票都强, 还是只有 P2 选出的低开票强 (模型起作用)?
  4. 能否提炼: 低开 + 什么条件 -> 更强?
"""
import pandas as pd
import numpy as np
import json

SNAP = r"C:\Users\elvisq\Projects\alphapilot\bt_research\_board_snap_cache.parquet"
NEXTDAY = r"C:\Users\elvisq\Projects\alphapilot\bt_research\_nextday_cache.parquet"
IND = r"C:\Users\elvisq\Projects\alphapilot\data\stock_industry_map.json"
P2 = r"C:\Users\elvisq\Projects\alphapilot\output\bt_dyn_confirm_long.json"
OUT = r"C:\Users\elvisq\Projects\alphapilot\bt_research\_p2_lowopen.parquet"

print("loading ...", flush=True)
nd = pd.read_parquet(NEXTDAY)
nd["date"] = nd["date"].astype(str)
ind = json.load(open(IND, encoding="utf-8"))
sym2name = {s: info.get("name", "") for s, info in ind.items()}
sym2l3 = {s: info.get("industry_l3") for s, info in ind.items()}

snap = pd.read_parquet(SNAP)
snap["date"] = snap["date"].astype(str)
pc = snap[snap["snap_min"] == 330][["symbol", "date", "close"]].sort_values(["symbol", "date"])
pc["prev_close"] = pc.groupby("symbol")["close"].shift(1)
pc = pc[["symbol", "date", "prev_close"]].dropna()
snap = snap.merge(pc, on=["symbol", "date"], how="left").dropna(subset=["prev_close"])
snap["chg"] = snap["close"] / snap["prev_close"] - 1

# P2 触发样本
dd = json.load(open(P2, encoding="utf-8"))
trig = [x for x in dd["trades"]["P2_dyn_confirm"] if x.get("trigger")]
ap = pd.DataFrame(trig)
ap["date"] = ap["date"].astype(str)
ap["buy_px"] = ap["px"]
ap = ap.merge(nd, on=["symbol", "date"], how="left").dropna(subset=["c_next"])
ap["ret_close"] = ap["c_next"] / ap["buy_px"] - 1
ap["l3"] = ap["symbol"].map(sym2l3)
ap["name"] = ap["symbol"].map(sym2name)

# 9:35 状态
d935 = snap[snap["snap_min"] == 5][["date", "symbol", "chg"]].rename(columns={"chg": "chg_935"})
ap = ap.merge(d935, on=["date", "symbol"], how="left")
d935["day_rank"] = d935.groupby("date")["chg_935"].rank(ascending=False)
ap = ap.merge(d935[["date", "symbol", "day_rank"]], on=["date", "symbol"], how="left")

# 开盘 gap (用 prev_close 算)
ap = ap.merge(snap[snap["snap_min"] == 330][["date", "symbol", "prev_close"]].drop_duplicates(),
              on=["date", "symbol"], how="left")
ap["gap_open"] = ap["open_px"] / ap["prev_close"] - 1

print("P2 columns:", ap.columns.tolist(), flush=True)
ap.to_parquet(OUT)

low = ap[ap["chg_935"] < 0]
flat = ap[(ap["chg_935"] >= 0) & (ap["chg_935"] < 0.03)]
print(f"\n低开组 n={len(low)} | 平开组 n={len(flat)}", flush=True)

# ── 1. 低开组特征 ──
print("\n===== 1. 低开组特征 =====", flush=True)
print(f"  开盘gap: 中位 {low['gap_open'].median()*100:+.2f}%, 均值 {low['gap_open'].mean()*100:+.2f}%", flush=True)
print(f"  score:   中位 {low['score'].median():.4f}, 平开组 {flat['score'].median():.4f}", flush=True)
print(f"  9:35排名: 中位 #{low['day_rank'].median():.0f}, 平开组 #{flat['day_rank'].median():.0f}", flush=True)

# 低开组 vs 平开组 vs 全市场所有低开票 (模型 vs 全市场)
print("\n===== 2. P2低开 vs P2平开 vs 全市场低开票 =====", flush=True)
def show(tag, s):
    print(f"  {tag:32s}: n={len(s):>4} | 次日收盘 {s.mean()*100:+5.2f}% | "
          f"中位 {s.median()*100:+5.2f}% | 胜率 {(s>0).mean()*100:4.1f}% | "
          f"大涨>7% {(s>0.07).mean()*100:4.1f}% | 大跌<-5% {(s<-0.05).mean()*100:4.1f}%", flush=True)
show("P2 低开组", low["ret_close"])
show("P2 平开组", flat["ret_close"])
show("P2 全体", ap["ret_close"])

# 全市场低开票的次日: 所有 9:35 <0% 的票
all_low = snap[(snap["snap_min"] == 5) & (snap["chg"] < 0)].merge(
    nd, on=["symbol", "date"], how="left").dropna(subset=["c_next"])
all_low["ret_close"] = all_low["c_next"] / all_low["close"] - 1
show("全市场所有9:35低开票", all_low["ret_close"])
# 全市场低开+次日大涨分布 (说明全市场低开票并不普遍强)
all_flat = snap[(snap["snap_min"] == 5) & (snap["chg"] >= 0)].merge(
    nd, on=["symbol", "date"], how="left").dropna(subset=["c_next"])
all_flat["ret_close"] = all_flat["c_next"] / all_flat["close"] - 1
show("全市场所有9:35平开/高开票", all_flat["ret_close"])

# ── 3. 低开组的板块/资金特征 ──
print("\n===== 3. 低开组按板块热度状态 =====", flush=True)
def board_agg(d):
    g = d.groupby("industry_l3").agg(
        n=("symbol", "count"), med_hi=("hi_chg", "median"), amt=("cum_amount", "sum"))
    return g[g["n"] >= 3]

snap["hi_chg"] = snap["high"] / snap["prev_close"] - 1
g_all = snap.groupby(["date", "snap_min"]).apply(board_agg).reset_index()
g_all["r_hi"] = g_all.groupby(["date", "snap_min"])["med_hi"].rank(ascending=False)
g_all["r_amt"] = g_all.groupby(["date", "snap_min"])["amt"].rank(ascending=False)
g_all["score"] = g_all["r_hi"] + g_all["r_amt"]
top5 = g_all.sort_values(["date", "snap_min", "score"]).groupby(["date", "snap_min"]).head(5)
top5 = top5[["date", "snap_min", "industry_l3"]]
t45 = set(zip(top5[top5["snap_min"] == 15]["date"], top5[top5["snap_min"] == 15]["industry_l3"]))
low["board_hot45"] = [ (r.date, r.l3) in t45 for r in low.itertuples() ]
for h in [True, False]:
    g = low[low["board_hot45"] == h]
    show(f"P2低开[板块9:45热门={h}]", g["ret_close"])

# 低开组 top l3
print("\n低开组板块分布:", low["l3"].value_counts().head(8).to_string(), flush=True)
print("\n低开组 top 样本 (次日收益):", flush=True)
print(low.nlargest(10, "ret_close")[["date", "name", "gap_open", "ret_close", "score"]].to_string(), flush=True)
