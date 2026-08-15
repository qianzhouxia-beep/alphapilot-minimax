# -*- coding: utf-8 -*-
"""验证 P2 候选池"板块龙头优先"。
核心: 在 P2 每天同板块出现多只候选时, 选"板块内龙头(9:35涨幅最高)" vs 非龙头, 次日表现?
落地思路(用户): 9:25~9:35 Top2 优先板块龙头 + 池内 + 资金量综合判断。
"""
import pandas as pd
import numpy as np
import json

SNAP = r"C:\Users\elvisq\Projects\alphapilot\bt_research\_board_snap_cache.parquet"
NEXTDAY = r"C:\Users\elvisq\Projects\alphapilot\bt_research\_nextday_cache.parquet"
IND = r"C:\Users\elvisq\Projects\alphapilot\data\stock_industry_map.json"
P2 = r"C:\Users\elvisq\Projects\alphapilot\output\bt_dyn_confirm_long.json"
OUT = r"C:\Users\elvisq\Projects\alphapilot\bt_research\_p2_leader_pool.parquet"

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
pc = pc[["symbol", "date", "prev_close"]].drop_duplicates()
snap = snap.merge(pc, on=["symbol", "date"], how="left").dropna(subset=["prev_close"])
snap["chg"] = snap["close"] / snap["prev_close"] - 1

# P2 候选池 (含未触发)
dd = json.load(open(P2, encoding="utf-8"))
ap = pd.DataFrame(dd["trades"]["P2_dyn_confirm"])
ap["date"] = ap["date"].astype(str)
# 买入价: 触发用 px, 未触发用 p935 近似
ap["buy_px"] = ap["px"].fillna(ap["p935"])
ap = ap.merge(nd, on=["symbol", "date"], how="left").dropna(subset=["c_next"])
ap["ret_close"] = ap["c_next"] / ap["buy_px"] - 1
ap["l3"] = ap["symbol"].map(sym2l3)
ap["name"] = ap["symbol"].map(sym2name)

# 每股 9:35 涨幅 (板块内龙头判定)
d935 = snap[snap["snap_min"] == 5][["date", "symbol", "chg"]].rename(columns={"chg": "chg_935"})
ap = ap.merge(d935, on=["date", "symbol"], how="left")

# 全市场 9:35 涨幅 -> 用于板块内 rank
d935_full = d935.copy()
d935_full["day_rank"] = d935_full.groupby("date")["chg_935"].rank(ascending=False)
ap = ap.merge(d935_full[["date", "symbol", "day_rank"]], on=["date", "symbol"], how="left")

# 板块内龙头判定: 同 (date, l3) 下 chg_935 最高的候选
ap["board_max_chg"] = ap.groupby(["date", "l3"])["chg_935"].transform("max")
ap["is_board_leader"] = (ap["chg_935"] == ap["board_max_chg"]).astype(int)
# 板块内只有一只票的, 自动是龙头
ap["board_n"] = ap.groupby(["date", "l3"])["symbol"].transform("count")
ap["multi"] = ap["board_n"] >= 2  # 同板块有多个候选

print(f"P2 候选池: {len(ap)} (触发{ap['trigger'].sum()}, 未触发{(~ap['trigger']).sum()})", flush=True)
print(f"同板块多候选的: {ap['multi'].sum()} ({(ap['multi'].mean()*100):.0f}%)", flush=True)
ap.to_parquet(OUT)

def show(tag, s):
    if len(s) == 0:
        print(f"  {tag:36s}: n=0", flush=True)
        return
    print(f"  {tag:36s}: n={len(s):>4} | 次日收盘 {s.mean()*100:+5.2f}% | "
          f"中位 {s.median()*100:+5.2f}% | 胜率 {(s>0).mean()*100:4.1f}% | "
          f"大涨>7% {(s>0.07).mean()*100:4.1f}% | 大跌<-5% {(s<-0.05).mean()*100:4.1f}%", flush=True)

print("\n===== 1. 全体候选: 板块龙头 vs 非龙头 =====", flush=True)
show("全体候选", ap["ret_close"])
show("板块龙头候选", ap[ap["is_board_leader"] == 1]["ret_close"])
show("非龙头候选", ap[ap["is_board_leader"] == 0]["ret_close"])

print("\n===== 2. 同板块多候选时: 龙头 vs 非龙头 =====", flush=True)
multi = ap[ap["multi"]]
show("多候选中的龙头", multi[multi["is_board_leader"] == 1]["ret_close"])
show("多候选中的非龙头", multi[multi["is_board_leader"] == 0]["ret_close"])

print("\n===== 3. 只看触发样本 (真实执行口径) =====", flush=True)
trg = ap[ap["trigger"] == True]
show("触发-板块龙头", trg[trg["is_board_leader"] == 1]["ret_close"])
show("触发-非龙头", trg[trg["is_board_leader"] == 0]["ret_close"])

print("\n===== 4. 龙头优先落地效果模拟 =====", flush=True)
# 模拟: 每天同板块多候选时只取龙头 (去掉非龙头), 看候选池整体收益变化
# 对照组: 每天随机保留一个 (维持数量)
rng = np.random.default_rng(42)
sim = []
for dt, day in ap.groupby("date"):
    # 全候选均值
    sim.append({"date": dt, "all": day["ret_close"].mean()})
    # 龙头优先: 每个板块只留龙头
    leaders = day[day["is_board_leader"] == 1]
    if len(leaders):
        sim.append({"date": dt, "leader_only": leaders["ret_close"].mean(), "n_leader": len(leaders)})
sdf = pd.DataFrame(sim)
show("每日全候选均值", sdf["all"])
if "leader_only" in sdf:
    show("每日龙头优先均值", sdf["leader_only"].dropna())
print(f"  (龙头优先时每天平均候选数: {sdf['n_leader'].mean():.1f})", flush=True)

# ── 5. 龙头 + 资金量 双条件 (用户落地思路) ──
print("\n===== 5. 龙头 + 板块9:45热度 (用户: 板块龙头+池内+资金量) =====", flush=True)
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
t45 = set(zip(top5[top5["snap_min"] == 15]["date"], top5[top5["snap_min"] == 15]["industry_l3"]))
ap["board_hot45"] = [ (r.date, r.l3) in t45 for r in ap.itertuples() ]

show("龙头+板块9:45热门", ap[(ap["is_board_leader"] == 1) & (ap["board_hot45"])]["ret_close"])
show("非龙头+板块9:45热门", ap[(ap["is_board_leader"] == 0) & (ap["board_hot45"])]["ret_close"])
show("龙头+板块非热门", ap[(ap["is_board_leader"] == 1) & (~ap["board_hot45"])]["ret_close"])

print("\n组合样本数:", flush=True)
print(ap.groupby(["is_board_leader", "board_hot45"]).size().to_string(), flush=True)
