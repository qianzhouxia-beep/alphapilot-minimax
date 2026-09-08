# -*- coding: utf-8 -*-
"""读 score_top10 完整 + daily_recommend 找 新鹏/金富 (一次性)"""
import sys
sys.path.insert(0, r"C:/Users/elvisq/Projects/alphapilot/bt_research")
from srv_ssh import Ssh

CMD = r"""
cd /home/ubuntu/alphapilot && python3 -c "
# -*- coding: utf-8 -*-
import json, sys
sys.stdout.reconfigure(encoding='utf-8')
d=json.load(open('output/score_top10.json'))
print('TYPE:', type(d).__name__)
if isinstance(d, dict):
    print('KEYS:', list(d.keys()))
rows = d if isinstance(d, list) else d.get('top10') or d.get('data') or d.get('picks') or []
print('N_ROWS:', len(rows))
for i,r in enumerate(rows[:15]):
    print(i+1, '|', r.get('symbol'), '|', r.get('name'), '| score=', r.get('score'), '| fs=', json.dumps(r.get('fusion_scores'), ensure_ascii=False))
"
"""

s = Ssh()
try:
    o, e, code = s.run(CMD, timeout=60)
    print(o)
    if e.strip():
        print("ERR:", e[:500])
finally:
    s.close()
