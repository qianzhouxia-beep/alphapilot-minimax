#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地 QMT scores 自动同步 (2026-08-08)

服务器每日 09:35 自动生成 output/qmt_scores/{YYYYMMDD}.json，
本脚本在 09:36-09:45 窗口内每分钟轮询一次，一旦发现当天文件即拉取到
本地 C:\\alphapilot\\scores\\{YYYYMMDD}.json，并写入 _last_sync_result.json。

替代 WorkBuddy 手动 _qmt_sync_*.py。由 Windows 计划任务驱动（每天 09:36 触发，
内部轮询至拉到或超时）。空闲可 --once 单次拉取。

用法:
  python scripts/sync_qmt_scores.py --once          # 单次检查并拉取
  python scripts/sync_qmt_scores.py --poll          # 09:36-09:45 每60s轮询（计划任务用）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, date
from pathlib import Path

# pythonw 下无控制台时兜底
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

import paramiko

ROOT = Path(__file__).resolve().parent.parent
LOCAL_DIR = Path(r"C:\alphapilot\scores")
LAST_RESULT = LOCAL_DIR / "_last_sync_result.json"

HOST = "150.158.100.236"
USER = "ubuntu"
# 2026-08-17: 原密钥随 Downloads 迁移丢失，改为自动探测（key.pem 为新位置）
KEY_PATH_CANDIDATES = [
    Path(r"C:\Users\elvisq\key.pem"),
    Path(r"C:\Users\elvisq\Downloads\AlphaPiolot.pem"),
]
KEY_PATH = next((p for p in KEY_PATH_CANDIDATES if p.exists()), KEY_PATH_CANDIDATES[0])
REMOTE_DIR = "/home/ubuntu/alphapilot/output/qmt_scores"

POLL_WINDOW_SEC = 9 * 60  # 09:36 → 09:45，最多轮询 9 分钟
POLL_INTERVAL_SEC = 60


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def today_str() -> str:
    return date.today().strftime("%Y%m%d")


def _connect():
    key = paramiko.RSAKey.from_private_key_file(str(KEY_PATH))
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, pkey=key, timeout=25, banner_timeout=30)
    return c


def fetch_once() -> int:
    """单次检查：若远端当天文件存在则拉取。返回 0=拉到, 1=远端还没有, 2=失败。"""
    today = today_str()
    local_path = LOCAL_DIR / f"{today}.json"
    local_cand = LOCAL_DIR / f"{today}.candidates.json"
    # 已拉过且非空则跳过
    if local_path.exists() and local_path.stat().st_size > 0:
        log(f"已存在 {local_path}，跳过")
        return 0

    try:
        c = _connect()
    except Exception as e:
        log(f"SSH 连接失败: {e}")
        return 2
    try:
        remote = f"{REMOTE_DIR}/{today}.json"
        sftp = c.open_sftp()
        try:
            st = sftp.stat(remote)
            if st.st_size <= 0:
                log(f"远端 {remote} 为空 (0 bytes)")
                return 1
        except FileNotFoundError:
            log(f"远端文件不存在: {remote}")
            return 1
        LOCAL_DIR.mkdir(parents=True, exist_ok=True)
        sftp.get(remote, str(local_path))
        log(f"已拉取 -> {local_path} ({st.st_size} bytes)")

        # 2026-08-09: 同时拉取 Top10 候选池文件（QMT v2.0 先到先得依赖）
        try:
            remote_cand = f"{REMOTE_DIR}/{today}.candidates.json"
            sftp.stat(remote_cand)
            sftp.get(remote_cand, str(local_cand))
            log(f"已拉取候选池 -> {local_cand} ({local_cand.stat().st_size if local_cand.exists() else 0} bytes)")
        except FileNotFoundError:
            log(f"候选池文件不存在: {remote_cand}（QMT v2 将回退到 scores Top10）")
        sftp.close()
    except Exception as e:
        log(f"拉取失败: {e}")
        return 2
    finally:
        c.close()

    # 写 _last_sync_result.json
    try:
        data = json.loads(local_path.read_text(encoding="utf-8"))
        items = list(data.items())
        top3 = items[:3]
        LAST_RESULT.write_text(
            json.dumps(
                {
                    "date": today,
                    "count": len(data),
                    "top3": [[k, round(float(v), 4)] for k, v in top3],
                    "path": str(local_path),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        log(f"Top3: {top3}")
    except Exception as e:
        log(f"写 _last_sync_result 失败: {e}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="单次检查拉取")
    ap.add_argument("--poll", action="store_true", help="09:36-09:45 每分钟轮询")
    args = ap.parse_args()

    wd = date.today().weekday()
    if wd >= 5:
        log(f"非工作日({date.today().strftime('%A')})跳过")
        return 0

    if args.once or not args.poll:
        return fetch_once()

    # --poll：从当前时刻起，最多轮询 POLL_WINDOW_SEC
    deadline = time.time() + POLL_WINDOW_SEC
    n = 0
    while time.time() < deadline:
        n += 1
        log(f"轮询 #{n}")
        rc = fetch_once()
        if rc == 0:
            log("拉取完成")
            return 0
        if rc == 2:
            log("连接/拉取失败，等待重试")
        # rc==1: 远端还没有，等下一轮
        time.sleep(POLL_INTERVAL_SEC)
    log("轮询窗口结束，未拉到当天文件（稍后可手动 --once）")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
