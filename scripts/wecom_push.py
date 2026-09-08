#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""企业微信(WeCom)群机器人推送。

用法:
  from wecom_push import send_wecom, send_markdown
  send_markdown("# 标题\n\n正文")

配置: Webhook 从环境变量 WECOM_WEBHOOK 读取。
  - 若设置了 WECOM_WEBHOOK_FILE，则从该文件读取（cron 不方便传 env 时用）
  - 未配置时 send_* 返回 (False, "no_webhook")，不抛异常（不影响主流程）
"""
from __future__ import annotations

import json
import mimetypes
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path


def _webhook() -> str:
    """解析 webhook：优先 env，其次 WECOM_WEBHOOK_FILE，最后默认配置路径。"""
    w = (os.environ.get("WECOM_WEBHOOK") or "").strip()
    if w:
        return w
    fp = os.environ.get("WECOM_WEBHOOK_FILE") or ""
    if not fp:
        # cron 无需设 env：默认回退到项目配置（权限 0600）
        fp = str(Path(__file__).resolve().parents[1] / "config" / "wecom_webhook.conf")
    if fp and Path(fp).exists():
        raw = Path(fp).read_text(encoding="utf-8", errors="ignore").strip()
        for line in raw.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if k.strip() == "WECOM_WEBHOOK":
                    return v.strip()
            elif line.startswith("https://qyapi.weixin.qq.com"):
                return line
    return ""


def _post(payload: dict, timeout: int = 10) -> tuple[bool, str]:
    """POST 到企业微信 webhook。返回 (ok, err)。"""
    url = _webhook()
    if not url:
        return False, "no_webhook"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "ignore")
            obj = json.loads(body) if body else {}
        if obj.get("errcode") in (0, None):
            return True, "ok"
        # 频率限制等，退避重试一次
        if obj.get("errcode") == 45009:
            time.sleep(3)
            with urllib.request.urlopen(req, timeout=timeout) as resp2:
                body2 = resp2.read().decode("utf-8", "ignore")
                obj2 = json.loads(body2) if body2 else {}
            if obj2.get("errcode") in (0, None):
                return True, "ok"
            return False, f"errcode={obj2.get('errcode')} {obj2.get('errmsg')}"
        return False, f"errcode={obj.get('errcode')} {obj.get('errmsg')}"
    except Exception as e:
        return False, str(e)


def send_text(content: str) -> tuple[bool, str]:
    return _post({"msgtype": "text", "text": {"content": content}})


def send_markdown(content: str) -> tuple[bool, str]:
    """markdown 消息。企业微信 markdown 支持 #/##/加粗/列表等，最多 4096 字节。"""
    return _post({"msgtype": "markdown", "markdown": {"content": content}})


def _webhook_key() -> str:
    """从 webhook URL 中提取 key。"""
    url = _webhook()
    if not url:
        return ""
    q = urllib.parse.urlparse(url).query
    return urllib.parse.parse_qs(q).get("key", [""])[0]


def _upload_media(file_path: Path, timeout: int = 30) -> tuple[bool, str]:
    """上传文件到企业微信，返回 (ok, media_id 或错误)。文件需 <= 20MB。"""
    key = _webhook_key()
    if not key:
        return False, "no_webhook"
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/upload_media?key={key}&type=file"

    boundary = f"----WeComBoundary{int(time.time() * 1000)}"
    filename = file_path.name
    ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    data = file_path.read_bytes()

    body = bytearray()
    body.extend(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="media"; filename="{filename}"\r\n'
            f"Content-Type: {ctype}\r\n\r\n"
        ).encode("utf-8")
    )
    body.extend(data)
    body.extend(f"\r\n--{boundary}--\r\n".encode("utf-8"))

    req = urllib.request.Request(
        url,
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", "ignore")
        obj = json.loads(text) if text else {}
        if obj.get("errcode") in (0, None) and obj.get("media_id"):
            return True, obj["media_id"]
        return False, f"upload errcode={obj.get('errcode')} {obj.get('errmsg')}"
    except Exception as e:
        return False, str(e)


def send_file(file_path) -> tuple[bool, str]:
    """上传并发送文件到企业微信群。返回 (ok, err)。"""
    fp = Path(file_path)
    if not fp.exists():
        return False, f"file_not_found:{fp.name}"
    if fp.stat().st_size > 20 * 1024 * 1024:
        return False, "file_too_large(>20MB)"
    ok, media_id = _upload_media(fp)
    if not ok:
        return False, media_id
    return _post({"msgtype": "file", "file": {"media_id": media_id}})


if __name__ == "__main__":
    ok, err = send_text("WeCom push module test")
    print(f"send_text -> ok={ok} err={err}")
