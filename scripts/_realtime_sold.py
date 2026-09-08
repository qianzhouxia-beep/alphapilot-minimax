# -*- coding: utf-8 -*-
"""用 mootdx 拉今天实时行情 (一次性)"""
import sys
sys.path.insert(0, r"C:/Users/elvisq/Projects/alphapilot/bt_research")
from srv_ssh import Ssh

CMD = r"""
cd /home/ubuntu/alphapilot && timeout 60 python3 -c "
import sys
sys.stdout.reconfigure(encoding='utf-8')
try:
    from mootdx.quotes import Quotes
    client = Quotes.factory(market='std')
except Exception as e:
    print('FACTORY_ERR', e)
    sys.exit(0)
syms = ['002466','002015','002980','300475','002636','000938','002747','002058','300390','000700','002292','003032']
for s6 in syms:
    try:
        q = client.quotes(symbol=s6)
        if q is None or q.empty:
            print(s6, 'NO_DATA'); continue
        row = q.iloc[0]
        name = row.get('name','')
        price = row.get('price') or row.get('last_close') or 0
        high = row.get('high') or 0
        low = row.get('low') or 0
        opn = row.get('open') or 0
        pre = row.get('last_close') or row.get('pre_close') or 0
        print('%s %s open=%.2f price=%.2f high=%.2f low=%.2f pre=%.2f' % (s6, name, float(opn), float(price), float(high), float(low), float(pre)))
    except Exception as e:
        print(s6, 'ERR', repr(e)[:100])
" 2>&1
"""

s = Ssh()
try:
    o, e, code = s.run(CMD, timeout=90)
    print(o)
    if e.strip():
        print("ERR:", e[:400])
finally:
    s.close()
