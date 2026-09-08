# -*- coding: utf-8 -*-
"""查 000700 今日 5m 走势 (卖出后是否反弹) (一次性)"""
import sys
sys.path.insert(0, r"C:/Users/elvisq/Projects/alphapilot/bt_research")
from srv_ssh import Ssh

CMD = r"""
cd /home/ubuntu/alphapilot && python3 -c "
# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd
df = pd.read_parquet('data/kline_cache/kline_all.parquet')
if 'symbol' in df.columns:
    code_col = 'symbol'
else:
    code_col = 'code'
sym = df[code_col].astype(str).str.zfill(6)
d = df[sym == '000700'].copy()
if len(d) == 0:
    print('NO 000700 in parquet')
else:
    print('rows:', len(d))
    print(d.tail(3).to_string())
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
