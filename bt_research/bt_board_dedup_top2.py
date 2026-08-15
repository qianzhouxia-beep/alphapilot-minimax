# -*- coding: utf-8 -*-
"""同板块去重只留龙头 vs 现网 score Top2."""
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


def score_top2(day):
    return day.sort_values("score", ascending=False).head(2)


def board_dedup_top2(day):
    """同板块只保留龙头(最高chg_935), 再按score取Top2."""
    d = day.sort_values("chg_935", ascending=False).drop_duplicates(subset="l3", keep="first")
    return d.sort_values("score", ascending=False).head(2)


trg = ap[ap["trigger"] == True]
live = pd.concat([score_top2(d) for _, d in trg.groupby("date")])
ddx = pd.concat([board_dedup_top2(d) for _, d in trg.groupby("date")])


def s(tag, x):
    if len(x) == 0:
        print(tag, "n=0")
        return
    print(
        f"{tag:30s}: n={len(x):3d} ret={x.mean()*100:+5.2f}% med={x.median()*100:+5.2f}% "
        f"wr={(x>0).mean()*100:4.1f}% big_win={(x>0.07).mean()*100:4.1f}% big_lose={(x<-0.05).mean()*100:4.1f}%"
    )


print("=== 同板块去重只留龙头 vs 现网score Top2 ===")
s("现网 P2 (score Top2)", live["ret_close"])
s("同板块去重+龙头(再按score)", ddx["ret_close"])
print()
print(f"去重法龙头占比 {ddx['is_leader'].mean()*100:.0f}% vs 现网 {live['is_leader'].mean()*100:.0f}%")
lv = live.groupby("date")["ret_close"].mean()
im = ddx.groupby("date")["ret_close"].mean()
j = pd.concat([lv.rename("live"), im.rename("dedup")], axis=1).dropna()
print(f"共{len(j)}天 去重法跑赢天数 {(j['dedup']>j['live']).mean()*100:.0f}%")
print(f"累计差 {((j['dedup']-j['live']).sum()*100):+.2f}pp")
chg_days = j[abs(j["dedup"] - j["live"]) > 0.001]
print(f"产生差异的天数 {len(chg_days)}/{len(j)}")
