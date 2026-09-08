# -*- coding: utf-8 -*-
"""查 002292/003032 今日快照 (是否同批卖飞) (一次性)"""
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
for code in ['002292', '003032']:
    df = c.quotes(symbol=[code])
    if df is not None and len(df):
        r = df.iloc[0]
        print(code, 'price=%s last_close=%s open=%s high=%s low=%s' % (r.get('price'), r.get('last_close'), r.get('open'), r.get('high'), r.get('low')))
    else:
        print(code, 'NO')
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
