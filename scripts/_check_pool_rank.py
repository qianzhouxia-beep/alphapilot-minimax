# -*- coding: utf-8 -*-
"""确认 003018 在服务器池的排名 (一次性)"""
import sys
sys.path.insert(0, r"C:/Users/elvisq/Projects/alphapilot/bt_research")
from srv_ssh import Ssh

CMD = r"""
cd /home/ubuntu/alphapilot && python3 -c "
import json, sys, glob, os
sys.stdout.reconfigure(encoding='utf-8')
for fn in sorted(glob.glob('output/qmt_scores/20260831*.json')):
    print('==', os.path.basename(fn))
    d = json.load(open(fn))
    rows = d if isinstance(d, list) else d.get('items') or d.get('data') or []
    for target in ['003018.SZ', '002328.SZ', '300475.SZ', '002636.SZ']:
        for i, r in enumerate(rows[:50]):
            if r.get('symbol') == target:
                print('  %s rank=%d score=%s fhf=%s' % (target, i+1, r.get('score'), r.get('fund_hard_fail')))
                break
        else:
            print('  %s NOT in top50' % target)
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
