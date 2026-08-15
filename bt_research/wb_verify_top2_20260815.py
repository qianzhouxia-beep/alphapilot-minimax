# -*- coding: utf-8 -*-
"""
WB 独立交叉验证: P2 Top2 时点研究 + 混合执行策略 (2026-08-15 同步稿)
==========================================================
独立实现路径: 仅共享 Cursor 的原始数据(bt_dyn_confirm_long.json /
_board_snap_cache.parquet / _nextday_cache.parquet), 代码逻辑全部重写.

待复现数字:
  ① 时点对比: 9:35 close +4.53% / 9:40 +4.05% / 9:45 +3.94% (胜率 70.7/70.1/69.4)
  ② 出票延迟: o940 vs c935 平均差 ≈ +0.01%
  ③ T1 触发样本: 9:36/9:37 市价买 +6.34% vs 触发价 +3.10% (贵 3.15%)
  ④ T2 组合: 全买 +94.8pp vs 现网动态确认 +150.0pp (未触发样本市价买 -2.26%)
  ⑤ 触发特征: 9:35 涨幅<0% 触发率 80% / >4% 仅 3.4%; score 四分位触发率无差
  ⑥ 混合策略: M3% 累计 +261.9pp vs 现网 +150.0pp (+112pp), 阈值扫描全跑赢
"""
import json
import numpy as np
import pandas as pd

BASE = r"C:\Users\elvisq\Projects\alphapilot"
SNAP = f"{BASE}\\bt_research\\_board_snap_cache.parquet"
NEXT = f"{BASE}\\bt_research\\_nextday_cache.parquet"
P2J = f"{BASE}\\output\\bt_dyn_confirm_long.json"

# ---------- 1. 加载原始数据 ----------
snap = pd.read_parquet(SNAP)
nd = pd.read_parquet(NEXT)
dd = json.load(open(P2J, encoding="utf-8"))
for c in ("date",):
    snap[c] = snap[c].astype(str)
    nd[c] = nd[c].astype(str)

trades_p0 = pd.DataFrame(dd["trades"]["P0_direct"])   # 830: 每日合成 Top10
trades_p2 = pd.DataFrame(dd["trades"]["P2_dyn_confirm"])
for dfx in (trades_p0, trades_p2):
    dfx["date"] = dfx["date"].astype(str)

# ---------- 2. 独立计算 前收 / 9:35涨幅 ----------
# 前收 = 前一日 15:00 (snap_min=330) close
pc = (snap[snap["snap_min"] == 330][["symbol", "date", "close"]]
      .sort_values(["symbol", "date"]))
pc["prev_close"] = pc.groupby("symbol")["close"].shift(1)
pc = pc[["symbol", "date", "prev_close"]].dropna(subset=["prev_close"])

# 各时点价格快照(独立 join)
px935 = snap[snap["snap_min"] == 5][["date", "symbol", "close"]].rename(columns={"close": "c935"})
px940o = snap[snap["snap_min"] == 10][["date", "symbol", "open"]].rename(columns={"open": "o940"})
px940c = snap[snap["snap_min"] == 10][["date", "symbol", "close"]].rename(columns={"close": "c940"})
px945c = snap[snap["snap_min"] == 15][["date", "symbol", "close"]].rename(columns={"close": "c945"})

# ---------- 3. 涨停线 ----------
def limit_pct(sym: str) -> float:
    if sym.startswith(("300", "301", "688")):
        return 0.20
    if sym.startswith(("8", "4")):
        return 0.30
    return 0.10

# ---------- 4. 构建分析表: P0 信号 + P2 触发 + 次日 ----------
ap = trades_p0.merge(
    trades_p2[["date", "symbol", "trigger", "px", "tmin"]].rename(
        columns={"trigger": "trg_p2", "px": "px_p2", "tmin": "tmin_p2"}),
    on=["date", "symbol"], how="left")
ap = ap.merge(nd, on=["symbol", "date"], how="left").dropna(subset=["c_next"])
ap = ap.merge(pc, on=["symbol", "date"], how="left").dropna(subset=["prev_close"])
for d_ in (px935, px940o, px940c, px945c):
    ap = ap.merge(d_, on=["date", "symbol"], how="left")

ap["chg_935"] = ap["c935"] / ap["prev_close"] - 1.0
ap["lim"] = ap["symbol"].apply(limit_pct)
ap["near_limit"] = ap["chg_935"] >= ap["lim"] * 0.97
ap = ap[~ap["near_limit"]].copy()

# 每日 Top2 (score 降序) —— 独立选取
ap = ap.sort_values(["date", "score"], ascending=[True, False])
top2 = ap.groupby("date").head(2).copy()
print(f"Top2 样本: {len(top2)} 个 ({top2['date'].nunique()} 天), 剔除涨停 {ap['near_limit'].sum()}")

# ---------- 5. 收益定义 (卖出=次日收盘) ----------
top2["ret_c935"] = top2["c_next"] / top2["c935"] - 1.0
top2["ret_o940"] = top2["c_next"] / top2["o940"] - 1.0
top2["ret_c940"] = top2["c_next"] / top2["c940"] - 1.0
top2["ret_c945"] = top2["c_next"] / top2["c945"] - 1.0
top2["ret_p2"] = np.where(top2["trg_p2"].astype(bool),
                          top2["c_next"] / top2["px_p2"] - 1.0, np.nan)
