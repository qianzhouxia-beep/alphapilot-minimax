#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据积累巡检 — 专门盯「盘中资金流」等新数据的持续积累。

背景：2026-08-06 买卖点研究收敛，结论是「先积累数据，09 月初再回测资金背离信号」。
本脚本每天盘后检查各积累数据是否正常增长，防止积累中断（服务停、cron 失效等）。

检查项：
  1. institutional-watch 服务是否 active
  2. institutional_watch_history.jsonl 是否今天仍在写、行数是否较上次增长、已积累几个交易日
  3. institutional_watch.json / fund_strength.json 最新快照是否今天更新
  4. kline5m 最新交易日是否为今天
  5. score_top10_day 归档今天 open/close 是否齐全

输出：
  - 报告：output/logs/data_accumulation.log（追加）
  - 状态：output/data_accumulation.json（覆盖，含 verdict）
异常时 verdict=ATTENTION 且 exit code 2（与 monitor_morning_soft_hybrid 一致）。

用法：
  python3 scripts/data_accumulation_check.py          # 正常巡检（写状态）
  python3 scripts/data_accumulation_check.py --manual # 手跑，不更新状态基线
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, date
from pathlib import Path

ROOT = Path("/home/ubuntu/alphapilot")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)

OUT = ROOT / "output"
LOGS = OUT / "logs"
STATE_PATH = OUT / ".data_accumulation_state.json"
RESULT_PATH = OUT / "data_accumulation.json"
LOG_PATH = LOGS / "data_accumulation.log"

TARGET_TRADING_DAYS = 20  # 资金背离信号回测所需最少交易日

today = date.today().isoformat()


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    try:
        LOGS.mkdir(exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def sh(cmd: str) -> str:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return (r.stdout + r.stderr).strip()
    except Exception as e:
        return f"err:{type(e).__name__}"


def file_mtime_today(p: Path) -> bool:
    try:
        return date.fromtimestamp(p.stat().st_mtime).isoformat() == today
    except Exception:
        return False


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(s: dict) -> None:
    try:
        STATE_PATH.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def history_stats() -> dict:
    """解析 institutional_watch_history.jsonl：条数 + 积累交易日列表。"""
    p = OUT / "institutional_watch_history.jsonl"
    if not p.exists():
        return {"exists": False, "lines": 0, "days": [], "first_ts": None, "last_ts": None}
    lines = []
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return {"exists": True, "lines": -1, "days": [], "first_ts": None, "last_ts": None}
    days = []
    first_ts = last_ts = None
    for ln in lines:
        try:
            obj = json.loads(ln)
        except Exception:
            continue
        ts = obj.get("ts", "")
        if not ts:
            continue
        if first_ts is None:
            first_ts = ts
        last_ts = ts
        d = ts[:10]
        if d not in days:
            days.append(d)
    return {"exists": True, "lines": len(lines), "days": sorted(days),
            "first_ts": first_ts, "last_ts": last_ts}


def check_kline5m_latest() -> str | None:
    """kline5m 最新交易日。读取一只样本票的 parquet。"""
    kdir = ROOT / "data" / "kline5m"
    if not kdir.is_dir():
        return None
    sample = "000001.parquet"
    p = kdir / sample
    if not p.exists():
        try:
            p = next(kdir.glob("*.parquet"))
        except Exception:
            return None
    try:
        import pandas as pd
        df = pd.read_parquet(p, columns=["datetime"])
        return str(df["datetime"].max())[:10]
    except Exception:
        try:
            import pandas as pd
            df = pd.read_parquet(p)
            return str(df["datetime"].max())[:10]
        except Exception:
            return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manual", action="store_true", help="手跑模式，不更新状态基线")
    args = ap.parse_args()

    state = load_state()
    issues: list[str] = []
    info: dict = {}

    # 1. institutional-watch 服务
    svc = sh("systemctl is-active institutional-watch 2>/dev/null").strip()
    svc_ok = svc == "active"
    info["service_active"] = svc_ok
    if not svc_ok:
        issues.append(f"institutional-watch 服务非 active（当前: {svc}）")

    # 2. history jsonl
    hs = history_stats()
    info["history"] = hs
    if not hs["exists"]:
        issues.append("institutional_watch_history.jsonl 不存在")
    else:
        if not file_mtime_today(OUT / "institutional_watch_history.jsonl"):
            issues.append("institutional_watch_history.jsonl 今天未更新（mtime 非今日）")
        prev_lines = state.get("prev_lines")
        prev_days = state.get("prev_days")
        if prev_lines is not None and hs["lines"] <= prev_lines:
            issues.append(f"history 行数未增长（上次 {prev_lines} → 现在 {hs['lines']}）")
        n_days = len(hs["days"])
        info["n_trading_days"] = n_days
        info["trading_days_remain"] = max(0, TARGET_TRADING_DAYS - n_days)
        if prev_days is not None and n_days < prev_days:
            issues.append(f"history 积累交易日数回退（上次 {prev_days} → 现在 {n_days}）")

    # 3. 最新快照新鲜度
    for f in ("institutional_watch.json", "fund_strength.json"):
        p = OUT / f
        fresh = p.exists() and file_mtime_today(p)
        info[f"{f}_today"] = fresh
        if not fresh:
            issues.append(f"{f} 今天未更新")

    # 4. kline5m
    k5 = check_kline5m_latest()
    info["kline5m_latest"] = k5
    if k5 != today:
        issues.append(f"kline5m 最新交易日 {k5} != 今天 {today}")

    # 5. score_top10_day 归档
    arch = OUT / "score_top10_day"
    open_ok = (arch / f"{today}_open.json").exists()
    close_ok = (arch / f"{today}_close.json").exists()
    info["score_top10_open"] = open_ok
    info["score_top10_close"] = close_ok
    if not (open_ok and close_ok):
        issues.append(f"score_top10_day 归档缺失: open={open_ok} close={close_ok}")

    # 汇总
    verdict = "OK" if not issues else "ATTENTION"
    n_days = info.get("n_trading_days", 0)
    remain = info.get("trading_days_remain", 0)
    result = {
        "date": today,
        "verdict": verdict,
        "issues": issues,
        "target_trading_days": TARGET_TRADING_DAYS,
        "accumulated_trading_days": n_days,
        "days_to_target": remain,
        "info": info,
    }
    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # 输出报告
    if verdict == "OK":
        log(f"[OK] 数据积累正常 | 已积累 {n_days}/{TARGET_TRADING_DAYS} 个交易日"
            + (f"，还差 {remain} 天" if remain > 0 else "，已达标 ✅"))
    else:
        log(f"[ATTENTION] 数据积累异常: {'; '.join(issues)}")

    # 更新状态基线（manual 不更新）
    if not args.manual:
        save_state({
            "prev_lines": hs.get("lines"),
            "prev_days": len(hs.get("days", [])),
            "prev_date": today,
        })

    sys.exit(0 if verdict == "OK" else 2)


if __name__ == "__main__":
    main()
