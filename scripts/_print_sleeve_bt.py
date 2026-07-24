#!/usr/bin/env python3
import json
d = json.load(open("output/weak_rotation_sleeve_backtest.json", encoding="utf-8"))
a = d["mode_collapse_empty"]
print("SUMMARY", a["summary"])
for x in a["days"]:
    print("---", x["trade_day"], "avg", x["avg_trade_ret"], "pool30", x.get("pool30_avg_ret"),
          "pool_hit", x.get("pool30_hit_ge3"), "skip", x.get("skip_reason"))
    print("hot", x.get("hot_industries")[:6])
    print("topn", [(p["name"], p["trade_ret"], p["industry_l1"], p.get("ret5_pre")) for p in x["sleeve_topn"]])
    print("caught", x.get("caught_ge3"))
print("TRAITS_POOLED")
print(json.dumps(d["strong_ge3_common_traits"]["pooled"], ensure_ascii=False, indent=2))
print("TRAITS_BY_DAY")
for k, v in d["strong_ge3_common_traits"]["by_day"].items():
    print(k, "n=", v.get("n"), "uptrend", v.get("pct_uptrend_ma"), "mild_vr", v.get("pct_vr_mild_0_8_1_8"),
          "main5", v.get("pct_main5_pos"), "main_bd", v.get("pct_main_board"),
          "top_dens", v.get("top_industry_density")[:5])
