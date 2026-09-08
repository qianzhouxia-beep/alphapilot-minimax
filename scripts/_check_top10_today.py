# -*- coding: utf-8 -*-
"""查今日(0831)服务器候选Top10 vs 网页Top10 (一次性)"""
import sys
sys.path.insert(0, r"C:/Users/elvisq/Projects/alphapilot/bt_research")
from srv_ssh import Ssh

CMD = r"""
cd /home/ubuntu/alphapilot
echo '===== output 今日候选 ====='
ls -la output/*.candidates.json output/score_top10.json output/daily_recommend.json 2>/dev/null
echo
echo '===== 今日 candidates Top10 (含 fusion_scores) ====='
python3 -c "
import json, glob
f=sorted(glob.glob('output/20260831*.candidates.json'))
print('files:',f)
if not f: print('NO candidates today')
for fp in f[:1]:
    d=json.load(open(fp))
    rows=d if isinstance(d,list) else d.get('candidates',d.get('data',[]))
    for i,r in enumerate(rows[:12]):
        fs=r.get('fusion_scores') or {}
        print(i+1, r.get('symbol'), r.get('name'), 'score=',r.get('score'), 'fs_vm25=',fs.get('vm25'), 'fs_fund=',fs.get('fund_flow'))
"
echo
echo '===== score_top10 ====='
python3 -c "
import json
d=json.load(open('output/score_top10.json'))
rows=d if isinstance(d,list) else d.get('top10',d.get('data',[]))
for i,r in enumerate(rows[:12]):
    print(i+1, r.get('symbol'), r.get('name'))
" 2>/dev/null || cat output/score_top10.json 2>/dev/null | head -40
echo
echo '===== daily_recommend ====='
python3 -c "
import json
d=json.load(open('output/daily_recommend.json'))
rows=d if isinstance(d,list) else d.get('recommendations',d.get('data',d.get('picks',[])))
for i,r in enumerate(rows[:12]):
    print(i+1, r.get('symbol'), r.get('name'))
" 2>/dev/null || cat output/daily_recommend.json 2>/dev/null | head -30
"""

s = Ssh()
try:
    o, e, code = s.run(CMD, timeout=90)
    print(o)
    if e.strip():
        print("ERR:", e[:800])
finally:
    s.close()
