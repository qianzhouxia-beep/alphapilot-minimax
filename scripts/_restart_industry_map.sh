#!/bin/bash
cd /home/ubuntu/alphapilot
pkill -f 'build_stock_industry_map_tdx.py' 2>/dev/null || true
sleep 2
# 清掉混入的无效进度，只保留已成功的有效映射（可选：全量重来）
python3 - <<'PY'
import json
from pathlib import Path
p=Path('data/stock_industry_map_tdx_progress.json')
out=Path('data/stock_industry_map.json')
keep={}
for path in (p, out):
    if not path.exists():
        continue
    try:
        raw=json.loads(path.read_text(encoding='utf-8'))
        data=raw.get('data') if isinstance(raw,dict) and 'data' in raw else raw
        if not isinstance(data, dict):
            continue
        for k,v in data.items():
            if isinstance(v,dict) and v.get('industry_path') and v.get('source')=='tdx_f10':
                # 只要常见 A 股号段
                if k.startswith(('000','001','002','003','300','301','600','601','603','605','688','689','8','4')):
                    keep[k]=v
    except Exception as e:
        print('skip', path, e)
print('kept_valid', len(keep))
p.write_text(json.dumps({'data':keep,'ok':len(keep),'fail':0},ensure_ascii=False),encoding='utf-8')
out.write_text(json.dumps(keep,ensure_ascii=False,indent=2),encoding='utf-8')
PY
nohup python3 -u scripts/build_stock_industry_map_tdx.py --concurrency 16 > data/stock_industry_map_tdx.log 2>&1 &
echo PID:$!
sleep 10
head -30 data/stock_industry_map_tdx.log
