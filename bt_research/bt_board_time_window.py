# -*- coding: utf-8 -*-
"""板块热度时点对比回测 v2 —— 全程向量化。
Q1: 9:35/9:40/9:45/10:00 各时点选出 Top5 板块龙头, 次日表现谁更靠谱?
Q2: 板块热度排名稳定性 —— 早盘 Top5 到后续时点/收盘的留存率。

板块热度定义(与朋友策略评估一致): 板块内 hi_chg 中位排名 + 成交额排名 之和最小 → Top5
龙头: 板块内 chg 最高个股
次日表现: 次日收盘相对买入时点价的收益
"""
import pandas as pd
import numpy as np
import json

SNAP = r"C:\Users\elvisq\Projects\alphapilot\bt_research\_board_snap_cache.parquet"
NEXTDAY = r"C:\Users\elvisq\Projects\alphapilot\bt_research\_nextday_cache.parquet"
IND = r"C:\Users\elvisq\Projects\alphapilot\data\stock_industry_map.json"
TRADES = r"C:\Users\elvisq\Projects\alphapilot\bt_research\_board_snap_trades.parquet"
STAB = r"C:\Users\elvisq\Projects\alphapilot\bt_research\_board_snap_stability.parquet"

SNAP_LABEL = {5: "9:35", 10: "9:40", 15: "9:45", 20: "9:50", 25: "9:55",
              30: "10:00", 60: "10:30", 90: "11:00", 120: "11:30",
              240: "14:00", 330: "15:00"}

print("loading ...", flush=True)
nd = pd.read_parquet(NEXTDAY)
nd = nd.rename(columns={"o_next": "o_next", "h_next": "h_next",
                        "l_next": "l_next", "c_next": "c_next"})
nd["date"] = nd["date"].astype(str)

ind = json.load(open(IND, encoding="utf-8"))
sym2name = {s: info.get("name", "") for s, info in ind.items()}

snap = pd.read_parquet(SNAP)
print("snap rows:", len(snap), flush=True)
snap["date"] = snap["date"].astype(str)

# ── prev_close: 每股前一交易日 15:00(330) 的 close ──
pc = snap[snap["snap_min"] == 330][["symbol", "date", "close"]].sort_values(["symbol", "date"])
pc["prev_close"] = pc.groupby("symbol")["close"].shift(1)
pc = pc[["symbol", "date", "prev_close"]].dropna(subset=["prev_close"])
snap = snap.merge(pc, on=["symbol", "date"], how="left")
snap = snap.dropna(subset=["prev_close"])
snap["chg"] = snap["close"] / snap["prev_close"] - 1
snap["hi_chg"] = snap["high"] / snap["prev_close"] - 1
print("snap w/ prev:", len(snap), flush=True)

# ── 每股每个时点: 板块聚合 ──
# 板块热度: 板块内 hi_chg 中位 排名 + cum_amount 和 排名 → score 越小越热
def board_agg(d):
    g = d.groupby("industry_l3").agg(
        n=("symbol", "count"), med_hi=("hi_chg", "median"),
        amt=("cum_amount", "sum"), top_chg=("chg", "max"),
    )
    return g[g["n"] >= 3]

# 所有 (date, snap_min) 组合的板块聚合, 一次 groupby
g_all = snap.groupby(["date", "snap_min"]).apply(board_agg).reset_index()
g_all["r_hi"] = g_all.groupby(["date", "snap_min"])["med_hi"].rank(ascending=False)
g_all["r_amt"] = g_all.groupby(["date", "snap_min"])["amt"].rank(ascending=False)
g_all["score"] = g_all["r_hi"] + g_all["r_amt"]
print("board-date-snap rows:", len(g_all), flush=True)

# 每个 (date, snap_min) 的 Top5 板块
top5 = g_all.sort_values(["date", "snap_min", "score"]).groupby(["date", "snap_min"]).head(5)
top5 = top5[["date", "snap_min", "industry_l3", "score", "med_hi", "amt"]]
print("top5 rows:", len(top5), flush=True)

# ── 龙头: Top5 板块内 chg 最高个股 ──
t5 = top5.rename(columns={"industry_l3": "l3"})
snap_idx = snap.set_index(["date", "snap_min", "industry_l3"])
# 对每个 (date,snap,l3) 取 chg 最大的行
trades = snap.merge(
    t5[["date", "snap_min", "l3"]], left_on=["date", "snap_min", "industry_l3"],
    right_on=["date", "snap_min", "l3"], how="inner",
)
# 板块内 leader = chg 最高
leader = trades.sort_values("chg", ascending=False).groupby(["date", "snap_min", "l3"]).head(1)
leader = leader[["date", "snap_min", "symbol", "close", "chg"]].rename(columns={"close": "buy_px"})

