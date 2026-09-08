# -*- coding: utf-8 -*-
"""查 000700 今日快照价格 (从服务器) (一次性)"""
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
df = c.quotes(symbol=['000700'])
print(df.to_string() if df is not None and len(df) else 'NO QUOTE')
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
