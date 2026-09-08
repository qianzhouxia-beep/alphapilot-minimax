#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地 Windows 弹窗 — 盘中机构资金异动通知。

连接服务器读取 output/institutional_watch.json，
发现新的 high/medium 告警 → Windows toast 弹窗。
已弹过的告警按 (symbol, type, main_net) 去重，不重复打扰。

用法:
  python scripts/local_watch_notify.py            # 单次轮询（供 Windows 任务计划每分钟调）
  python scripts/local_watch_notify.py --loop --interval 60  # 常驻

需要: pip install win11toast paramiko
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# pythonw 下无控制台，stdout/stderr 为 None → 重定向到 devnull，避免 print 崩溃
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

import paramiko

ROOT = Path(__file__).resolve().parent.parent
SEEN_PATH = ROOT / ".watch_notify_seen.json"

HOST = "150.158.100.236"
USER = "ubuntu"
PEM = Path(r"C:\Users\elvisq\Downloads\AlphaPiolot.pem")
REMOTE_STATE = "/home/ubuntu/alphapilot/output/institutional_watch.json"

SEVERITY_EMOJI = {"high": "🚨", "medium": "⚠️", "info": "ℹ️"}


def fetch_remote_alerts() -> list[dict]:
    """SSH 读服务器告警文件。"""
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, key_filename=str(PEM), timeout=20, banner_timeout=30)
    try:
        stdin, stdout, stderr = c.exec_command(f"cat {REMOTE_STATE}", timeout=30)
        raw = stdout.read().decode("utf-8", "replace")
        st = json.loads(raw)
        return st.get("alerts") or []
    finally:
        c.close()


def load_seen() -> set[tuple]:
    if SEEN_PATH.exists():
        try:
            return {tuple(x) for x in json.loads(SEEN_PATH.read_text(encoding="utf-8"))}
        except Exception:
            return set()
    return set()


def save_seen(seen: set[tuple]) -> None:
    SEEN_PATH.write_text(
        json.dumps([list(x) for x in seen], ensure_ascii=False), encoding="utf-8"
    )


def toast(title: str, msg: str, urgency: str = "default") -> None:
    try:
        from win11toast import toast as w11toast

        w11toast(title, msg, duration="short" if urgency == "default" else "long")
    except Exception as e:
        print(f"[toast] 失败: {e}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--interval", type=int, default=60)
    args = ap.parse_args()

    def once() -> int:
        try:
            alerts = fetch_remote_alerts()
        except Exception as e:
            print(f"[watch_notify] 连接失败: {e}", flush=True)
            return 1

        seen = load_seen()
        fresh: list[dict] = []
        for a in alerts:
            key = (a.get("symbol", ""), a.get("type", ""), a.get("main_net", 0))
            if key not in seen and a.get("severity") in ("high", "medium"):
                fresh.append(a)
                seen.add(key)

        for a in fresh:
            emoji = SEVERITY_EMOJI.get(a.get("severity", ""), "🔔")
            toast(
                f"{emoji} 主力资金异动 · {a.get('name', '')}",
                f"{a.get('msg', '')}",
                urgency="long" if a.get("severity") == "high" else "default",
            )
            print(f"[{time.strftime('%H:%M:%S')}] {emoji} {a.get('msg')}", flush=True)

        if seen:
            save_seen(seen)
        return 0

    if not args.loop:
        return once()

    while True:
        try:
            once()
        except Exception as e:
            print(f"[watch_notify] 错误: {e}", flush=True)
        time.sleep(max(20, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
