#!/usr/bin/env python3
"""
AlphaPilot 盘后数据全量刷新脚本 (服务器端)
流程:
  0. 当日行业/概念资金流榜（东财「今日」，修 T+1 落盘滞后）
  1. 资金流历史库
  1b. Wind 候选股资金/PE 覆盖（需 WIND_API_KEY；失败不阻断）
  2. 两融 + 业绩预告
  3. 龙虎榜近月
  4. 基本面聚合
  5. K线缓存增量
  6. 筹码：用落盘K线本地推演（不依赖东财/本地上传）
  7. 数据新鲜度检测 + readiness 修复

状态: /tmp/refresh_all_data.status
预警: output/data_alerts.json
"""
import os
import sys
import json
import time
import subprocess

os.chdir("/home/ubuntu/alphapilot")
STATUS_FILE = "/tmp/refresh_all_data.status"
READY_LOG = "output/logs/data_readiness.log"


def set_status(step, progress, detail=""):
    now = time.strftime("%H:%M:%S")
    status = {
        "step": step,
        "progress": progress,
        "detail": detail,
        "updated_at": now,
        "date": time.strftime("%Y-%m-%d"),
    }
    with open(STATUS_FILE, "w") as f:
        json.dump(status, f, ensure_ascii=False)
    print(f"[{now}] {step} {progress}% - {detail}", flush=True)


def run_step(name, cmd, timeout_min=20):
    set_status(name, 0, f"开始执行: {cmd}")
    t0 = time.time()
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout_min * 60
        )
        elapsed = int(time.time() - t0)
        if r.returncode == 0:
            set_status(name, 100, f"完成 ({elapsed}s)")
            return True
        err = (r.stderr or r.stdout or "").strip()[-400:]
        set_status(name, -1, f"失败 ({elapsed}s): {err}")
        return False
    except subprocess.TimeoutExpired:
        set_status(name, -1, f"超时({timeout_min}min)")
        return False
    except Exception as e:
        set_status(name, -1, f"异常: {e}")
        return False


def run_step_retry(name, cmd, timeout_min=20, retries=3, sleep_sec=120):
    """盘后源站常延迟：失败则间隔重试。"""
    for i in range(1, retries + 1):
        ok = run_step(name, cmd, timeout_min=timeout_min)
        if ok:
            return True
        if i < retries:
            set_status(name, 0, f"第{i}次失败，{sleep_sec}s 后重试 ({i+1}/{retries})")
            time.sleep(sleep_sec)
    return False


if __name__ == "__main__":
    print("=" * 60, flush=True)
    print("AlphaPilot 盘后数据全量刷新", flush=True)
    print(time.strftime("%Y-%m-%d %H:%M:%S"), flush=True)
    print("=" * 60, flush=True)

    results = {}

    # 0) 行业/概念当日资金榜 — 必须进 15:30 主链，避免停在 T-1
    results["sector_board_flows"] = run_step_retry(
        "sector_board_flows",
        f"{sys.executable} -u scripts/refresh_sector_board_flows.py --require-today",
        timeout_min=8,
        retries=3,
        sleep_sec=90,
    )

    results["fund_flow"] = run_step(
        "fund_flow", f"{sys.executable} build_fund_flow_history.py", 5
    )

    # 1b) Wind 候选覆盖（无 Key 则跳过，不失败）
    if (os.environ.get("WIND_API_KEY") or "").strip() or os.path.exists(
        os.path.expanduser("~/.wind-aifinmarket/config")
    ):
        results["wind_candidates"] = run_step(
            "wind_candidates",
            f"{sys.executable} -u scripts/enrich_candidates_wind.py",
            8,
        )
    else:
        set_status("wind_candidates", 100, "跳过：未配置 WIND_API_KEY")
        results["wind_candidates"] = True

    results["margin_event"] = run_step(
        "margin_event", f"{sys.executable} pull_margin_event_data.py", 10
    )
    results["lhb"] = run_step(
        "lhb", f"{sys.executable} scripts/pull_lhb_history.py", 10
    )
    results["fundamentals"] = run_step(
        "fundamentals", f"{sys.executable} scripts/build_fundamental_data.py", 15
    )
    # 先更新 K 线，再算筹码（筹码依赖换手率日K）；空更新会对齐失败并重试
    results["kline_cache"] = run_step_retry(
        "kline_cache",
        "cd /home/ubuntu/alphapilot && python3 cache_kline.py update",
        timeout_min=30,
        retries=3,
        sleep_sec=120,
    )
    if results["kline_cache"]:
        results["chip"] = run_step(
            "chip",
            f"{sys.executable} -u scripts/pull_chip_from_kline.py --workers 1",
            timeout_min=40,
        )
    else:
        set_status("chip", -1, "跳过：K线未对齐源站最新日")
        results["chip"] = False

    if os.environ.get("REFRESH_RUN_RECOMMEND") == "1":
        results["recommend"] = run_step(
            "recommend", f"{sys.executable} -u recommend.py", 20
        )

    results["freshness"] = run_step(
        "freshness",
        f"{sys.executable} -u scripts/data_freshness_check.py --require-today",
        3,
    )

    results["readiness"] = run_step(
        "readiness",
        f"{sys.executable} -u scripts/data_readiness_gate.py --repair "
        f">> {READY_LOG} 2>&1",
        45,
    )

    critical_ok = all(
        results.get(k)
        for k in ("sector_board_flows", "fund_flow", "kline_cache", "fundamentals", "chip")
    )
    if critical_ok:
        set_status(
            "done",
            100,
            "关键数据已落盘（含服务器自算筹码）。告警见 output/data_alerts.json",
        )
        sys.exit(0)
    set_status("done", -1, f"部分失败: { {k:v for k,v in results.items() if not v} }")
    sys.exit(1)
