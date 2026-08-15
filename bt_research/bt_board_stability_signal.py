# -*- coding: utf-8 -*-
"""板块热度"稳定性确认"价值分析。
核心问题: 早盘(9:35)选出的 Top5 板块, 若等确认——即 9:35 与 9:45 都在 Top5——龙头次日表现是否显著更好?
回答: "5分钟够不够?" "要不要等10分钟确认?"
"""
import pandas as pd
import numpy as np
import json

SNAP = r"C:\Users\elvisq\Projects\alphapilot\bt_research\_board_snap_cache.parquet"
NEXTDAY = r"C:\Users\elvisq\Projects\alphapilot\bt_research\_nextday_cache.parquet"
IND = r"C:\Users\elvisq\Projects\alphapilot\data\stock_industry_map.json"
TRADES = r"C:\Users\elvisq\Projects\alphapilot\bt_research\_board_snap_trades.parquet"
OUT = r"C:\Users\elvisq\Projects\alphapilot\bt_research\_board_stability_signal.parquet"

print("loading ...", flush=True)
nd = pd.read_parquet(NEXTDAY)
nd["date"] = nd["date"].astype(str)
ind = json.load(open(IND, encoding="utf-8"))
sym2name = {s: info.get("name", "") for s, info in ind.items()}

snap = pd.read_parquet(SNAP)
snap["date"] = snap["date"].astype(str)

# prev_close 复用
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

# 展平: date -> snap -> set(l3)
sets = {}
for (dt, mt), sub in top5.groupby(["date", "snap_min"]):
    sets.setdefault(dt, {})[mt] = set(sub["industry_l3"])

# 每个 9:35 Top5 板块, 标记是否在 9:45 仍在前5 (稳定) / 掉出 (不稳定)
# 再对每个 (date, l3) 计算 9:35 的龙头及其次日表现
leader = snap[snap["snap_min"] == 5]  # 9:35 快照
# 9:35 Top5 板块 + 稳定标记
rows = []
for dt, by_snap in sets.items():
    if 5 not in by_snap or 15 not in by_snap:
        continue
    top5_935 = by_snap[5]
    top5_945 = by_snap[15]
    for l3 in top5_935:
        d = snap[(snap["date"] == dt) & (snap["snap_min"] == 5) & (snap["industry_l3"] == l3)]
        if d.empty:
            continue
        ld = d.sort_values("chg", ascending=False).iloc[0]
        stable = l3 in top5_945
        rows.append({
            "date": dt, "l3": l3, "stable": stable,
            "symbol": ld["symbol"], "buy_px": ld["close"],
        })

stab_sig = pd.DataFrame(rows)
stab_sig = stab_sig.merge(nd, on=["symbol", "date"], how="left").dropna(subset=["o_next", "c_next"])
stab_sig["ret_close"] = stab_sig["c_next"] / stab_sig["buy_px"] - 1
stab_sig["name"] = stab_sig["symbol"].map(sym2name)
stab_sig.to_parquet(OUT)

print(f"\n样本: {len(stab_sig)}  (稳定={stab_sig['stable'].sum()}, 掉出={(~stab_sig['stable']).sum()})", flush=True)
print("\n===== 9:35 Top5 板块龙头: 按稳定性分组 =====", flush=True)
for st, name in [(True, "稳定(9:45仍在Top5)"), (False, "掉出(9:45不在Top5)")]:
    g = stab_sig[stab_sig["stable"] == st]
    if len(g):
        rc = g["ret_close"]
        print(f"  {name:22s}: n={len(g):>3} | 次日收盘 {rc.mean()*100:+5.2f}% | "
              f"中位 {rc.median()*100:+5.2f}% | 胜率 {(rc>0).mean()*100:4.1f}% | "
              f"大跌<-5% {(rc<-0.05).mean()*100:4.1f}%", flush=True)

# 对比: 全部 9:35 龙头 (不分稳定性)
g_all935 = stab_sig
rc = g_all935["ret_close"]
print(f"  {'全体9:35龙头':22s}: n={len(g_all935):>3} | 次日收盘 {rc.mean()*100:+5.2f}% | "
      f"中位 {rc.median()*100:+5.2f}% | 胜率 {(rc>0).mean()*100:4.1f}% | "
      f"大跌<-5% {(rc<-0.05).mean()*100:4.1f}%", flush=True)

# 再看 9:45 仍在 Top5 的板块龙头 (即"等10分钟"后直接买 9:35 龙头 vs 买 9:45 龙头)
print("\n===== 等确认: 9:45 时点买入 vs 9:35 直接买 =====", flush=True)
# 9:45 的龙头
leader945 = snap[snap["snap_min"] == 15].copy()
l945_rows = []
for dt, by_snap in sets.items():
    if 15 not in by_snap:
        continue
    for l3 in by_snap[15]:
        d = snap[(snap["date"] == dt) & (snap["snap_min"] == 15) & (snap["industry_l3"] == l3)]
        if d.empty:
            continue
        ld = d.sort_values("chg", ascending=False).iloc[0]
        l945_rows.append({"date": dt, "l3": l3, "symbol": ld["symbol"], "buy_px": ld["close"]})
l945 = pd.DataFrame(l945_rows)
l945 = l945.merge(nd, on=["symbol", "date"], how="left").dropna(subset=["o_next", "c_next"])
l945["ret_close"] = l945["c_next"] / l945["buy_px"] - 1
rc = l945["ret_close"]
print(f"  9:45龙头: n={len(l945):>3} | 次日收盘 {rc.mean()*100:+5.2f}% | "
      f"中位 {rc.median()*100:+5.2f}% | 胜率 {(rc>0).mean()*100:4.1f}% | "
      f"大跌<-5% {(rc<-0.05).mean()*100:4.1f}%", flush=True)

# 稳定板块: 9:35买 vs 9:45买 (稳定板块龙头在9:45的价格买入)
print("\n===== 稳定板块: 9:35买 vs 9:45买 =====", flush=True)
stab_sym_dates = set(zip(stab_sig[stab_sig["stable"]]["symbol"], stab_sig[stab_sig["stable"]]["date"]))
l945_stable = l945.copy()
l945_stable["_k"] = list(zip(l945_stable["symbol"], l945_stable["date"]))
l945_stable = l945_stable[l945_stable["_k"].isin(stab_sym_dates)]
# 注意: 9:45 的龙头可能不是 9:35 的龙头, 用 symbol 匹配有偏差; 直接用 l945 全体对比即可
rc = l945_stable["ret_close"]
print(f"  9:45买(全体): n={len(l945):>3} 9:45买(稳定板块): n={len(l945_stable):>3} | "
      f"稳定板块次日 {rc.mean()*100:+5.2f}% 胜率 {(rc>0).mean()*100:4.1f}%", flush=True)
