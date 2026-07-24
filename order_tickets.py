#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""实盘/半自动下单：订单票据状态机（多租户）。

状态:
  pending_review → approved | rejected | expired
  approved → submitted → filled | failed
  approved → cancelled

P0: 云端只做人审闸门 + 模拟执行已确认单。
P1+: Windows QMT Agent 拉取 approved 单真仓下单。

存储:
  data/order_tickets/{user_id}.json
  站长(owner) → data/order_tickets/owner.json
"""
from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
TICKET_DIR = ROOT / "data" / "order_tickets"
BROKER_DIR = ROOT / "data" / "broker_connections"

STATUSES = (
    "pending_review",
    "approved",
    "rejected",
    "expired",
    "submitted",
    "filled",
    "failed",
    "cancelled",
)

# 支持的券商适配器（商业化预留；真连放到后期）
BROKER_ADAPTERS = {
    "qmt_xtquant": {
        "label": "迅投 QMT / 券商定制 QMT（国金等）",
        "fields": [
            {"key": "account_id", "label": "资金账号", "secret": False},
            {"key": "qmt_userdata_path", "label": "QMT userdata 路径", "secret": False},
            {"key": "session_id", "label": "会话 ID", "secret": False},
            {"key": "trade_host", "label": "交易主机(可选)", "secret": False},
            {"key": "trade_port", "label": "交易端口(可选)", "secret": False},
            {"key": "quote_host", "label": "行情主机(可选)", "secret": False},
            {"key": "quote_port", "label": "行情端口(可选)", "secret": False},
            {"key": "agent_token", "label": "本机 Agent Token", "secret": True},
        ],
        "note": "真仓由客户本机 Agent 连接各自 QMT；云端只存连接配置与已确认订单。",
    },
    "paper_only": {
        "label": "仅模拟盘（不接真仓）",
        "fields": [],
        "note": "默认模式：确认后只在模拟盘成交。",
    },
}


def _uid_key(user: dict | None, user_id: int | str | None = None) -> str:
    if user_id is not None:
        if str(user_id) in ("owner", "0") or user_id == 0:
            return "owner"
        return str(int(user_id))
    if not user:
        return "owner"
    if user.get("is_owner"):
        return "owner"
    return str(int(user["id"]))


def tickets_path(user: dict | None = None, user_id: int | str | None = None) -> Path:
    TICKET_DIR.mkdir(parents=True, exist_ok=True)
    return TICKET_DIR / f"{_uid_key(user, user_id)}.json"


def broker_path(user: dict | None = None, user_id: int | str | None = None) -> Path:
    BROKER_DIR.mkdir(parents=True, exist_ok=True)
    return BROKER_DIR / f"{_uid_key(user, user_id)}.json"


def _load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_tickets(user: dict | None = None, user_id: int | str | None = None) -> dict:
    raw = _load(tickets_path(user, user_id), None)
    if not isinstance(raw, dict):
        return {"user_key": _uid_key(user, user_id), "updated_at": None, "tickets": []}
    raw.setdefault("tickets", [])
    raw.setdefault("user_key", _uid_key(user, user_id))
    return raw


def save_tickets(doc: dict, user: dict | None = None, user_id: int | str | None = None) -> None:
    doc["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    doc["user_key"] = _uid_key(user, user_id)
    _save(tickets_path(user, user_id), doc)


def load_broker_connection(user: dict | None = None, user_id: int | str | None = None) -> dict:
    raw = _load(broker_path(user, user_id), None)
    if not isinstance(raw, dict):
        return {
            "adapter": "paper_only",
            "enabled": False,
            "config": {},
            "status": "not_configured",
            "updated_at": None,
        }
    return raw


def save_broker_connection(
    payload: dict,
    user: dict | None = None,
    user_id: int | str | None = None,
) -> dict:
    cur = load_broker_connection(user, user_id)
    adapter = str(payload.get("adapter") or cur.get("adapter") or "paper_only")
    if adapter not in BROKER_ADAPTERS:
        raise ValueError(f"不支持的适配器: {adapter}")
    cfg = dict(cur.get("config") or {})
    incoming = payload.get("config")
    if isinstance(incoming, dict):
        # 密钥字段：空字符串表示不改
        meta_fields = {f["key"]: f for f in BROKER_ADAPTERS[adapter].get("fields") or []}
        for k, v in incoming.items():
            if k in meta_fields and meta_fields[k].get("secret") and (v is None or v == ""):
                continue
            cfg[k] = v
    out = {
        "adapter": adapter,
        "enabled": bool(payload.get("enabled", cur.get("enabled"))),
        "config": cfg,
        "status": str(payload.get("status") or cur.get("status") or "configured"),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "note": BROKER_ADAPTERS[adapter].get("note"),
    }
    # 永不把明文 agent_token 以外的密码写日志；存储层后续可加密
    _save(broker_path(user, user_id), out)
    # API 返回时脱敏
    return public_broker_connection(out)


def public_broker_connection(doc: dict) -> dict:
    adapter = doc.get("adapter") or "paper_only"
    fields = BROKER_ADAPTERS.get(adapter, {}).get("fields") or []
    cfg = dict(doc.get("config") or {})
    safe = {}
    for f in fields:
        k = f["key"]
        if k not in cfg:
            continue
        if f.get("secret"):
            safe[k] = "***" if cfg.get(k) else ""
        else:
            safe[k] = cfg.get(k)
    return {
        "adapter": adapter,
        "enabled": bool(doc.get("enabled")),
        "config": safe,
        "status": doc.get("status") or "not_configured",
        "updated_at": doc.get("updated_at"),
        "adapters_catalog": [
            {"id": k, "label": v["label"], "fields": v["fields"], "note": v.get("note")}
            for k, v in BROKER_ADAPTERS.items()
        ],
        "note": BROKER_ADAPTERS.get(adapter, {}).get("note"),
    }


def _default_expire_hhmm() -> tuple[int, int]:
    """确认截止：默认当日 14:55。可用 ORDER_TICKET_EXPIRE_HHMM=HH:MM 覆盖。"""
    raw = (os.environ.get("ORDER_TICKET_EXPIRE_HHMM") or "14:55").strip()
    try:
        hh, mm = raw.split(":", 1)
        return int(hh), int(mm)
    except Exception:
        return 14, 55


def create_tickets_from_picks(
    picks: list[dict],
    *,
    user: dict | None = None,
    user_id: int | str | None = None,
    source: str = "morning_live",
    asof: str | None = None,
    position_exposure: float = 1.0,
    expire_hhmm: tuple[int, int] | None = None,
) -> list[dict]:
    """用今日 picks 生成待确认票据；同日同 symbol 未完结则跳过重复。"""
    from datetime import timedelta

    if expire_hhmm is None:
        expire_hhmm = _default_expire_hhmm()

    doc = load_tickets(user, user_id)
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    # 过期：默认当天 14:55（ORDER_TICKET_EXPIRE_HHMM）；已过则顺延次日同刻
    expire_dt = now.replace(
        hour=expire_hhmm[0], minute=expire_hhmm[1], second=0, microsecond=0
    )
    if now >= expire_dt:
        expire_dt = expire_dt + timedelta(days=1)
    expire_at = expire_dt.strftime("%Y-%m-%d %H:%M:%S")

    existing = {
        (t.get("symbol"), str(t.get("asof_date") or "")[:10])
        for t in doc.get("tickets") or []
        if t.get("status") in ("pending_review", "approved", "submitted", "filled")
    }
    created = []
    asof = asof or now.strftime("%Y-%m-%d %H:%M:%S")
    for i, p in enumerate(picks or []):
        sym = str(p.get("symbol") or "")
        if not sym:
            continue
        key = (sym, today)
        if key in existing:
            continue
        tid = f"t_{today.replace('-', '')}_{_bare(sym)}_{uuid.uuid4().hex[:8]}"
        ticket = {
            "id": tid,
            "asof": asof,
            "asof_date": today,
            "status": "pending_review",
            "source": source,
            "symbol": sym,
            "name": p.get("name") or "",
            "side": "buy",
            "score": p.get("score"),
            "research_tier": p.get("research_tier"),
            "live_main_net": p.get("live_main_net") or p.get("main_net"),
            "money_phase_label": p.get("money_phase_label"),
            "suggest_price": p.get("buy_price") or p.get("price"),
            "target_price": p.get("target_price"),
            "stop_price": p.get("stop_price"),
            "position_exposure": position_exposure,
            "rank": p.get("morning_pick_rank") or (i + 1),
            "weight": 1.0,
            "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "expire_at": expire_at,
            "approved_at": None,
            "rejected_at": None,
            "reject_reason": None,
            "exec_mode": "paper",
            "selection_arm": "A0_baseline",
        }
        try:
            from k_execution import ticket_exec_meta

            ticket.update(ticket_exec_meta(p))
        except Exception:
            pass
        doc.setdefault("tickets", []).append(ticket)
        created.append(ticket)
        existing.add(key)
    if created:
        save_tickets(doc, user, user_id)
    return created


def _bare(sym: str) -> str:
    s = str(sym or "").lower().replace("sh", "").replace("sz", "").replace("bj", "")
    return s[-6:] if len(s) >= 6 else s


def expire_stale(user: dict | None = None, user_id: int | str | None = None) -> int:
    doc = load_tickets(user, user_id)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    n = 0
    for t in doc.get("tickets") or []:
        if t.get("status") != "pending_review":
            continue
        exp = t.get("expire_at") or ""
        if exp and now > exp:
            t["status"] = "expired"
            t["expired_at"] = now
            n += 1
    if n:
        save_tickets(doc, user, user_id)
    return n


def list_tickets(
    user: dict | None = None,
    user_id: int | str | None = None,
    *,
    status: str | None = None,
    today_only: bool = False,
) -> list[dict]:
    expire_stale(user, user_id)
    doc = load_tickets(user, user_id)
    today = datetime.now().strftime("%Y-%m-%d")
    out = []
    for t in doc.get("tickets") or []:
        if today_only and str(t.get("asof_date") or "")[:10] != today:
            continue
        if status and t.get("status") != status:
            continue
        out.append(t)
    out.sort(key=lambda x: (x.get("rank") or 99, x.get("created_at") or ""))
    return out


def get_ticket(ticket_id: str, user: dict | None = None, user_id: int | str | None = None) -> dict | None:
    doc = load_tickets(user, user_id)
    for t in doc.get("tickets") or []:
        if t.get("id") == ticket_id:
            return t
    return None


def approve_tickets(
    ticket_ids: list[str],
    *,
    user: dict | None = None,
    user_id: int | str | None = None,
    weights: dict[str, float] | None = None,
) -> list[dict]:
    expire_stale(user, user_id)
    doc = load_tickets(user, user_id)
    weights = weights or {}
    broker = load_broker_connection(user, user_id)
    exec_mode = "live" if broker.get("enabled") and broker.get("adapter") != "paper_only" else "paper"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    done = []
    idset = set(ticket_ids)
    for t in doc.get("tickets") or []:
        if t.get("id") not in idset:
            continue
        if t.get("status") != "pending_review":
            continue
        t["status"] = "approved"
        t["approved_at"] = now
        t["exec_mode"] = exec_mode
        if t["id"] in weights:
            try:
                t["weight"] = max(0.1, min(1.0, float(weights[t["id"]])))
            except (TypeError, ValueError):
                pass
        done.append(t)
    if done:
        save_tickets(doc, user, user_id)
    return done


def reject_tickets(
    ticket_ids: list[str],
    *,
    user: dict | None = None,
    user_id: int | str | None = None,
    reason: str = "",
) -> list[dict]:
    doc = load_tickets(user, user_id)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    done = []
    idset = set(ticket_ids)
    for t in doc.get("tickets") or []:
        if t.get("id") not in idset:
            continue
        if t.get("status") != "pending_review":
            continue
        t["status"] = "rejected"
        t["rejected_at"] = now
        t["reject_reason"] = reason or "user_reject"
        done.append(t)
    if done:
        save_tickets(doc, user, user_id)
    return done


def mark_ticket_status(
    ticket_id: str,
    status: str,
    *,
    user: dict | None = None,
    user_id: int | str | None = None,
    extra: dict | None = None,
) -> dict | None:
    if status not in STATUSES:
        raise ValueError(f"bad status {status}")
    doc = load_tickets(user, user_id)
    for t in doc.get("tickets") or []:
        if t.get("id") != ticket_id:
            continue
        t["status"] = status
        t[f"{status}_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if extra:
            t.update(extra)
        save_tickets(doc, user, user_id)
        return t
    return None


def approved_buy_symbols(user: dict | None = None, user_id: int | str | None = None) -> list[dict]:
    """供 trade_executor：今日已确认、尚未成交的买单。"""
    return [
        t
        for t in list_tickets(user, user_id, today_only=True)
        if t.get("status") == "approved" and t.get("side") == "buy"
    ]


def sync_approved_to_paper_signals(
    *,
    user: dict | None = None,
    user_id: int | str | None = None,
    pt_path: Path | None = None,
    strat_id: str = "v19_daily",
) -> list[dict]:
    """把今日已确认买单写入模拟盘 signals，供 trade_executor 消费。"""
    approved = approved_buy_symbols(user, user_id)
    if pt_path is None:
        if _uid_key(user, user_id) == "owner":
            pt_path = ROOT / "data" / "paper_trading.json"
        else:
            pt_path = ROOT / "data" / "paper_accounts" / f"{_uid_key(user, user_id)}.json"
    if not pt_path.exists():
        return []
    try:
        pt = json.loads(pt_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    signals = []
    for t in approved:
        signals.append(
            {
                "symbol": t.get("symbol"),
                "name": t.get("name") or "",
                "score": t.get("score"),
                "action": "buy",
                "price": float(t.get("suggest_price") or 0),
                "target_price": t.get("target_price"),
                "stop_price": t.get("stop_price"),
                "quantity": 0,
                "strategy_id": strat_id,
                "position_exposure": t.get("position_exposure", 1.0),
                "protocol": "human_approved",
                "ticket_id": t.get("id"),
                "entry_weight": t.get("weight", 1.0),
                "reason": f"人工确认 {t.get('id')} rank={t.get('rank')}",
            }
        )

    found = False
    for s in pt.get("strategies") or []:
        if s.get("id") == strat_id:
            s["signals"] = signals
            found = True
            break
    if not found and signals:
        pt.setdefault("strategies", []).insert(
            0,
            {
                "id": strat_id,
                "name": "VM2.5 人工确认",
                "status": "active",
                "allocated": 500000,
                "used": 0,
                "positions": [],
                "signals": signals,
            },
        )
    pt["approval_gate"] = {
        "enabled": True,
        "pending_n": len(list_tickets(user, user_id, status="pending_review", today_only=True)),
        "approved_n": len(approved),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    pt["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    pt_path.write_text(json.dumps(pt, ensure_ascii=False, indent=2), encoding="utf-8")
    return signals


if __name__ == "__main__":
    demo = [{"symbol": "600519", "name": "贵州茅台", "score": 0.7, "buy_price": 1700}]
    print(create_tickets_from_picks(demo, user_id="owner"))
    print(list_tickets(user_id="owner", today_only=True))