# 次日
leader = leader.merge(nd, on=["symbol", "date"], how="left")
leader = leader.dropna(subset=["o_next", "c_next"])
leader["name"] = leader["symbol"].map(sym2name)
leader["snap_label"] = leader["snap_min"].map(SNAP_LABEL)
print("leader trades:", len(leader), flush=True)
leader.to_parquet(TRADES)

# ── Q1: 各时点龙头次日表现 ──
print("\n===== Q1: 各时点选出板块龙头的次日表现 (次日收盘 / 买入价) =====", flush=True)
leader["ret_close"] = leader["c_next"] / leader["buy_px"] - 1
leader["ret_open"] = leader["o_next"] / leader["buy_px"] - 1
is_20 = leader["symbol"].str.startswith(("30", "68"))
leader["limit"] = (leader["c_next"] / leader["buy_px"] - 1 >= np.where(is_20, 0.195, 0.095)).astype(int)
# 注意: 涨停率应基于当日涨幅, 这里用买价涨幅近似 (买入价≈时点价, 次日收盘涨幅 >= 板内涨幅)
for mt in sorted(SNAP_LABEL.keys()):
    g = leader[leader["snap_min"] == mt]
    if len(g) < 20:
        continue
    rc = g["ret_close"]
    print(f"  {SNAP_LABEL[mt]:>6}: n={len(g):>4} | 次日收盘 {rc.mean()*100:+5.2f}% | "
          f"中位 {rc.median()*100:+5.2f}% | 胜率 {(rc>0).mean()*100:4.1f}% | "
          f"大涨>7% {(rc>0.07).mean()*100:4.1f}% | 大跌<-5% {(rc<-0.05).mean()*100:4.1f}% | "
          f"次日涨停 {(g['limit']).mean()*100:4.1f}%", flush=True)

# ── Q2: 板块热度排名稳定性 ──
print("\n===== Q2: 板块热度 Top5 排名稳定性 =====", flush=True)
# 对每天, 计算各时点 Top5 板块集合
pivot = top5[["date", "snap_min", "industry_l3"]]
# 展平成 date x snap -> set
sets = {}
for (dt, mt), sub in pivot.groupby(["date", "snap_min"]):
    sets.setdefault(dt, {})[mt] = set(sub["industry_l3"])

stable_rows = []
for dt, by_snap in sets.items():
    if 5 not in by_snap:
        continue
    top5_935 = by_snap[5]
    for mt in sorted(SNAP_LABEL.keys()):
        if mt not in by_snap or mt == 5:
            continue
        overlap = len(top5_935 & by_snap[mt])
        stable_rows.append({"date": dt, "snap_min": mt, "overlap": overlap})

stab = pd.DataFrame(stable_rows)
stab.to_parquet(STAB)
print(f"\n[9:35 Top5 板块在后续时点留存率] (共 {stab['date'].nunique()} 天)", flush=True)
for mt in sorted(SNAP_LABEL.keys()):
    g = stab[stab["snap_min"] == mt]
    if len(g):
        print(f"  {SNAP_LABEL[mt]:>6}: 留存 {g['overlap'].mean():.2f}/5 = {g['overlap'].mean()/5*100:.0f}% | "
              f"n={len(g)}", flush=True)

# 同时: 各时点 Top5 两两重叠 (相邻时点的变化率)
print("\n[相邻时点 Top5 板块重叠率] (衡量排名漂移速度)", flush=True)
dates = sorted(sets.keys())
overlap_pairs = []
for dt in dates:
    by_snap = sets[dt]
    for a, b in zip(sorted(by_snap.keys()), sorted(by_snap.keys())[1:]):
        if a in by_snap and b in by_snap:
            ov = len(by_snap[a] & by_snap[b])
            overlap_pairs.append({"date": dt, "a": a, "b": b, "ov": ov})
op = pd.DataFrame(overlap_pairs)
if len(op):
    for (a, b), sub in op.groupby(["a", "b"]):
        print(f"  {SNAP_LABEL.get(a,'?')}→{SNAP_LABEL.get(b,'?')}: 重叠 {sub['ov'].mean():.2f}/5 "
              f"({sub['ov'].mean()/5*100:.0f}%)", flush=True)
