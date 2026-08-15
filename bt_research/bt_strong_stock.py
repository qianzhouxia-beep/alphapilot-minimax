# -*- coding: utf-8 -*-
"""抓强势股的正确定义研究:
板块热度Top5选龙头 miss 了真正的强势股吗? 强势股到底在哪?

用户问题: "9:30~9:45确认窗会不会错过强势股? 真正要研究的是如何抓板块龙头/强势股"

核心对比:
  A) 板块热度 Top5 龙头 (板块逻辑, 已证明弱: +0.05~0.55%)
  B) P2 选出的票 (个股逻辑, +1.04%) - 它们在哪? 什么特征?
  C) 真正的"强势股": 开盘 30 分钟内涨幅>8% 且次日表现 (纯个股强势)
"""
import pandas as pd
import numpy as np
import json

SNAP = r"C:\Users\elvisq\Projects\alphapilot\bt_research\_board_snap_cache.parquet"
NEXTDAY = r"C:\Users\elvisq\Projects\alphapilot\bt_research\_nextday_cache.parquet"
IND = r"C:\Users\elvisq\Projects\alphapilot\data\stock_industry_map.json"
P2 = r"C:\Users\elvisq\Projects\alphapilot\output\bt_dyn_confirm_long.json"

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
snap["hi_chg"] = snap["high"] / snap["prev_close"] - 1

# ═══════════════════════════════════════════
# PART 1: "个股强势" 定义 -> 9:35 涨幅前N的票, 次日表现
# (不经板块过滤的纯个股强势)
# ═══════════════════════════════════════════
print("===== PART 1: 纯个股强势 (9:35涨幅前N, 不经板块过滤) =====", flush=True)
d935 = snap[snap["snap_min"] == 5]
# 只保留有次日数据的
d935 = d935.merge(nd, on=["symbol", "date"], how="left").dropna(subset=["o_next", "c_next"])
d935["ret_close"] = d935["c_next"] / d935["close"] - 1

# 按日期分组, 每日期内按 chg 排名
d935["rank_in_day"] = d935.groupby("date")["chg"].rank(ascending=False)

for n, label in [(20, "9:35全市场涨幅前20"), (50, "9:35全市场涨幅前50"), (100, "9:35全市场涨幅前100")]:
    g = d935[d935["rank_in_day"] <= n]
    rc = g["ret_close"]
    print(f"  {label}: n={len(g):>4} | 次日收盘 {rc.mean()*100:+5.2f}% | "
          f"中位 {rc.median()*100:+5.2f}% | 胜率 {(rc>0).mean()*100:4.1f}% | "
          f"大涨>7% {(rc>0.07).mean()*100:4.1f}% | 大跌<-5% {(rc<-0.05).mean()*100:4.1f}%", flush=True)

# 涨幅 >=8% (朋友策略触发口径)
g8 = d935[d935["chg"] >= 0.08]
rc = g8["ret_close"]
print(f"  {'9:35涨幅>=8%(朋友触发口径)':20s}: n={len(g8):>4} | 次日收盘 {rc.mean()*100:+5.2f}% | "
      f"中位 {rc.median()*100:+5.2f}% | 胜率 {(rc>0).mean()*100:4.1f}% | 大跌<-5% {(rc<-0.05).mean()*100:4.1f}%", flush=True)

# ═══════════════════════════════════════════
# PART 2: 板块热度 Top5 龙头 vs 板块内其他强势股
# 热门板块里, "时点涨幅最高"是不是最好的? 还是次龙头?
# ═══════════════════════════════════════════
print("\n===== PART 2: 热门板块内, 龙头 vs 次龙头 vs 其他 =====", flush=True)
def board_agg(d):
    g = d.groupby("industry_l3").agg(
        n=("symbol", "count"), med_hi=("hi_chg", "median"), amt=("cum_amount", "sum"))
    return g[g["n"] >= 3]

g_all = snap.groupby(["date", "snap_min"]).apply(board_agg).reset_index()
g_all["r_hi"] = g_all.groupby(["date", "snap_min"])["med_hi"].rank(ascending=False)
g_all["r_amt"] = g_all.groupby(["date", "snap_min"])["amt"].rank(ascending=False)
g_all["score"] = g_all["r_hi"] + g_all["r_amt"]
top5 = g_all.sort_values(["date", "snap_min", "score"]).groupby(["date", "snap_min"]).head(5)
top5 = top5[["date", "snap_min", "industry_l3"]]
t45 = set(zip(top5[top5["snap_min"] == 15]["date"], top5[top5["snap_min"] == 15]["industry_l3"]))

