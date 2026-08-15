# -*- coding: utf-8 -*-
"""核心研究: 9:30~9:45 确认窗口会不会 miss 强势股? + P2 叠加板块热度稳定性因子。

回答用户问题:
  1. 等确认(9:45)会错过强势股吗?
     -> 把 9:45 Top5 板块分为: 稳定(9:35也在) / 新晋(9:35不在,9:45进) / 掉出(9:35在,9:45不在)
     -> 新晋板块龙头 = "后发强势股", 若表现好则确认窗口不 miss, 反而抓到真强势
  2. AlphaPilot P2 叠加"板块热度稳定性"因子的价值
     -> P2 买入股票的板块在 9:35/9:45 的 Top5 状态 -> 分组比较次日表现
"""
import pandas as pd
import numpy as np
import json

SNAP = r"C:\Users\elvisq\Projects\alphapilot\bt_research\_board_snap_cache.parquet"
NEXTDAY = r"C:\Users\elvisq\Projects\alphapilot\bt_research\_nextday_cache.parquet"
IND = r"C:\Users\elvisq\Projects\alphapilot\data\stock_industry_map.json"
P2 = r"C:\Users\elvisq\Projects\alphapilot\output\bt_dyn_confirm_long.json"
OUT_DIR = r"C:\Users\elvisq\Projects\alphapilot\bt_research"

print("loading ...", flush=True)
nd = pd.read_parquet(NEXTDAY)
nd["date"] = nd["date"].astype(str)
ind = json.load(open(IND, encoding="utf-8"))
sym2name = {s: info.get("name", "") for s, info in ind.items()}

snap = pd.read_parquet(SNAP)
snap["date"] = snap["date"].astype(str)
pc = snap[snap["snap_min"] == 330][["symbol", "date", "close"]].sort_values(["symbol", "date"])
pc["prev_close"] = pc.groupby("symbol")["close"].shift(1)
pc = pc[["symbol", "date", "prev_close"]].dropna()
snap = snap.merge(pc, on=["symbol", "date"], how="left").dropna(subset=["prev_close"])
snap["chg"] = snap["close"] / snap["prev_close"] - 1
snap["hi_chg"] = snap["high"] / snap["prev_close"] - 1

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
print("top5:", len(top5), flush=True)

# 每股每日各时点的 chg (供龙头)
px = snap[["date", "symbol", "snap_min", "industry_l3", "chg", "close"]].copy()

# ═══════════════════════════════════════════
# PART 1: 9:45 Top5 板块三分类龙头
# ═══════════════════════════════════════════
t35 = set(zip(top5[top5["snap_min"] == 5]["date"], top5[top5["snap_min"] == 5]["industry_l3"]))
t45 = set(zip(top5[top5["snap_min"] == 15]["date"], top5[top5["snap_min"] == 15]["industry_l3"]))

rows = []
for (dt, l3) in sorted(t45):
    d45 = px[(px["date"] == dt) & (px["snap_min"] == 15) & (px["industry_l3"] == l3)]
    if d45.empty:
        continue
    ld = d45.sort_values("chg", ascending=False).iloc[0]
    if (dt, l3) in t35:
        cat = "稳定(9:35+9:45都在Top5)"
    else:
        cat = "新晋(9:35不在,9:45才进Top5)"
    rows.append({"date": dt, "l3": l3, "cat": cat,
                 "symbol": ld["symbol"], "buy_px": ld["close"]})

df1 = pd.DataFrame(rows)
df1 = df1.merge(nd, on=["symbol", "date"], how="left").dropna(subset=["o_next", "c_next"])
df1["ret_close"] = df1["c_next"] / df1["buy_px"] - 1
df1["name"] = df1["symbol"].map(sym2name)
df1.to_parquet(f"{OUT_DIR}\\_board_945_cat.parquet")

print("\n===== PART 1: 9:45 Top5 板块龙头三分类 =====", flush=True)
for cat, sub in df1.groupby("cat"):
    rc = sub["ret_close"]
    print(f"  {cat:28s}: n={len(sub):>3} | 次日收盘 {rc.mean()*100:+5.2f}% | "
          f"中位 {rc.median()*100:+5.2f}% | 胜率 {(rc>0).mean()*100:4.1f}% | "
          f"大涨>7% {(rc>0.07).mean()*100:4.1f}% | 大跌<-5% {(rc<-0.05).mean()*100:4.1f}%", flush=True)

# 对比: 9:35 直接选 (含会掉出的假热点)
rows935 = []
for (dt, l3) in sorted(t35 | (set())):
    pass
# 9:35 全体 Top5 龙头 (含稳定+掉出)
t35_rows = []
for (dt, l3) in sorted(t35):
    d = px[(px["date"] == dt) & (px["snap_min"] == 5) & (px["industry_l3"] == l3)]
    if d.empty:
        continue
    ld = d.sort_values("chg", ascending=False).iloc[0]
    t35_rows.append({"date": dt, "symbol": ld["symbol"], "buy_px": ld["close"]})
