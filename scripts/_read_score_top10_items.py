# -*- coding: utf-8 -*-
"""读 score_top10 items (一次性)"""
import sys
sys.path.insert(0, r"C:/Users/elvisq/Projects/alphapilot/bt_research")
from srv_ssh import Ssh

CMD = r"""
cd /home/ubuntu/alphapilot && python3 -c "
import json, sys
sys.stdout.reconfigure(encoding='utf-8')
d=json.load(open('output/score_top10.json'))
print('asof:', d.get('asof'), 'mode:', d.get('mode'), 'n:', d.get('n'))
print('note:', d.get('note'))
items = d.get('items') or []
print('items:', len(items))
for i,r in enumerate(items[:15]):
    print(i+1, '|', r.get('symbol'), '|', r.get('name'), '| score=', r.get('score'), '| fs=', json.dumps(r.get('fusion_scores'), ensure_ascii=False) if r.get('fusion_scores') else 'none')
print('--- recommend_compare ---')
rc = d.get('recommend_compare')
print(json.dumps(rc, ensure_ascii=False)[:800] if rc else 'none')
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
