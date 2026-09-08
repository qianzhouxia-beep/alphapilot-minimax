#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Upload C:/alphapilot/fusion_closed_trades.jsonl to the Shanghai server.

QMT/TDX 买卖模型把平仓写在本机；选股模型 16:15 cron 只读服务器
/home/ubuntu/alphapilot/data/fusion_closed_trades.jsonl。
Linux 上的 C:/alphapilot/... 路径不存在，所以必须在 16:15 之前把本机 jsonl 推上去。

Merge by (source, symbol, sell_time, action, volume). Does not delete server rows.

Suggested Windows task: weekdays 16:10.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import paramiko

HOST = "150.158.100.236"
KEY_CANDIDATES = [
    r"C:\Users\elvisq\Downloads\AlphaPiolot.pem",
    r"C:\Users\elvisq\key.pem",
]
LOCAL = Path(r"C:\alphapilot\fusion_closed_trades.jsonl")
REMOTE = "/home/ubuntu/alphapilot/data/fusion_closed_trades.jsonl"
REPO = Path(__file__).resolve().parents[1] / "data" / "fusion_closed_trades.jsonl"


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            t = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(t, dict):
            out.append(t)
    return out


def _key(t: dict) -> tuple:
    return (
        t.get("source"),
        t.get("symbol"),
        t.get("sell_time"),
        t.get("action"),
        t.get("volume"),
    )


def _merge(a: list[dict], b: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for t in a + b:
        k = _key(t)
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
    return out


def _connect():
    last = None
    for kp in KEY_CANDIDATES:
        if not os.path.exists(kp):
            continue
        try:
            k = paramiko.RSAKey.from_private_key_file(kp)
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(HOST, username="ubuntu", pkey=k, timeout=20)
            return ssh
        except Exception as e:
            last = e
    raise RuntimeError(f"ssh failed: {last}")


def main() -> int:
    local_rows = _merge(_rows(LOCAL), _rows(REPO))
    ssh = _connect()
    sftp = ssh.open_sftp()
    remote_rows = []
    try:
        with sftp.open(REMOTE, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    t = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(t, dict):
                    remote_rows.append(t)
    except OSError:
        remote_rows = []
    merged = _merge(remote_rows, local_rows)
    text = "".join(json.dumps(r, ensure_ascii=True) + "\n" for r in merged)
    upload = LOCAL.parent / "fusion_closed_trades.jsonl.upload"
    upload.write_text(text, encoding="utf-8")
    sftp.put(str(upload), REMOTE)
    sftp.close()
    ssh.close()
    try:
        upload.unlink()
    except OSError:
        pass
    LOCAL.parent.mkdir(parents=True, exist_ok=True)
    LOCAL.write_text(text, encoding="utf-8")
    REPO.parent.mkdir(parents=True, exist_ok=True)
    REPO.write_text(text, encoding="utf-8")
    print(f"synced n={len(merged)} -> {REMOTE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