df935 = pd.DataFrame(t35_rows)
df935 = df935.merge(nd, on=["symbol", "date"], how="left").dropna(subset=["c_next"])
df935["ret_close"] = df935["c_next"] / df935["buy_px"] - 1
rc = df935["ret_close"]
print(f"  {'9:35全体Top5龙头(含假热点)':28s}: n={len(df935):>3} | 次日收盘 {rc.mean()*100:+5.2f}% | "
      f"中位 {rc.median()*100:+5.2f}% | 胜率 {(rc>0).mean()*100:4.1f}% | 大跌<-5% {(rc<-0.05).mean()*100:4.1f}%", flush=True)

# 确认窗口的价值: 新晋 vs 掉出 (9:35 错过/选错的部分)
print("\n[确认窗口的净效应]", flush=True)
drop_rows = []
for (dt, l3) in sorted(t35 - t45):
    d = px[(px["date"] == dt) & (px["snap_min"] == 5) & (px["industry_l3"] == l3)]
    if d.empty:
        continue
    ld = d.sort_values("chg", ascending=False).iloc[0]
    drop_rows.append({"date": dt, "symbol": ld["symbol"], "buy_px": ld["close"]})
dfd = pd.DataFrame(drop_rows)
dfd = dfd.merge(nd, on=["symbol", "date"], how="left").dropna(subset=["c_next"])
dfd["ret_close"] = dfd["c_next"] / dfd["buy_px"] - 1
rc = dfd["ret_close"]
print(f"  {'掉出(9:35在,9:45不在)':28s}: n={len(dfd):>3} | 次日收盘 {rc.mean()*100:+5.2f}% | "
      f"胜率 {(rc>0).mean()*100:4.1f}% | 大跌<-5% {(rc<-0.05).mean()*100:4.1f}%", flush=True)
print(f"  掉出数量 {len(dfd)} vs 新晋数量 {len(df1[df1['cat'].str.startswith('新晋')])}", flush=True)

# ═══════════════════════════════════════════
# PART 2: AlphaPilot P2 叠加板块热度稳定性因子
# ═══════════════════════════════════════════
print("\n\n===== PART 2: P2 买入股票所在板块的热度状态 =====", flush=True)
dd = json.load(open(P2, encoding="utf-8"))
trig = [x for x in dd["trades"]["P2_dyn_confirm"] if x.get("trigger")]
ap = pd.DataFrame(trig)
ap["date"] = ap["date"].astype(str)
ap["buy_px"] = ap["px"]
ap = ap.merge(nd, on=["symbol", "date"], how="left").dropna(subset=["c_next"])
ap["ret_close"] = ap["c_next"] / ap["buy_px"] - 1
ap["l3"] = ap["symbol"].map({s: info.get("industry_l3") for s, info in ind.items()})
ap["name"] = ap["symbol"].map(sym2name)

# 板块状态: 该股票所在板块在 9:35/9:45 的 Top5 状态
state_map = {}
for (dt, l3) in t35 & t45:
    state_map[(dt, l3)] = "稳定(Top5+Top5)"
for (dt, l3) in t35 - t45:
    state_map[(dt, l3)] = "掉出(Top5-非Top5)"
for (dt, l3) in t45 - t35:
    state_map[(dt, l3)] = "新晋(非Top5+Top5)"

ap["board_state"] = ap.apply(lambda r: state_map.get((r["date"], r["l3"]), "非Top5"), axis=1)
ap.to_parquet(f"{OUT_DIR}\\_p2_board_state.parquet")

print(f"\nP2 样本总数: {len(ap)}", flush=True)
print(f"板块状态分布:", flush=True)
print(ap["board_state"].value_counts().to_string(), flush=True)

print("\n[P2 按板块热度状态分组]", flush=True)
for st in ["稳定(Top5+Top5)", "新晋(非Top5+Top5)", "掉出(Top5-非Top5)", "非Top5"]:
    g = ap[ap["board_state"] == st]
    if len(g) < 5:
        continue
    rc = g["ret_close"]
    print(f"  {st:22s}: n={len(g):>3} | 次日收盘 {rc.mean()*100:+5.2f}% | "
          f"中位 {rc.median()*100:+5.2f}% | 胜率 {(rc>0).mean()*100:4.1f}% | "
          f"大跌<-5% {(rc<-0.05).mean()*100:4.1f}%", flush=True)

# 加分因子效果: 稳定板块的 P2 票 vs 全部
g_stable = ap[ap["board_state"] == "稳定(Top5+Top5)"]
g_rest = ap[ap["board_state"] != "稳定(Top5+Top5)"]
if len(g_stable):
    rc = g_stable["ret_close"]
    print(f"\n[因子效果] 稳定板块P2票 vs 其余:", flush=True)
    print(f"  稳定板块: n={len(g_stable)} 次日 {rc.mean()*100:+.2f}% 胜率 {(rc>0).mean()*100:.1f}% 大跌 {(rc<-0.05).mean()*100:.1f}%", flush=True)
    rc = g_rest["ret_close"]
    print(f"  其余:     n={len(g_rest)} 次日 {rc.mean()*100:+.2f}% 胜率 {(rc>0).mean()*100:.1f}% 大跌 {(rc<-0.05).mean()*100:.1f}%", flush=True)
