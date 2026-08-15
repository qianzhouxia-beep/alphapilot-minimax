# -*- coding: utf-8 -*-
"""混合策略回测: 9:35 低涨幅直接买 + 高涨幅等动态确认

设计:
  每日 score Top2 (9:35 定格)
  对每只票:
    若 chg_935 < THRESH  → 9:36/9:37 市价直接买 (o940, 管线出票后立即成交)
    若 chg_935 >= THRESH → 等动态确认 (触发则 px_p2 买, 未触发空仓)
  组合收益 = 当日买入票的均收益 (都没买=0)

对比基准:
  现网 B: 全部等动态确认 (触发才买, 未触发空仓)
  全买 A: 全部 9:36/9:37 市价买

THRESH 敏感度: 0% / 1% / 2% / 3% / 4%
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
for df in (px935, px940o):
    ap = ap.merge(df, on=["date", "symbol"], how="left")

ap["lim"] = ap["symbol"].apply(limit_pct)
ap["near_limit"] = ap["chg_935"] >= ap["lim"] * 0.97
ap = ap[~ap["near_limit"]]


def pick_top2(day):
    return day.sort_values("score", ascending=False).head(2)


top2 = pd.concat([pick_top2(d) for _, d in ap.groupby("date")])
top2["trg_p2"] = top2["trg_p2"].astype(bool)
top2["ret_o940"] = top2["c_next"] / top2["o940"] - 1
top2["ret_p2"] = np.where(top2["trg_p2"], top2["c_next"] / top2["px_p2"] - 1, np.nan)

print(f"样本: {len(top2)} ({top2['date'].nunique()}天 Top2), 剔除涨停 {ap['near_limit'].sum()}, o940缺失 {top2['o940'].isna().sum()}")


def hybrid_daily(day, thresh):
    """混合策略单日: 返回当日组合收益."""
    rets = []
    for _, row in day.iterrows():
        if row["chg_935"] < thresh:
            # 低涨幅: 市价直接买
            if row["o940"] is not None and np.isfinite(row["o940"]):
                rets.append(row["ret_o940"])
        else:
            # 高涨幅: 等动态确认
            if row["trg_p2"]:
                rets.append(row["ret_p2"])
    if len(rets) == 0:
        return 0.0
    return float(np.mean(rets))


def all_confirm_daily(day):
    """现网: 全部等动态确认, 未触发空仓."""
    trg = day[day["trg_p2"]]
    if len(trg) == 0:
        return 0.0
    return float(trg["ret_p2"].mean())


def all_buy_daily(day):
    """全买: 全部 9:36/9:37 市价."""
    d = day[day["o940"].notna()]
    if len(d) == 0:
        return 0.0
    return float(d["ret_o940"].mean())


dates = top2["date"].unique()
base_confirm = [all_confirm_daily(top2[top2["date"] == d]) for d in dates]
base_allbuy = [all_buy_daily(top2[top2["date"] == d]) for d in dates]

print("\n===== 组合对比 (77天每日Top2) =====")
def stat(name, s):
    s = np.array(s)
    print(
        f"  {name:30s}: 日均 {s.mean()*100:+5.2f}% | 累计 {s.sum()*100:+7.1f}pp | "
        f"正收益天数 {(s>0).mean()*100:.0f}% | 中位 {np.median(s)*100:+.2f}%"
    )

stat("B. 现网 全动态确认", base_confirm)
stat("A. 全买 9:36/9:37市价", base_allbuy)
print()

for th in [0.00, 0.01, 0.02, 0.03, 0.04]:
    hyb = [hybrid_daily(top2[top2["date"] == d], th) for d in dates]
    stat(f"M{int(th*100)}%. 低涨幅市价买(阈{int(th*100)}%)", hyb)
    # 对比现网
    arr = np.array(hyb) - np.array(base_confirm)
    print(f"      → vs 现网: 累计差 {arr.sum()*100:+6.1f}pp | 跑赢天数 {(arr>0).mean()*100:.0f}%")

# 低涨幅样本市价买的收益分解 (阈值2%)
print("\n===== 阈值2% 混合策略样本分解 =====")
low = top2[top2["chg_935"] < 0.02]
high = top2[top2["chg_935"] >= 0.02]
print(f"  低涨幅(<2%) 样本: {len(low)} ({len(low)/len(top2)*100:.0f}%)")
print(f"    其中动态确认会触发: {low['trg_p2'].mean()*100:.0f}% ({low['trg_p2'].sum()}/{len(low)})")
print(f"    市价买 次日: {low['ret_o940'].mean()*100:+.2f}% | 胜率 {(low['ret_o940']>0).mean()*100:.0f}% | 大跌 {(low['ret_o940']<-0.05).mean()*100:.0f}%")
print(f"    若等确认触发: {low[low['trg_p2']]['ret_p2'].mean()*100:+.2f}% (n={low['trg_p2'].sum()})")
print(f"  高涨幅(>=2%) 样本: {len(high)}")
print(f"    其中动态确认会触发: {high['trg_p2'].mean()*100:.0f}% ({high['trg_p2'].sum()}/{len(high)})")
print(f"    若等确认触发: {high[high['trg_p2']]['ret_p2'].mean()*100:+.2f}% (n={high['trg_p2'].sum()})")
print(f"    未触发(空仓)占比: {(~high['trg_p2']).mean()*100:.0f}%")

# 稳健性: 阈值3% 的收益是否被极端日拉动?
print("\n===== 稳健性: 阈值3% 逐日收益分布 =====")
th = 0.03
hyb3 = np.array([hybrid_daily(top2[top2["date"] == d], th) for d in dates])
base = np.array(base_confirm)
print(f"  混合M3 累计 {hyb3.sum()*100:+.1f}pp vs 现网 {base.sum()*100:+.1f}pp")
print(f"  混合M3 收益>5%的天数: {(hyb3>0.05).sum()}, 现网: {(base>0.05).sum()}")
print(f"  混合M3 亏损<-5%的天数: {(hyb3<-0.05).sum()}, 现网: {(base<-0.05).sum()}")
# 去掉最大单日贡献后的累计
print(f"  混合M3 去掉最大单日: {(hyb3.sum()-hyb3.max())*100:+.1f}pp vs 现网去掉最大: {(base.sum()-base.max())*100:+.1f}pp")
# 中位数收益
print(f"  混合M3 日收益中位: {np.median(hyb3)*100:+.2f}% vs 现网: {np.median(base)*100:+.2f}%")
