# -*- coding: utf-8 -*-
"""拉 000700 今日分时 (09:35 卖出后走势) (一次性)"""
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
    df = c.minutes(symbol='000700', frequency=5)
    if df is not None and len(df):
        print('n=', len(df))
        df = df.tail(30)
        for _, r in df.iterrows():
            print(r.get('datetime'), 'o=%s c=%s h=%s l=%s v=%s' % (r.get('open'), r.get('close'), r.get('high'), r.get('low'), r.get('vol')))
    else:
        print('NO minutes data')
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
