# -*- coding: utf-8 -*-
"""拉 000700 今日 5m K线 (一次性)"""
import sys
sys.path.insert(0, r"C:/Users/elvisq/Projects/alphapilot/bt_research")
from srv_ssh import Ssh

CMD = r"""
cd /home/ubuntu/alphapilot && python3 -c "
# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')
from mootdx.quotes import Quotes
c = Quotes.factory(market='std')
try:
    df = c.bars(symbol='000700', frequency=5, offset=48)
    if df is not None and len(df):
        print('n=', len(df))
        print(df.tail(20).to_string())
    else:
        print('NO 5m data')
except Exception as e:
    print('ERR', e)
"
"""

s = Ssh()
try:
    o, e, code = s.run(CMD, timeout=90)
    print(o)
    if e.strip():
        print("ERR:", e[:400])
finally:
    s.close()
