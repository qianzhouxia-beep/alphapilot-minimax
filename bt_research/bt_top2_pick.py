# -*- coding: utf-8 -*-
"""落地回测最终版: 多种 Top2 选法对比。
用户思路: 9:25~9:35 Top2 = 板块龙头优先 + 池内 + 资金量综合判断。
对比:
  A. 现网: score Top2
  B. 龙头优先加成 (score * 1.10 if leader)
  C. 同板块去重只留龙头再按score
  D. 只从龙头中选 (龙头不足2个则回退score补足)
  E. 龙头优先 + 资金量加成 (9:35累计成交额排名加成)
"""
import json
import pandas as pd

SNAP = r"C:\Users\elvisq\Projects\alphapilot\bt_research\_board_snap_cache.parquet"
NEXTDAY = r"C:\Users\elvisq\Projects\alphapilot\bt_research\_nextday_cache.parquet"
IND = r"C:\Users\elvisq\Projects\alphapilot\data\stock_industry_map.json"
P2 = r"C:\Users\elvisq\Projects\alphapilot\output\bt_dyn_confirm_long.json"

nd = pd.read_parquet(NEXTDAY)
nd["date"] = nd["date"].astype(str)
ind = json.load(open(IND, encoding="utf-8"))
sym2l3 = {s: info.get("industry_l3") for s, info in ind.items()}
snap = pd.read_parquet(SNAP)
snap["date"] = snap["date"].astype(str)
pc = snap[snap["snap_min"] == 330][["symbol", "date", "close"]].sort_values(["symbol", "date"])
pc["prev_close"] = pc.groupby("symbol")["close"].shift(1)
pc = pc[["symbol", "date", "prev_close"]].drop_duplicates()
snap = snap.merge(pc, on=["symbol", "date"], how="left").dropna(subset=["prev_close"])
snap["chg"] = snap["close"] / snap["prev_close"] - 1
dd = json.load(open(P2, encoding="utf-8"))
ap = pd.DataFrame(dd["trades"]["P2_dyn_confirm"])
ap["date"] = ap["date"].astype(str)
ap["buy_px"] = ap["px"].fillna(ap["p935"])
ap = ap.merge(nd, on=["symbol", "date"], how="left").dropna(subset=["c_next"])
ap["ret_close"] = ap["c_next"] / ap["buy_px"] - 1
ap["l3"] = ap["symbol"].map(sym2l3)
d935 = snap[snap["snap_min"] == 5][["date", "symbol", "chg"]].rename(columns={"chg": "chg_935"})
ap = ap.merge(d935, on=["date", "symbol"], how="left")
ap["board_max"] = ap.groupby(["date", "l3"])["chg_935"].transform("max")
ap["is_leader"] = (ap["chg_935"] == ap["board_max"]).astype(int)
# is_leader 可能因 chg_935 NaN 变为 NaN, 统一为 0/1
ap["is_leader"] = ap["is_leader"].fillna(0).astype(int)
# 资金量: 9:35 累计成交额 (cum_amount)
amt = snap[snap["snap_min"] == 5][["date", "symbol", "cum_amount"]].rename(
    columns={"cum_amount": "amt_935"}
)
ap = ap.merge(amt, on=["date", "symbol"], how="left")
ap["amt_rank"] = ap.groupby("date")["amt_935"].rank(ascending=False, pct=True)


def score_top2(day):
    return day.sort_values("score", ascending=False).head(2)


def leader_boost_top2(day, boost=0.10):
    d = day.copy()
    d["combo"] = d["score"] * (1 + boost * d["is_leader"])
    return d.sort_values("combo", ascending=False).head(2)


def board_dedup_top2(day):
    d = day.sort_values("chg_935", ascending=False).drop_duplicates(subset="l3", keep="first")
    return d.sort_values("score", ascending=False).head(2)


def leader_only_top2(day):
    """只从龙头中选, 不足则回退score补足."""
    leaders = day[day["is_leader"] == 1].sort_values("score", ascending=False)
    rest = day[day["is_leader"] == 0].sort_values("score", ascending=False)
    return pd.concat([leaders.head(2), rest.head(2)]).head(2)


def leader_amt_top2(day, leader_boost=0.10, amt_boost=0.10):
    """龙头优先 + 资金量加成 (9:35累计成交额前50%加分)."""
    d = day.copy()
    d["big_amt"] = (d["amt_rank"] <= 0.5).astype(int)
    d["combo"] = d["score"] * (1 + leader_boost * d["is_leader"] + amt_boost * d["big_amt"])
    return d.sort_values("combo", ascending=False).head(2)


trg = ap[ap["trigger"] == True]
methods = {
    "A. 现网 score Top2": score_top2,
    "B. 龙头加成10%": leader_boost_top2,
    "C. 同板块去重只留龙头": board_dedup_top2,
    "D. 只从龙头中选": leader_only_top2,
    "E. 龙头+资金量加成": leader_amt_top2,
}

res = {}
for name, fn in methods.items():
    rows = pd.concat([fn(d) for _, d in trg.groupby("date")])
    res[name] = rows


def s(tag, x):
    x = x.copy()
    x["is_leader"] = pd.to_numeric(x["is_leader"], errors="coerce").fillna(0)
    r = x["ret_close"]
    print(
        f"{tag:28s}: n={len(x):3d} ret={r.mean()*100:+5.2f}% med={r.median()*100:+5.2f}% "
        f"wr={(r>0).mean()*100:4.1f}% big_win={(r>0.07).mean()*100:4.1f}% big_lose={(r<-0.05).mean()*100:4.1f}% "
        f"leader={(x['is_leader'].mean()*100):3.0f}%"
    )


print("=== 9:25~9:35 Top2 落地选股法对比 (76天, 可交易子集) ===")
for name, rows in res.items():
    s(name, rows)

# 逐日胜率: 各法相对现网的日胜率
live_g = res["A. 现网 score Top2"].groupby("date")["ret_close"].mean()
print("\n[各法相对现网逐日跑赢天数]")
for name, rows in res.items():
    if name == "A. 现网 score Top2":
        continue
    g = rows.groupby("date")["ret_close"].mean()
    j = pd.concat([live_g.rename("live"), g.rename("g")], axis=1).dropna()
    diff_days = j[abs(j["g"] - j["live"]) > 0.001]
    if len(diff_days) == 0:
        print(f"  {name:28s}: 无差异")
        continue
    print(
        f"  {name:28s}: {len(diff_days)}/76天有差异, 跑赢 {((diff_days['g']>diff_days['live']).mean()*100):.0f}%, "
        f"累计差 {((diff_days['g']-diff_days['live']).sum()*100):+.2f}pp"
    )
