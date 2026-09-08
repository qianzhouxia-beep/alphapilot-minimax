# -*- coding: utf-8 -*-
"""拉信号股票 08-20~08-31 日线 (一次性)"""
import json, sys
sys.path.insert(0, r"C:/Users/elvisq/Projects/alphapilot/bt_research")
from srv_ssh import Ssh

sig = json.load(open(r"C:\Users\elvisq\Projects\alphapilot\scripts\_vwap_signals_dedup.json"))
symbols = sorted(set(s["symbol"] for s in sig))
sym_list = ",".join(symbols)
print("symbols:", sym_list)

CMD = r"""
cd /home/ubuntu/alphapilot && python3 -c "
import pandas as pd, sys
sys.stdout.reconfigure(encoding='utf-8')
df = pd.read_parquet('data/kline_cache/kline_all.parquet')
ccol = 'symbol' if 'symbol' in df.columns else 'code'
df['sym'] = df[ccol].astype(str).str.zfill(6)
targets = '@@SYMS@@'.split(',')
for t in targets:
    t6 = t.split('.')[0]
    d = df[df['sym']==t6].sort_values('date')
    d = d[d['date']>='2026-08-19']
    print('== ' + t + ' rows=%d' % len(d))
    for _, r in d.iterrows():
        print('  %s o=%.2f h=%.2f l=%.2f c=%.2f' % (str(r['date'])[:10], r['open'], r['high'], r['low'], r['close']))
" 2>&1
""".replace("@@SYMS@@", sym_list)

s = Ssh()
try:
    o, e, code = s.run(CMD, timeout=120)
    print(o)
    if e.strip():
        print("ERR:", e[:500])
finally:
    s.close()
