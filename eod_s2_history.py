"""S2 尾盘狙击选股历史归档与查询。"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent
HISTORY_DIR = ROOT / "data" / "eod_s2_history"
CURRENT_FILE = ROOT / "output" / "eod_s2_picks.json"
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _ensure_dir() -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def normalize_payload(data: dict[str, Any] | None) -> dict[str, Any]:
    """保证 payload 含 date / generated_at 等追踪字段。"""
    payload = dict(data or {})
    date = str(payload.get("date") or "").strip()
    if not _DATE_RE.match(date):
        gen = str(payload.get("generated_at") or "")
        if len(gen) >= 10 and _DATE_RE.match(gen[:10]):
            date = gen[:10]
        else:
            date = datetime.now().strftime("%Y-%m-%d")
        payload["date"] = date
    if not payload.get("generated_at"):
        payload["generated_at"] = datetime.now().isoformat()
    if not payload.get("generated_time"):
        try:
            payload["generated_time"] = datetime.fromisoformat(
                str(payload["generated_at"]).replace("Z", "")
            ).strftime("%H:%M")
        except Exception:
            payload["generated_time"] = datetime.now().strftime("%H:%M")
    payload.setdefault("strategy", "S2最优版")
    payload.setdefault("picks", [])
    return payload


def history_path(date: str) -> Path:
    return HISTORY_DIR / f"{date}.json"


def save_history(payload: dict[str, Any]) -> Path:
    """按交易日覆盖写入历史归档。"""
    payload = normalize_payload(payload)
    date = payload["date"]
    _ensure_dir()
    path = history_path(date)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    return path


def load_history(date: str) -> Optional[dict[str, Any]]:
    if not _DATE_RE.match(date or ""):
        return None
    path = history_path(date)
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return normalize_payload(json.load(f))
    except Exception:
        return None


def list_history_dates(limit: int = 90) -> list[str]:
    _ensure_dir()
    dates = []
    for p in HISTORY_DIR.glob("*.json"):
        stem = p.stem
        if _DATE_RE.match(stem):
            dates.append(stem)
    dates.sort(reverse=True)
    return dates[: max(1, min(int(limit or 90), 365))]


def load_current() -> Optional[dict[str, Any]]:
    if not CURRENT_FILE.is_file():
        return None
    try:
        with open(CURRENT_FILE, encoding="utf-8") as f:
            return normalize_payload(json.load(f))
    except Exception:
        return None


def archive_current_if_needed() -> Optional[str]:
    """把当前 output/eod_s2_picks.json 补进历史（不覆盖已有归档）。"""
    cur = load_current()
    if not cur:
        return None
    date = cur["date"]
    path = history_path(date)
    if path.is_file():
        return date
    save_history(cur)
    return date


def query_history(
    date: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 90,
) -> dict[str, Any]:
    """
    - 指定 date: 返回单日详情
    - 否则返回日期列表；若带 from/to 则过滤后附带每日摘要
    """
    archive_current_if_needed()

    if date:
        if not _DATE_RE.match(date):
            return {"error": "invalid_date", "message": "日期格式应为 YYYY-MM-DD", "date": date}
        payload = load_history(date)
        if not payload:
            # 当日若即当前文件也允许命中
            cur = load_current()
            if cur and cur.get("date") == date:
                payload = cur
        if not payload:
            return {"date": date, "picks": [], "note": "该日无尾盘狙击记录", "found": False}
        payload = dict(payload)
        payload["found"] = True
        return payload

    dates = list_history_dates(limit=365)
    if date_from and _DATE_RE.match(date_from):
        dates = [d for d in dates if d >= date_from]
    if date_to and _DATE_RE.match(date_to):
        dates = [d for d in dates if d <= date_to]
    dates = dates[: max(1, min(int(limit or 90), 365))]

    days = []
    for d in dates:
        payload = load_history(d) or {}
        picks = payload.get("picks") or []
        top = picks[0] if picks else None
        days.append(
            {
                "date": d,
                "generated_at": payload.get("generated_at"),
                "generated_time": payload.get("generated_time"),
                "total_passed": payload.get("total_passed"),
                "pick_count": len(picks),
                "top1": (
                    {
                        "symbol": top.get("symbol"),
                        "name": top.get("name"),
                        "price": top.get("price"),
                        "change_pct": top.get("change_pct"),
                    }
                    if top
                    else None
                ),
                "note": payload.get("note"),
            }
        )

    return {
        "dates": dates,
        "days": days,
        "count": len(dates),
        "from": date_from,
        "to": date_to,
    }
