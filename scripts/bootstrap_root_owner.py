#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""创建/重置 root 管理员，并把遗留收藏划归该账号。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from auth_users import (  # noqa: E402
    OWNER_EMAIL,
    OWNER_BOOTSTRAP_PASSWORD,
    ensure_owner_user,
    reset_owner_password,
)
from watchlist import claim_legacy_watchlist, get_watchlist  # noqa: E402


def main() -> None:
    reset = "--reset-password" in sys.argv
    if reset:
        user = reset_owner_password()
    else:
        user = ensure_owner_user()
    claimed = claim_legacy_watchlist(int(user["id"]))
    items = get_watchlist("all", user_id=int(user["id"]))
    print(
        json.dumps(
            {
                "owner_email": OWNER_EMAIL,
                "owner_id": user["id"],
                "password_hint": "env OWNER_BOOTSTRAP_PASSWORD / default AlphaPilotRoot2026!",
                "reset_password": reset,
                "claimed_legacy_rows": claimed,
                "watchlist_count": len(items),
                "is_owner": user.get("is_owner"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
