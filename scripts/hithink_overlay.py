#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同花顺官方数据只读旁路（补缺口、不改选股/不改生产买卖）。

补的字段: 涨停/跌停/炸板池、连板天梯、热股榜、龙虎榜、集合竞价快照。
产出: output/hithink_overlay.json + output/hithink_archive/YYYY-MM-DD.json
任何失败只记日志，不抛到生产管线。

Key 读取顺序:
  HITHINK_FINANCE_API_KEY / FUYAO_TOKEN
  → config/hithink_api_key.conf（权限 0600，不进 git）
  → ~/.hithink_finance_api_key
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BASE = "https://fuyao.aicubes.cn"
CST = timezone(timedelta(hours=8))
OUT = ROOT / "output" / "hithink_overlay.json"
ARCH = ROOT / "output" / "hithink_archive"
KEY_FILE = ROOT / "config" / "hithink_api_key.conf"


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def load_key() -> str:
    for k in ("HITHINK_FINANCE_API_KEY", "FUYAO_TOKEN"):
        v = (os.environ.get(k) or "").strip()
        if v:
            return v
    if KEY_FILE.exists():
        raw = KEY_FILE.read_text(encoding="utf-8", errors="ignore").strip()
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                if k.strip() in ("HITHINK_FINANCE_API_KEY", "FUYAO_TOKEN", "API_KEY"):
                    return v.strip()
            elif line.startswith("sk-"):
                return line
    home = Path.home() / ".hithink_finance_api_key"
    if home.exists():
        return home.read_text(encoding="utf-8", errors="ignore").strip()
    return ""


def last_trade_date() -> tuple[str, int]:
    d = datetime.now(CST).date()
    while d.weekday() >= 5:
        d = d - timedelta(days=1)
    dt = datetime(d.year, d.month, d.day, tzinfo=CST)
    return d.isoformat(), int(dt.timestamp() * 1000)


def get_json(path: str, params: dict | None = None, timeout: int = 20) -> dict:
    q = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
    url = BASE + path + (("?" + q) if q else "")
    req = urllib.request.Request(
        url,
        headers={
            "X-api-key": load_key(),
            "User-Agent": "AlphaPilot-hithink-overlay/1.0",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def safe_call(name: str, path: str, params: dict | None = None) -> dict:
    t0 = time.time()
    try:
        body = get_json(path, params)
        ms = int((time.time() - t0) * 1000)
        code = body.get("code")
        data = body.get("data")
        n = 0
        if isinstance(data, dict):
            n = len(data.get("item") or data.get("stock_items") or [])
        log(f"  {name}: code={code} n={n} {ms}ms")
        return {
            "ok": code == 0,
            "code": code,
            "message": body.get("message"),
            "ms": ms,
            "data": data if code == 0 else None,
        }
    except Exception as e:
        log(f"  {name}: FAIL {type(e).__name__}: {e}")
        return {"ok": False, "error": str(e)[:200], "data": None}


def pick_codes() -> list[str]:
    """从当日生产档案取观察标的（只读，取不到就用空列表）。"""
    codes: list[str] = []

    def add(sym: str) -> None:
        s = str(sym or "").upper().replace("SH", "").replace("SZ", "").replace("BJ", "")
        s = "".join(ch for ch in s if ch.isdigit())[-6:]
        if len(s) != 6:
            return
        if s.startswith("6"):
            ths = s + ".SH"
        elif s.startswith(("0", "3")):
            ths = s + ".SZ"
        else:
            ths = s + ".BJ"
        if ths not in codes:
            codes.append(ths)

    candidates = [
        ROOT / "output" / "daily_picks_archive" / datetime.now(CST).strftime("%Y-%m-%d") / "top2.json",
        ROOT / "output" / "daily_recommend.json",
    ]
    for p in candidates:
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        rows = d.get("picks") or d.get("recommendations") or []
        for it in rows[:30]:
            add(it.get("symbol") or it.get("code") or "")
    return codes[:40]


def run() -> dict:
    log("hithink overlay (read-only, no production writes)")
    key = load_key()
    if not key:
        log("NO KEY — skip")
        return {"ok": False, "error": "no_key"}
    date_s, date_ms = last_trade_date()
    codes = pick_codes()
    log(f"asof={date_s} observe_codes={len(codes)}")

    payload = {
        "asof": datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S"),
        "trade_date": date_s,
        "observe_only": True,
        "does_not_change_selection": True,
        "observe_codes": codes,
        "sources": {},
    }

    payload["sources"]["limit_up_pool"] = safe_call(
        "limit-up-pool",
        "/api/a-share/special-data/limit-up-pool",
        {
            "date_ms": str(date_ms),
            "page": "1",
            "size": "100",
            "sort_field": "continue_day_cnt",
            "sort_dir": "desc",
        },
    )
    payload["sources"]["limit_down_pool"] = safe_call(
        "limit-down-pool",
        "/api/a-share/special-data/limit-down-pool",
        {"date_ms": str(date_ms), "page": "1", "size": "50"},
    )
    payload["sources"]["limit_break_pool"] = safe_call(
        "limit-break-pool",
        "/api/a-share/special-data/limit-break-pool",
        {"date_ms": str(date_ms), "page": "1", "size": "50"},
    )
    payload["sources"]["limit_up_ladder"] = safe_call(
        "limit-up-ladder",
        "/api/a-share/special-data/limit-up-ladder",
    )
    payload["sources"]["hot_stock_list"] = safe_call(
        "hot-stock-list",
        "/api/a-share/special-data/hot-stock-list",
        {"period": "day"},
    )
    payload["sources"]["dragon_tiger"] = safe_call(
        "dragon-tiger-list",
        "/api/a-share/special-data/dragon-tiger-list",
        {"board_type": "all", "date": date_s},
    )
    if codes:
        payload["sources"]["auction_snapshot"] = safe_call(
            "auction-snapshot",
            "/api/a-share/auction/snapshot",
            {"thscodes": ",".join(codes)},
        )
        payload["sources"]["prices_snapshot"] = safe_call(
            "prices-snapshot",
            "/api/a-share/prices/snapshot",
            {"thscodes": ",".join(codes)},
        )
        payload["sources"]["anomaly_stock"] = safe_call(
            "anomaly-stock",
            "/api/a-share/special-data/anomaly-analysis-stock",
            {"thscodes": ",".join(codes[:50])},
        )

    ok_n = sum(1 for v in payload["sources"].values() if v.get("ok"))
    payload["ok"] = ok_n > 0
    payload["ok_sources"] = ok_n
    payload["n_sources"] = len(payload["sources"])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    ARCH.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    OUT.write_text(text, encoding="utf-8")
    (ARCH / f"{date_s}.json").write_text(text, encoding="utf-8")
    log(f"wrote {OUT} ok_sources={ok_n}/{payload['n_sources']}")
    return payload


if __name__ == "__main__":
    p = run()
    raise SystemExit(0 if p.get("ok") else 1)
