#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sg_util: 新加坡服务器连接助手（凭据从既有本地文件读取，不在命令行出现明文）。
用法: from sg_util import client, run
"""
import pathlib
import re
import time

import paramiko

HOST = "43.156.119.47"
USER = "ubuntu"
_SRC = pathlib.Path(__file__).parent / "_crypto_probe" / "_deploy_atomic.py"


def get_pass() -> str:
    import os
    if os.environ.get("SG_PASS"):
        return os.environ["SG_PASS"]
    m = re.search(r'PASSWORD\s*=\s*"([^"]+)"', _SRC.read_text(encoding="utf-8"))
    if not m:
        raise RuntimeError("SG password not found")
    return m.group(1)


def client(retries: int = 6):
    pw = get_pass()
    for i in range(retries):
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            c.connect(HOST, username=USER, password=pw, timeout=25,
                      banner_timeout=25, auth_timeout=25)
            return c
        except Exception:
            time.sleep(4 + i * 3)
    raise RuntimeError("sg unreachable")


def run(sg, cmd: str, timeout: int = 60):
    _, so, se = sg.exec_command(cmd, timeout=timeout)
    ec = so.channel.recv_exit_status()
    return so.read().decode("utf-8", "replace"), se.read().decode("utf-8", "replace"), ec
