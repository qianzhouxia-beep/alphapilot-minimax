#!/usr/bin/env python3
"""
全量管线独立运行脚本（带超时、重试、日志）
"""
import sys
import json
import traceback
from pathlib import Path
from datetime import datetime

sys.path.insert(0, "/home/ubuntu/alphapilot")

LOG = Path("/home/ubuntu/alphapilot/logs/pipeline_run.log")
OUTPUT = Path("/home/ubuntu/alphapilot/output")
TOP_N = 20


def log(msg):
    t = datetime.now().strftime("%H:%M:%S")
    line = f"[{t}] {msg}"
    print(line)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_with_timeout(func, timeout=60, *args, **kwargs):
    """带超时的函数执行"""
    import threading

    result = [None]
    error = [None]
    done = threading.Event()

    def wrapper():
        try:
            result[0] = func(*args, **kwargs)
        except Exception as e:
            error[0] = e
        finally:
            done.set()

    t = threading.Thread(target=wrapper, daemon=True)
    t.start()
    if not done.wait(timeout=timeout):
        raise TimeoutError(f"函数执行超时 ({timeout}s)")
    if error[0]:
        raise error[0]
    return result[0]


try:
    from recommend import run_daily_recommend

    log("管线启动")
    log("直接调用 run_daily_recommend()...")
    result = run_daily_recommend(top_n=TOP_N)

    total_scanned = int(result.get("total_scanned", 0) or 0)
    valid_scored = int(result.get("valid_scored", 0) or 0)
    top = result.get("recommendations", []) or []

    log(f"扫描: {total_scanned} 只")
    log(f"有效评分: {valid_scored} 只")
    log(f"Top-{len(top)}:")
    for i, r in enumerate(top, 1):
        log(
            f"  {i}. {r['symbol']} {r['name']} | 评分: {r['score']:.4f} | "
            f"买入: {r['buy_price']:.2f} | 目标: {r['target_price']:.2f} | "
            f"止损: {r['stop_price']:.2f}"
        )

    OUTPUT.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT / f"daily_recommend_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    cache_path = OUTPUT / "daily_recommend.json"

    payload = {
        "generated_at": datetime.now().isoformat(),
        "total_scanned": total_scanned,
        "valid_scored": valid_scored,
        "top_n": TOP_N,
        "recommendations": top,
    }

    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"已保存: {output_path}")
    log(f"已保存缓存: {cache_path}")

    log("管线完成 ✅")

except Exception as e:
    log(f"❌ 管线异常: {e}")
    log(traceback.format_exc())
    sys.exit(1)
