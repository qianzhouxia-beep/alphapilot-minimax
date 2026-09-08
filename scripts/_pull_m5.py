# -*- coding: utf-8 -*-
"""vwap_weak_early 信号回测：次日早盘卖 vs 次日收盘卖 vs 持有 (一次性)

策略对比:
  A. 现状: 信号日次日 09:35-09:50 早盘卖 (用 09:40 bar close 近似, 或实际日志价)
  B. 次日收盘卖 (持有到信号次日收盘)
  C. 持有到最终 (信号日之后最后可观测日收盘, 即 08-28 收盘, 或今天 08-31 盘中)

信号日 = vwap_broken 置位日 (14:45 尾盘), 次日 = 下一个交易日
"""
import json, os, sys
sys.path.insert(0, r"C:/Users/elvisq/Projects/alphapilot/bt_research")
from srv_ssh import Ssh

sig = json.load(open(r"C:\Users\elvisq\Projects\alphapilot\scripts\_vwap_signals_dedup.json"))

# 从 5m parquet 拉需要的 bar: {symbol: [(datetime, open, high, low, close)]}
syms = sorted(set(s["symbol"].split(".")[0] for s in sig))
cmd = r"""
cd /home/ubuntu/alphapilot && python3 -c "
import pandas as pd, sys, json
sys.stdout.reconfigure(encoding='utf-8')
out = {}
for s6 in '@@SYMS@@'.split(','):
    fp = 'data/kline5m/%s.parquet' % s6
    try:
        df = pd.read_parquet(fp)
    except Exception as e:
        print('ERR', s6, e); continue
    df = df.sort_values('datetime') if 'datetime' in df.columns else df.sort_index()
    rows = []
    for _, r in df.iterrows():
        t = str(r.get('datetime') or r.get('time') or r.name)
        rows.append([t, float(r['open']), float(r['high']), float(r['low']), float(r['close'])])
    out[s6] = rows
print('DATA_BEGIN')
print(json.dumps(out))
print('DATA_END')
"
"""
# 只拉需要的股票
cmd = cmd.replace("@@SYMS@@", ",".join(syms))

s = Ssh()
try:
    o, e, code = s.run(cmd, timeout=180)
    if "DATA_BEGIN" in o:
        body = o.split("DATA_BEGIN")[1].split("DATA_END")[0].strip()
        data = json.loads(body)
        json.dump(data, open(r"C:\Users\elvisq\Projects\alphapilot\scripts\_m5_data.json", "w"))
        print("saved %d symbols" % len(data))
    else:
        print("NO DATA_BEGIN")
        print(o[-2000:])
    if e.strip():
        print("ERR:", e[:400])
finally:
    s.close()