top2["o940_valid"] = top2["o940"].notna()

def stat(tag, r):
    if len(r) == 0:
        print(f"  {tag:26s}: n=0")
        return
    print(f"  {tag:26s}: n={len(r):3d} | 次日收盘 {r.mean()*100:+6.2f}% | 胜率 {(r>0).mean()*100:4.1f}% "
          f"| 大涨>7% {(r>0.07).mean()*100:4.1f}% | 大跌<-5% {(r<-0.05).mean()*100:4.1f}%")

print("\n===== ① 时点对比 (有 o940 的样本) =====")
ok = top2[top2["o940_valid"]]
stat("9:35 close 买", ok["ret_c935"])
stat("9:40 close 买", ok["ret_c940"])
stat("9:45 close 买", ok["ret_c945"])
stat("触发价买 (现网)", ok["ret_p2"])

print("\n===== ② 出票延迟成本 =====")
print(f"  o940 vs c935 平均: {((ok['o940']/ok['c935']-1).mean()*100):+.2f}%")

print("\n===== ③ T1 触发样本口径 =====")
trg = ok[ok["trg_p2"].astype(bool)]
stat("触发样本 9:36/9:37买(o940)", trg["ret_o940"])
stat("触发样本 触发价买", trg["ret_p2"])
print(f"  触发价 vs o940 平均: {((trg['px_p2']/trg['o940']-1).mean()*100):+.2f}%")

print("\n===== ④ T2 组合口径 (每日 Top2) =====")
comb = {}
comb["A 9:36/9:37市价全买"] = top2.groupby("date")["ret_o940"].mean()
comb["B 触发才买(空仓)"] = top2.groupby("date").apply(
    lambda d: d[d["trg_p2"].astype(bool)]["ret_p2"].mean() if d["trg_p2"].astype(bool).any() else 0.0)
comb["C 触发才买(未触发市价)"] = top2.groupby("date").apply(
    lambda d: (d[d["trg_p2"].astype(bool)]["ret_p2"].mean()
               if d["trg_p2"].astype(bool).any() else d["ret_o940"].mean()))
for name, s in comb.items():
    s = s.dropna()
    print(f"  {name:22s}: 日均 {s.mean()*100:+5.2f}% | 累计 {s.sum()*100:+7.1f}pp | 正收益天数 {(s>0).mean()*100:.0f}%")
nontrg = ok[~ok["trg_p2"].astype(bool)]
stat("未触发样本 9:36/9:37买", nontrg["ret_o940"])

print("\n===== ⑤ 触发特征 =====")
# 全 Top10 样本的触发特征 (用 ap 而非 top2, 同 Cursor 的触发特征口径)
trg_all = ap[ap["trg_p2"].astype(bool)]
rate_by_bucket = ap.groupby(pd.cut(ap["chg_935"], [-1, 0, 0.02, 0.04, 1]))["trg_p2"].mean()
print("9:35 涨幅分桶触发率:")
for iv, r in rate_by_bucket.items():
    n = len(ap[ap["chg_935"].between(iv.left, iv.right, inclusive='left')])
    print(f"  {iv}: {r*100:5.1f}% (n={n})")
# score 四分位触发率
ap["score_q"] = pd.qcut(ap["score"], 4, labels=False, duplicates="drop")
print("score 四分位触发率:", [f"{x*100:.1f}%" for x in ap.groupby("score_q")["trg_p2"].mean().tolist()])
print(f"  触发时点中位: {top2[top2['trg_p2'].astype(bool)]['tmin_p2'].median():.0f} 分 (570=9:30)")

# ---------- 6. 混合策略 ----------
print("\n===== ⑥ 混合策略 (阈值扫描) =====")
for thr in (0.0, 0.01, 0.02, 0.03, 0.04):
    def arm_ret(d):
        if d["chg_935"] < thr:
            return d["ret_o940"]
        return d["ret_p2"] if d["trg_p2"] else 0.0
    r = top2[top2["o940_valid"]].apply(arm_ret, axis=1)
    daily = top2[top2["o940_valid"]].assign(_r=r).groupby("date")["_r"].mean()
    tag = f"M{int(thr*100)}%"
    print(f"  {tag}: 日均 {daily.mean()*100:+5.2f}% | 累计 {daily.sum()*100:+7.1f}pp "
          f"| 正收益天数 {(daily>0).mean()*100:.0f}% | 中位 {daily.median()*100:+.2f}%")

# 稳健性: 去掉最大单日 (阈值3%)
thr = 0.03
def arm_ret3(d):
    if d["chg_935"] < thr:
        return d["ret_o940"]
    return d["ret_p2"] if d["trg_p2"] else 0.0
tt = top2[top2["o940_valid"]].copy()
tt["_m3"] = tt.apply(arm_ret3, axis=1)
dm = tt.groupby("date")["_m3"].mean().dropna()
comb_b = comb["B 触发才买(空仓)"].dropna()
print(f"\n  稳健性(M3%): 去掉最大单日后 混合 {dm.sort_values().iloc[1:].sum()*100:+.1f}pp vs 现网 {comb_b.sort_values().iloc[1:].sum()*100:+.1f}pp")
print(f"  收益>5% 天数: 混合 {(dm>0.05).sum()} vs 现网 {(comb_b>0.05).sum()} | 亏损<-5% 天数: 混合 {(dm<-0.05).sum()} vs 现网 {(comb_b<-0.05).sum()}")
