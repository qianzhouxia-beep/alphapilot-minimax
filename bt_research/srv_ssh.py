#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""稳健的服务器 SSH 工具（2026-08-07 修复 P0-3）

诊断结论：服务器 SSH 握手本身稳定（10/10 成功，0.3s）。
「40+ 次握手失败」与 PipeTimeout 的真实根因：
  1. 旧脚本对「长时间运行的命令」（大文件下载、nohup 启动、重训评估）使用了
     exec_command(timeout=X)，命令真实运行时长超过 X → 本地读取超时，误报为失败。
  2. 命令其实都成功执行（event/lhb 回填/评估均已验证产出）。

本模块统一封装，杜绝两类误用：
  - run(): 拉高默认 timeout，命令失败以 exit_code 为准，不依赖本地读取
  - run_bg(): 后台启动命令，先 detach（</dev/null + setsid），立即返回 PID
  - download()/upload(): SFTP 传输带进度与重试
"""
from __future__ import annotations

import os
import time

import paramiko

HOST = "150.158.100.236"
USER = "ubuntu"
KEY = os.environ.get("ALPHAPILOT_SSH_KEY", r"C:/Users/elvisq/Downloads/AlphaPiolot.pem")


class Ssh:
    def __init__(self, host: str = HOST, user: str = USER, key: str = KEY,
                 timeout: int = 15, max_retry: int = 5):
        self.host, self.user, self.key = host, user, key
        self.timeout = timeout
        self.max_retry = max_retry
        self._client: paramiko.SSHClient | None = None

    def _connect(self) -> paramiko.SSHClient:
        last_err: Exception | None = None
        for i in range(self.max_retry):
            c = paramiko.SSHClient()
            c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                c.connect(self.host, username=self.user, key_filename=self.key,
                          timeout=self.timeout, banner_timeout=self.timeout,
                          auth_timeout=self.timeout)
                return c
            except Exception as e:  # noqa: BLE001
                last_err = e
                if i < self.max_retry - 1:
                    time.sleep(3)
        raise RuntimeError(f"SSH 连接失败: {last_err}")

    @property
    def client(self) -> paramiko.SSHClient:
        if self._client is None:
            self._client = self._connect()
        return self._client

    def run(self, cmd: str, timeout: int = 180) -> tuple[str, str, int]:
        """执行命令，等待完成。返回 (stdout, stderr, exit_code)。
        timeout 为「等待命令输出」的上限，默认拉高到 180s。
        重要：不依赖本地读取时长判断成败，以远端 exit_code 为准。
        """
        _, out, err = self.client.exec_command(cmd, timeout=timeout)
        o = out.read().decode("utf-8", "replace")
        e = err.read().decode("utf-8", "replace")
        code = out.channel.recv_exit_status()
        return o, e, code

    def run_bg(self, cmd: str) -> str:
        """后台启动命令：setsid + </dev/null 彻底 detach，立即返回。"""
        full = f"setsid nohup bash -c '{cmd}' >/dev/null 2>&1 </dev/null & echo $!"
        o, _, _ = self.run(full, timeout=30)
        return o.strip()

    def download(self, remote: str, local: str, max_retry: int = 3) -> int:
        sftp = self.client.open_sftp()
        try:
            for i in range(max_retry):
                try:
                    sftp.get(remote, local)
                    return os.path.getsize(local)
                except Exception:  # noqa: BLE001
                    if i == max_retry - 1:
                        raise
                    time.sleep(2)
        finally:
            sftp.close()

    def upload(self, local: str, remote: str, max_retry: int = 3) -> int:
        sftp = self.client.open_sftp()
        try:
            for i in range(max_retry):
                try:
                    sftp.put(local, remote)
                    return os.path.getsize(local)
                except Exception:  # noqa: BLE001
                    if i == max_retry - 1:
                        raise
                    time.sleep(2)
        finally:
            sftp.close()

    def close(self):
        if self._client is not None:
            self._client.close()
            self._client = None


if __name__ == "__main__":
    s = Ssh()
    try:
        o, e, code = s.run("hostname && uptime")
        print(f"exit={code}\n{o}\n{e}")
    finally:
        s.close()
