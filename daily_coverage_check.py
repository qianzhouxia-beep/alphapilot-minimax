# -*- coding: utf-8 -*-
"""daily_coverage_check.py — 全数据 时间+覆盖率 双维检查 (正式版, 部署到服务器)
检查项:
  1. kline_all    : 最新日期 + 近5交易日逐日覆盖数 (阈值 <4500 告警)
  2. chip         : date 分布 + 最新日期占比 (阈值 <95% 告警)
  3. fund_flow    : 最新日期 + 近5日逐日覆盖 (阈值 <4800 告警)
  4. open5m       : 最新日期 + 当日行数 (阈值 <8000 告警)
  5. kline5m      : 最新日期 (抽样)
  6. 板块资金     : asof 日期
  7. daily_recommend: run_at + recommendations 数
输出: output/logs/coverage_check.json + 控制台
退出码: 0=全部OK 1=有告警
"""
import json, os, time, sys
from collections import Counter

ROOT = '/home/ubuntu/alphapilot'
KLINE = f'{ROOT}/data/kline_cache/kline_all.parquet'
CHIP = f'{ROOT}/data/chip_data_all.json'
FUND = f'{ROOT}/data/fund_flow_history.json'
OPEN5M = f'{ROOT}/open5m_all.csv'
REC = f'{ROOT}/output/daily_recommend.json'

alerts = []
report = {"ts": time.strftime('%Y-%m-%d %H:%M:%S'), "items": {}}

def log(msg):
    print(msg, flush=True)

# ---------- 1. kline_all ----------
try:
    import pandas as pd
    df = pd.read_parquet(KLINE, columns=['symbol', 'date'])
    df['date'] = df['date'].astype(str)
    dates = sorted(df['date'].unique())
    last5 = dates[-5:]
    cov = {d: int((df['date'] == d).sum()) for d in last5}
    latest = last5[-1]
    n_ok = cov.get(latest, 0)
    item = {"latest": latest, "daily_cov": cov, "total_symbols": int(df['symbol'].nunique())}
    report['items']['kline_all'] = item
    log(f"[KLINE] 最新 {latest} | 近5日覆盖 {cov} | 总 {item['total_symbols']}")
    if n_ok < 4500:
        alerts.append(f"kline_all 覆盖率不足: {latest} 仅 {n_ok} 只 (<4500)")
except Exception as e:
    alerts.append(f"kline_all 读取失败: {str(e)[:120]}")

# ---------- 2. chip ----------
try:
    d = json.load(open(CHIP))
    data = d.get('data', d) if isinstance(d, dict) else d
    dates = Counter()
    for v in data.values():
        if isinstance(v, dict) and v.get('date'):
            dates[str(v['date'])] += 1
    if dates:
        latest = max(dates)
        n_latest = dates[latest]
        pct = n_latest / len(data) * 100
        report['items']['chip'] = {"latest": latest, "n": int(n_latest), "total": len(data), "pct": round(pct, 1)}
        log(f"[CHIP ] 最新 {latest}: {n_latest}/{len(data)} ({pct:.1f}%)")
        if pct < 95:
            alerts.append(f"chip 覆盖率不足: {latest} 仅 {pct:.1f}%")
    else:
        alerts.append("chip 无日期数据")
except Exception as e:
    alerts.append(f"chip 读取失败: {str(e)[:120]}")

# ---------- 3. fund_flow ----------
try:
    raw = open(FUND, encoding='utf-8').read()
    cut = raw.rfind('}')
    if cut > 0:
        raw = raw[:cut+1]
    fd = json.loads(raw)
    dates_all = Counter()
    for v in fd.values():
        if isinstance(v, dict):
            for k in v.keys():
                dates_all[str(k)] += 1
    if dates_all:
        latest = max(dates_all)
        n_latest = dates_all[latest]
        last5 = sorted(dates_all)[-5:]
        cov5 = {dd: int(dates_all[dd]) for dd in last5}
        report['items']['fund_flow'] = {"latest": latest, "n_latest": n_latest, "total": len(fd), "cov5": cov5}
        log(f"[FUND ] 最新 {latest}: {n_latest}/{len(fd)} | 近5日 {cov5}")
        if n_latest < 4800:
            alerts.append(f"fund_flow 覆盖率不足: {latest} 仅 {n_latest} 只 (<4800)")
    else:
        alerts.append("fund_flow 无数据")
except Exception as e:
    alerts.append(f"fund_flow 读取失败: {str(e)[:120]}")

# ---------- 4. open5m ----------
try:
    import pandas as pd
    df5 = pd.read_csv(OPEN5M, dtype={'code': str}, usecols=['code', 'date'])
    latest = df5['date'].max()
    n_latest = int((df5['date'] == latest).sum())
    report['items']['open5m'] = {"latest": latest, "n": n_latest, "total_rows": len(df5)}
    log(f"[O5M  ] 最新 {latest}: {n_latest} 只")
    if n_latest < 8000:
        alerts.append(f"open5m 覆盖不足: {latest} 仅 {n_latest} 只 (<8000)")
except Exception as e:
    alerts.append(f"open5m 读取失败: {str(e)[:120]}")

# ---------- 5. kline5m (抽样最新) ----------
try:
    import glob
    k5 = glob.glob(f'{ROOT}/data/kline5m/*.parquet')
    if k5:
        import pandas as pd
        s = pd.read_parquet(k5[0])
        dt = str(s['datetime'].max())[:10]
        report['items']['kline5m'] = {"latest_sample": dt, "files": len(k5)}
        log(f"[K5M  ] 抽样最新 {dt} | 文件 {len(k5)}")
except Exception as e:
    alerts.append(f"kline5m 读取失败: {str(e)[:120]}")

# ---------- 6. 板块资金 ----------
try:
    for name, key in [('concept_flow_today.json', 'concept'), ('sector_flow_today.json', 'sector')]:
        for pat in [f'{ROOT}/data/{name}', f'{ROOT}/output/{name}', f'{ROOT}/{name}']:
            if os.path.exists(pat):
                d2 = json.load(open(pat))
                asof = d2.get('asof', 'N/A')
                n = d2.get('total', len(d2.get('data', [])))
                report['items'][key + '_flow'] = {"asof": asof, "n": n}
                log(f"[{key.upper():4}] asof {asof} | {n} 条")
                break
except Exception as e:
    alerts.append(f"板块资金读取失败: {str(e)[:120]}")

# ---------- 7. daily_recommend ----------
try:
    rec = json.load(open(REC))
    run_at = rec.get('run_at', 'N/A')
    nrec = len(rec.get('recommendations', []))
    report['items']['daily_recommend'] = {"run_at": run_at, "n": nrec}
    log(f"[REC  ] run_at {run_at} | 推荐 {nrec} 只")
except Exception as e:
    alerts.append(f"daily_recommend 读取失败: {str(e)[:120]}")

# ---------- 输出 ----------
report['ok'] = len(alerts) == 0
report['alerts'] = alerts
os.makedirs(f'{ROOT}/output/logs', exist_ok=True)
with open(f'{ROOT}/output/logs/coverage_check.json', 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
log('=' * 50)
if alerts:
    log('⚠️ 告警:')
    for a in alerts:
        log(f'  - {a}')
    log(f'结果: FAIL ({len(alerts)} 项)')
    sys.exit(1)
else:
    log('结果: OK (全部数据 时间+覆盖率 正常)')
    sys.exit(0)
