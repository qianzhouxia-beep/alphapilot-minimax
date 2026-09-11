#!/usr/bin/env python3
"""
AlphaPilot 盘后数据全量刷新脚本 (服务器端)
流程:
  1. K线缓存增量更新 (cache_kline.py update, ~14分钟)
  2. 筹码数据 (由本地 WorkBuddy 通过 upload-chip-data API 上传)
  (资金流历史库已移至 21:00 独立 cron: build_fund_flow_history.py)

状态文件: /tmp/refresh_all_data.status
"""
import os, sys, json, time, subprocess

os.chdir("/home/ubuntu/alphapilot")
STATUS_FILE = "/tmp/refresh_all_data.status"

def set_status(step, progress, detail=""):
    now = time.strftime("%H:%M:%S")
    status = {"step": step, "progress": progress, "detail": detail, "updated_at": now}
    with open(STATUS_FILE, "w") as f:
        json.dump(status, f)
    print(f"[{now}] {step} {progress}% - {detail}", flush=True)

def run_step(name, cmd, timeout_min=20):
    set_status(name, 0, f"开始执行: {cmd}")
    t0 = time.time()
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout_min*60)
        elapsed = int(time.time() - t0)
        if r.returncode == 0:
            set_status(name, 100, f"完成 ({elapsed}s)")
        else:
            err = r.stderr.strip()[-300:]
            set_status(name, -1, f"失败 ({elapsed}s): {err}")
        return r.returncode == 0
    except subprocess.TimeoutExpired:
        set_status(name, -1, f"超时({timeout_min}min)")
        return False
    except Exception as e:
        set_status(name, -1, f"异常: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60, flush=True)
    print("AlphaPilot 盘后数据全量刷新", flush=True)
    print(time.strftime("%Y-%m-%d %H:%M:%S"), flush=True)
    print("=" * 60, flush=True)

    success = True

    # Step 1: 资金流历史库
# MOVED 2026-08-06: 15:30 时 tdxhub 当天数据未更新完，拉不到当天 → 移到 21:00 单独 cron
#     success &= run_step("fund_flow",
#         f"{sys.executable} build_fund_flow_history.py", 5)

    # Step 2: 推荐管线
# DISABLED 2026-07-29: 会覆盖管线 daily_recommend.json — pipeline V3 已跑过
#     success &= run_step("recommend",
#         f"{sys.executable} -u recommend.py", 20)

    # Step 3: 筹码 - 由本地上传
    set_status("chip", 0, "筹码数据需通过 WorkBuddy 本地拉取上传")

# Step 4: K线缓存增量更新
    success &= run_step("kline_cache",
        "cd /home/ubuntu/alphapilot && python3 cache_kline.py update",
        timeout_min=30)

    if success:
        set_status("done", 100, "服务器端全部完成。请执行筹码数据更新。")
    else:
        set_status("done", -1, "部分步骤失败，请检查日志")
