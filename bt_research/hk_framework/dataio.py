#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dataio: HTTP (UA-aware) + atomic JSON IO + trading calendar."""
import json
import os
import tempfile
import time
import urllib.request

import config as C


def get_json(url: str, timeout: int = 20, retries: int = 3, referer: str | None = None):
    """UA-aware GET -> json. 腾讯/东财对 cloud IP 无 UA 会假性限流/400。"""
    last = None
    for i in range(retries):
        req = urllib.request.Request(url, headers={
            "User-Agent": C.UA, "Referer": referer or C.REFERER})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 + i * 2)
    raise RuntimeError(f"GET failed {url[:90]}: {last}")


def load(path: str, default=None):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return default


def save_atomic(obj, path: str):
    """写临时文件再 rename，避免半截文件污染（L1 纪律）。"""
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def append_jsonl(obj, path: str):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def trading_days(kline: dict, ref: str = "00700") -> list[str]:
    """以参考标的的日K日期为交易日历（港股）。"""
    bars = kline.get(ref) or []
    return [b["d"] for b in bars]
