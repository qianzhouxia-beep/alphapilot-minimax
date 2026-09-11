#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cursor: post expansion (regime) result to Issue #6."""
import json
import subprocess
import urllib.request
from pathlib import Path

OWNER = "qianzhouxia-beep"
BODY = Path(__file__).with_name("_post_issue6_trackA_expand_body.md")


def get_token() -> str:
    p = subprocess.run(
        ["git", "credential", "fill"],
        input=b"protocol=https\nhost=github.com\n\n", capture_output=True)
    for line in p.stdout.decode().splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    raise RuntimeError("no token")


def api(url, token, method="GET", body=None):
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "cursor-alphapilot")
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=20) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def main():
    token = get_token()
    st, d = api(
        f"https://api.github.com/repos/{OWNER}/alphapilot-docs/issues/6/comments",
        token, method="POST", body={"body": BODY.read_text(encoding="utf-8")})
    print("POST status:", st)
    print("comment id:", d.get("id"), d.get("html_url", ""))
    if st >= 300:
        print(json.dumps(d, ensure_ascii=False)[:500])


if __name__ == "__main__":
    main()
