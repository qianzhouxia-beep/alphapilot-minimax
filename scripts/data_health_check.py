#!/usr/bin/env python3
"""
AlphaPilot Pipeline & Data Health Check — P0 防护
05:10 cron: 检查凌晨管线是否正常产出，失败则写告警文件。
"""
import json, os, sys, time
from pathlib import Path

ROOT = Path("/home/ubuntu/alphapilot")
ALARM_PATH = ROOT / "output" / "health_alarm.json"
PIPELINE_LOG = ROOT / "output/logs/pipeline_0500.log"
REC_PATH = ROOT / "output/daily_recommend.json"
GC_PATH = ROOT / "output/volume_gc_pool.json"
ICIR_PATH = ROOT / "output/icir_all_scores.json"

NOW = time.strftime("%Y-%m-%d %H:%M:%S")
TODAY = time.strftime("%Y-%m-%d")

alarms = []

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

# 1. 检查 pipeline 日志是否包含「管线完成」
if PIPELINE_LOG.exists():
    text = PIPELINE_LOG.read_text(encoding="utf-8", errors="replace")
    if "🚀 管线完成!" in text:
        log("✅ pipeline_0500: 管线完成")
    elif "Traceback" in text:
        alarms.append("pipeline_crash: pipeline_0500.log 包含异常堆栈")
        log("❌ pipeline_0500: 崩溃")
    else:
        alarms.append("pipeline_incomplete: pipeline_0500.log 无完成标记")
        log("⚠️ pipeline_0500: 未完成")
else:
    alarms.append("pipeline_log_missing: pipeline_0500.log 不存在")
    log("❌ pipeline_0500: 日志缺失")

# 2. 检查 daily_recommend.json 候选数
n_rec = 0
if REC_PATH.exists():
    try:
        data = json.loads(REC_PATH.read_text(encoding="utf-8"))
        recs = data.get("recommendations") or []
        n_rec = len(recs)
        run_at = str(data.get("run_at") or data.get("generated_at") or "")[:10]
        if run_at == TODAY or run_at == "":
            if n_rec >= 5:
                log(f"✅ daily_recommend: {n_rec} 只候选 (新鲜)")
            elif n_rec > 0:
                alarms.append(f"low_candidates: daily_recommend 仅 {n_rec} 只")
                log(f"⚠️ daily_recommend: 仅 {n_rec} 只")
            else:
                alarms.append("empty_candidates: daily_recommend 为 0")
                log("❌ daily_recommend: 空")
        else:
            alarms.append(f"stale_run: daily_recommend asof={run_at} != today {TODAY}")
            log(f"❌ daily_recommend: 过期 ({run_at})")
    except Exception as e:
        alarms.append(f"rec_parse_error: {e}")
        log(f"❌ daily_recommend: 解析失败 {e}")
else:
    alarms.append("rec_missing: daily_recommend.json 不存在")
    log("❌ daily_recommend: 缺失")

# 3. 检查 icir_all_scores.json
if ICIR_PATH.exists():
    try:
        data = json.loads(ICIR_PATH.read_text(encoding="utf-8"))
        scores = data.get("scores", data.get("stocks", []))
        if len(scores) >= 100:
            log(f"✅ icir_all_scores: {len(scores)} 只")
        else:
            alarms.append(f"low_icir: icir 仅 {len(scores)} 只")
            log(f"⚠️ icir_all_scores: 仅 {len(scores)} 只")
    except:
        alarms.append("icir_parse_error")
        log("❌ icir_all_scores: 解析失败")
else:
    alarms.append("icir_missing")
    log("❌ icir_all_scores: 缺失")

# 4. 汇总
alarm = {
    "asof": NOW,
    "healthy": len(alarms) == 0,
    "n_alarms": len(alarms),
    "alarms": alarms,
    "recommendations": n_rec,
    "summary": "✅ 全部正常" if len(alarms) == 0 else f"⚠️ {len(alarms)} 项告警",
}

ALARM_PATH.write_text(json.dumps(alarm, ensure_ascii=False, indent=2), encoding="utf-8")

if alarms:
    log("⚠️" * 20)
    for a in alarms:
        log(f"  ⚠️ {a}")
    log("⚠️" * 20)
else:
    log("✅" * 10 + " 所有健康检查通过 " + "✅" * 10)

log(f"告警写入: {ALARM_PATH}")
raise SystemExit(0 if len(alarms) == 0 else 1)