# 9:45 Top5 板块内的成分股, 按 chg 排序 -> 第1(龙头)/第2/第3/其余
rows = []
for (dt, l3) in sorted(t45):
    d = snap[(snap["date"] == dt) & (snap["snap_min"] == 15) & (snap["industry_l3"] == l3)]
    if len(d) < 3:
        continue
    d = d.sort_values("chg", ascending=False)
    for i, (_, r) in enumerate(d.iterrows()):
        rank = "龙头(第1)" if i == 0 else ("次龙(第2)" if i == 1 else ("第3" if i == 2 else "第4+" ))
        if rank == "第4+":
            continue
        rows.append({"date": dt, "l3": l3, "rank": rank,
                     "symbol": r["symbol"], "buy_px": r["close"]})
df = pd.DataFrame(rows)
df = df.merge(nd, on=["symbol", "date"], how="left").dropna(subset=["c_next"])
df["ret_close"] = df["c_next"] / df["buy_px"] - 1
df["name"] = df["symbol"].map(sym2name)
print(f"热门板块成分股样本: {len(df)}", flush=True)
for rank, sub in df.groupby("rank"):
    rc = sub["ret_close"]
    print(f"  {rank:10s}: n={len(sub):>4} | 次日收盘 {rc.mean()*100:+5.2f}% | "
          f"胜率 {(rc>0).mean()*100:4.1f}% | 大涨>7% {(rc>0.07).mean()*100:4.1f}% | 大跌<-5% {(rc<-0.05).mean()*100:4.1f}%", flush=True)

# ═══════════════════════════════════════════
# PART 3: P2 选出的票, 在 9:35 的涨幅排名位置
# (P2 是否本身就是"强势股"?)
# ═══════════════════════════════════════════
print("\n===== PART 3: P2 选出的票 9:35 时的位置 =====", flush=True)
dd = json.load(open(P2, encoding="utf-8"))
trig = [x for x in dd["trades"]["P2_dyn_confirm"] if x.get("trigger")]
ap = pd.DataFrame(trig)
ap["date"] = ap["date"].astype(str)
ap["buy_px"] = ap["px"]
ap = ap.merge(nd, on=["symbol", "date"], how="left").dropna(subset=["c_next"])
ap["ret_close"] = ap["c_next"] / ap["buy_px"] - 1
ap["l3"] = ap["symbol"].map(sym2l3)

# P2 票在 9:35 的涨幅
d935_ = snap[snap["snap_min"] == 5][["date", "symbol", "chg"]].rename(columns={"chg": "chg_935"})
ap = ap.merge(d935_, on=["date", "symbol"], how="left")
# 当日全市场排名
d935_rank = d935_.copy()
d935_rank["day_rank"] = d935_rank.groupby("date")["chg_935"].rank(ascending=False)
ap = ap.merge(d935_rank[["date", "symbol", "day_rank"]], on=["date", "symbol"], how="left")
print(f"P2 票 9:35 涨幅分布: 中位 {ap['chg_935'].median()*100:+.2f}%, "
      f"均值 {ap['chg_935'].mean()*100:+.2f}%, 涨幅>5%占 {(ap['chg_935']>0.05).mean()*100:.1f}%", flush=True)
print(f"P2 票 9:35 全市场排名: 中位 #{ap['day_rank'].median():.0f}, "
      f"前100占 {(ap['day_rank']<=100).mean()*100:.1f}%, 前200占 {(ap['day_rank']<=200).mean()*100:.1f}%", flush=True)

# P2 票的次日表现 vs 涨幅分位
print("\n[P2 票按 9:35 涨幅分组]", flush=True)
ap["grp"] = pd.cut(ap["chg_935"], [-1, 0, 0.03, 0.05, 0.08, 1], labels=["<0%", "0~3%", "3~5%", "5~8%", ">8%"])
for grp, sub in ap.groupby("grp", observed=True):
    rc = sub["ret_close"]
    print(f"  9:35涨幅 {grp}: n={len(sub):>3} | 次日收盘 {rc.mean()*100:+5.2f}% | "
          f"胜率 {(rc>0).mean()*100:4.1f}% | 大涨>7% {(rc>0.07).mean()*100:4.1f}% | 大跌<-5% {(rc<-0.05).mean()*100:4.1f}%", flush=True)
