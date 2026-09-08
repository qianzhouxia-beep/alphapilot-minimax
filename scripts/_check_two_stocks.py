# -*- coding: utf-8 -*-
"""查 002328 新朋股份 / 003018 金富科技 今日行情 (一次性)"""
import sys
sys.path.insert(0, r"C:/Users/elvisq/Projects/alphapilot/bt_research")
from srv_ssh import Ssh

CMD = r"""
cd /home/ubuntu/alphapilot && python3 -c "
# -*- coding: utf-8 -*-
import json, sys
sys.stdout.reconfigure(encoding='utf-8')
from mootdx.quotes import Quotes
c = Quotes.factory(market='std')
for code, name in [('002328','新朋股份'), ('003018','金富科技')]:
    df = c.quotes(symbol=[code])
    if df is not None and len(df):
        r = df.iloc[0]
        print(name, code, {k: r.get(k) for k in ['price','last_close','open','high','low','vol','amount','bid1_vol'] if k in r})
    else:
        print(name, code, 'NO QUOTE')
"
"""

s = Ssh()
try:
    o, e, code = s.run(CMD, timeout=60)
    print(o)
    if e.strip():
        print("ERR:", e[:400])
finally:
    s.close()
