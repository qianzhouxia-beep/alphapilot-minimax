#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""个人账号：注册/登录 + JWT（供收藏夹、模拟盘私有化）。"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "users.db"
JWT_SECRET = os.environ.get("AUTH_JWT_SECRET", "").strip() or "alphapilot-dev-secret-change-me"
JWT_TTL_SEC = int(os.environ.get("AUTH_JWT_TTL_SEC", str(30 * 24 * 3600)))
# 系统模拟盘 + 旧全局收藏全部归 root 管理员
OWNER_EMAIL = (
    os.environ.get("PRIVATE_OWNER_EMAIL", "").strip().lower()
    or os.environ.get("PAPER_OWNER_EMAIL", "").strip().lower()
    or "root@alphapilot.local"
)
OWNER_BOOTSTRAP_PASSWORD = (
    os.environ.get("OWNER_BOOTSTRAP_PASSWORD", "").strip()
    or os.environ.get("ROOT_ADMIN_PASSWORD", "").strip()
    or "AlphaPilotRoot2026!"
)


def _b64url(data: bytes) -> str:
    return urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return urlsafe_b64decode(s + pad)


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    return c


def init_users_db() -> None:
    c = _conn()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL DEFAULT '',
            plan TEXT NOT NULL DEFAULT 'free',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    c.commit()
    c.close()


def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return f"pbkdf2_sha256${_b64url(salt)}${_b64url(dk)}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt_b64, hash_b64 = stored.split("$", 2)
        if algo != "pbkdf2_sha256":
            return False
        salt = _b64url_decode(salt_b64)
        expect = _b64url_decode(hash_b64)
        got = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
        return hmac.compare_digest(got, expect)
    except Exception:
        return False


def create_user(email: str, password: str, full_name: str = "") -> dict[str, Any]:
    init_users_db()
    email = email.strip().lower()
    if "@" not in email:
        raise ValueError("邮箱格式不正确")
    if len(password) < 8:
        raise ValueError("密码至少 8 位")
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    c = _conn()
    try:
        cur = c.execute(
            "INSERT INTO users(email, password_hash, full_name, plan, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?)",
            (email, _hash_password(password), full_name.strip() or email.split("@")[0], "free", now, now),
        )
        c.commit()
        uid = int(cur.lastrowid)
    except sqlite3.IntegrityError:
        raise ValueError("该邮箱已注册")
    finally:
        c.close()
    return get_user_by_id(uid)


def authenticate(email: str, password: str) -> dict[str, Any] | None:
    init_users_db()
    email = email.strip().lower()
    c = _conn()
    row = c.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    c.close()
    if not row:
        return None
    if not _verify_password(password, row["password_hash"]):
        return None
    return _row_user(row)


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    init_users_db()
    c = _conn()
    row = c.execute("SELECT * FROM users WHERE id = ?", (int(user_id),)).fetchone()
    c.close()
    return _row_user(row) if row else None


def get_user_by_email(email: str) -> dict[str, Any] | None:
    init_users_db()
    c = _conn()
    row = c.execute(
        "SELECT * FROM users WHERE email = ?", (email.strip().lower(),)
    ).fetchone()
    c.close()
    return _row_user(row) if row else None


def _row_user(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "email": row["email"],
        "full_name": row["full_name"] or "",
        "plan": row["plan"] or "free",
        "created_at": row["created_at"],
        "is_owner": (row["email"] or "").lower() == OWNER_EMAIL,
    }


def issue_token(user: dict[str, Any]) -> str:
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    now = int(time.time())
    payload = {
        "sub": int(user["id"]),
        "email": user["email"],
        "iat": now,
        "exp": now + JWT_TTL_SEC,
    }
    body = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64url(
        hmac.new(JWT_SECRET.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    )
    return f"{header}.{body}.{sig}"


def verify_token(token: str) -> dict[str, Any] | None:
    try:
        header_b64, body_b64, sig_b64 = token.split(".")
        expect = _b64url(
            hmac.new(
                JWT_SECRET.encode(),
                f"{header_b64}.{body_b64}".encode(),
                hashlib.sha256,
            ).digest()
        )
        if not hmac.compare_digest(expect, sig_b64):
            return None
        payload = json.loads(_b64url_decode(body_b64))
        if int(payload.get("exp") or 0) < int(time.time()):
            return None
        user = get_user_by_id(int(payload["sub"]))
        return user
    except Exception:
        return None


def ensure_owner_user() -> dict[str, Any]:
    """确保 root 管理员存在；不存在则用引导密码创建。"""
    init_users_db()
    existing = get_user_by_email(OWNER_EMAIL)
    if existing:
        return existing
    try:
        return create_user(OWNER_EMAIL, OWNER_BOOTSTRAP_PASSWORD, full_name="root")
    except ValueError:
        # 并发创建竞态
        again = get_user_by_email(OWNER_EMAIL)
        if again:
            return again
        raise


def ensure_owner_placeholder() -> None:
    """启动时保证 root 管理员可用。"""
    ensure_owner_user()


def reset_owner_password(password: str | None = None) -> dict[str, Any]:
    """重置 root 密码（部署/运维脚本用）。"""
    init_users_db()
    pwd = (password or OWNER_BOOTSTRAP_PASSWORD).strip()
    if len(pwd) < 8:
        raise ValueError("密码至少 8 位")
    user = ensure_owner_user()
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    c = _conn()
    c.execute(
        "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
        (_hash_password(pwd), now, int(user["id"])),
    )
    c.commit()
    c.close()
    return get_user_by_id(int(user["id"])) or user
