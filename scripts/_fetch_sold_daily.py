# -*- coding: utf-8 -*-
"""拉 TDX A/B + QMT live 全部卖出股票的日线 (一次性)"""
import sys, json
sys.path.insert(0, r"C:/Users/elvisq/Projects/alphapilot/bt_research")
from srv_ssh import Ssh

# 所有卖出涉及的股票 (symbol6)
SELLS = {
    "TDX_A": [
        ("2026-08-20", "000651", 41.47, "rotation_sell -0.1%"),
        ("2026-08-24", "300139", 57.95, "t2_after_extend 70%"),
        ("2026-08-24", "601083", 13.11, "t2_after_extend 12.1%"),
        ("2026-08-24", "601998", 8.56, "t2_after_extend 2.2%"),
        ("2026-08-25", "603209", 14.37, "t2_force -1.8%"),
        ("2026-08-26", "001301", 63.06, "rotation_sell -1.5%"),
        ("2026-08-27", "002747", 31.33, "rotation_sell -0.1%"),
        ("2026-08-28", "002015", 16.07, "rotation_sell -0.5%"),
        ("2026-08-28", "000938", 35.92, "t2_after_extend 2.2%"),
        ("2026-08-31", "002466", 49.67, "rotation_sell -1.9%"),
    ],
    "TDX_B": [
        ("2026-08-20", "000651", 41.46, "t2_force -0.1%"),
        ("2026-08-20", "300568", 14.61, "t2_force -3.1%"),
        ("2026-08-20", "601083", 11.63, "t2_force -0.5%"),
        ("2026-08-20", "601919", 16.62, "t2_force -0.6%"),
    ],
}
symbols = sorted(set(s[1] for v in SELLS.values() for s in v))
json.dump(SELLS, open(r"C:\Users\elvisq\Projects\alphapilot\scripts\_sell_list.json", "w"))

CMD = r"""
cd /home/ubuntu/alphapilot && python3 -c "
import pandas as pd, sys
sys.stdout.reconfigure(encoding='utf-8')
df = pd.read_parquet('data/kline_cache/kline_all.parquet')
ccol = 'symbol' if 'symbol' in df.columns else 'code'
df['sym'] = df[ccol].astype(str).str.zfill(6)
targets = '@@SYMS@@'.split(',')
for t6 in targets:
    d = df[df['sym']==t6].sort_values('date')
    d = d[d['date']>='2026-08-19']
    print('== ' + t6 + ' rows=%d' % len(d))
    for _, r in d.iterrows():
        print('  %s o=%.2f h=%.2f l=%.2f c=%.2f' % (str(r['date'])[:10], r['open'], r['high'], r['low'], r['close']))
" 2>&1
""".replace("@@SYMS@@", ",".join(symbols))

s = Ssh()
try:
    o, e, code = s.run(CMD, timeout=120)
    print(o)
    if e.strip():
        print("ERR:", e[:400])
finally:
    s.close()
