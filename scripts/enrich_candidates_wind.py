#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 Wind MCP 拉取候选股当日/近5日主力净流入 + PE + 分档，写入 data/wind_candidate_flow.json。

设计（B′）：
  - 只打日频池 / 尾盘池 / 持仓 / 自选，控制积分
  - 盘中可多次刷新（midday / pre_eod），提升实时精度
  - money_flow_gate 优先读本文件覆盖 main_net / main_net_5d / pe_ttm

用法:
  python3 scripts/enrich_candidates_wind.py
  python3 scripts/enrich_candidates_wind.py --limit 80 --session pre_eod
  python3 scripts/enrich_candidates_wind.py --codes 600929,000737 --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "wind_candidate_flow.json"
STOCK_EP = "https://mcp.wind.com.cn/vserver_stock_data/mcp/"
# 主力 + 机构/大户/中户/散户分档（盘中精度）
INDEXES = (
    "中文简称,最新成交价,涨跌幅,市盈率(TTM),"
    "当日主力净流入额,当日主力净流入占比,"
    "近5日主力净流入额,近5日主力净流入占比,"
    "该日机构资金净流入额,该日大户资金净流入额,该日中户资金净流入额,该日散户资金净流入额"
)


def _bare(sym: str) -> str:
    s = str(sym or "").lower().replace("sh", "").replace("sz", "").replace("bj", "")
    return re.sub(r"\D", "", s)[-6:]


def _windcode(bare: str) -> str:
    b = _bare(bare)
    if not b or len(b) != 6:
        return b
    if b.startswith(("5", "6", "9")):
        return f"{b}.SH"
    if b.startswith(("0", "1", "2", "3")):
        return f"{b}.SZ"
    if b.startswith(("4", "8")):
        return f"{b}.BJ"
    return f"{b}.SH"


def load_api_key() -> str:
    env = (os.environ.get("WIND_API_KEY") or "").strip()
    if env:
        return env
    home = Path.home()
    cfg = home / ".wind-aifinmarket" / "config"
    if cfg.exists():
        for line in cfg.read_text(encoding="utf-8").splitlines():
            line = line.strip().lstrip("\ufeff")
            if line.startswith("export "):
                line = line[7:].strip()
            if line.startswith("WIND_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    local = home / ".agents" / "skills" / "wind-mcp-skill" / "config.json"
    if local.exists():
        try:
            j = json.loads(local.read_text(encoding="utf-8"))
            k = (j.get("wind_api_key") or "").strip()
            if k:
                return k
        except Exception:
            pass
    raise SystemExit("WIND_API_KEY 未配置（环境变量或 ~/.wind-aifinmarket/config）")


def _parse_sse_or_json(text: str) -> dict:
    t = text.strip()
    if t.startswith("{"):
        return json.loads(t)
    last = None
    for line in text.splitlines():
        if line.startswith("data: "):
            last = line[6:]
    if not last:
        raise RuntimeError(f"无法解析 Wind 响应: {text[:200]}")
    return json.loads(last)


def mcp_call(api_key: str, tool_name: str, arguments: dict, timeout: float = 60.0) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }

    def _post(method: str, params: dict) -> dict:
        body = json.dumps(
            {"jsonrpc": "2.0", "id": int(time.time() * 1000), "method": method, "params": params}
        ).encode("utf-8")
        req = urllib.request.Request(STOCK_EP, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        payload = _parse_sse_or_json(raw)
        if payload.get("error"):
            raise RuntimeError(payload["error"])
        return payload.get("result") or {}

    _post(
        "initialize",
        {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "alphapilot-enrich", "version": "1.1"},
        },
    )
    return _post(
        "tools/call",
        {"name": tool_name, "arguments": arguments, "_meta": {"clientVersion": "1.1"}},
    )


def _extract_row(result: dict) -> dict:
    content = result.get("content") if isinstance(result, dict) else None
    text = None
    if isinstance(content, list) and content:
        text = content[0].get("text")
    if not text and isinstance(result, dict):
        text = result.get("text")
    if not text:
        return {}
    try:
        inner = json.loads(text) if isinstance(text, str) else text
    except Exception:
        return {"raw": text}
    if isinstance(inner, dict) and inner.get("error"):
        return {"error": str(inner.get("error"))}
    data = (inner or {}).get("data") or inner
    cols = data.get("columns") if isinstance(data, dict) else None
    rows = data.get("rows") if isinstance(data, dict) else None
    if not cols or not rows:
        return {"raw": data}
    names = [c.get("name") if isinstance(c, dict) else str(c) for c in cols]
    row0 = rows[0]
    return {names[i]: row0[i] for i in range(min(len(names), len(row0)))}


def _f(v):
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _append_codes(codes: list[str], raw) -> None:
    if isinstance(raw, dict):
        codes.append(_bare(raw.get("code") or raw.get("symbol")))
    else:
        codes.append(_bare(raw))


def collect_symbols(extra: list[str] | None = None) -> list[str]:
    """优先级：持仓 → 日频池 → 尾盘池 → 启动池 → 旁路样本 → 自选。"""
    priority: list[str] = []
    rest: list[str] = []

    def add_pri(c: str):
        c = _bare(c)
        if c and len(c) == 6 and c not in priority and c not in rest:
            priority.append(c)

    def add_rest(c: str):
        c = _bare(c)
        if c and len(c) == 6 and c not in priority and c not in rest:
            rest.append(c)

    # 持仓
    pt = ROOT / "data" / "paper_trading.json"
    if pt.exists():
        try:
            d = json.loads(pt.read_text(encoding="utf-8"))
        except Exception:
            d = {}
        for pos in (d.get("positions") or {}).values() if isinstance(d.get("positions"), dict) else []:
            if isinstance(pos, dict):
                add_pri(pos.get("symbol") or pos.get("code"))
        for bucket in ("v19", "s2", "daily", "eod", "strategies"):
            b = d.get(bucket) or {}
            if isinstance(b, dict) and "positions" in b:
                for pos in b.get("positions") or []:
                    if isinstance(pos, dict):
                        add_pri(pos.get("symbol") or pos.get("code"))
            elif isinstance(b, dict):
                for _k, v in b.items():
                    if isinstance(v, dict) and isinstance(v.get("positions"), (list, dict)):
                        poss = v["positions"]
                        if isinstance(poss, dict):
                            poss = list(poss.values())
                        for pos in poss:
                            if isinstance(pos, dict):
                                add_pri(pos.get("symbol") or pos.get("code"))

    # 日频推荐（按分数）
    rec = ROOT / "output" / "daily_recommend.json"
    if rec.exists():
        try:
            d = json.loads(rec.read_text(encoding="utf-8"))
            items = list(d.get("recommendations") or [])
            items.sort(key=lambda x: -float((x or {}).get("score") or 0))
            for it in items:
                add_rest(it.get("code") or it.get("symbol"))
        except Exception:
            pass

    # 尾盘 / 晨间
    for name, keys in (
        ("eod_s2_picks.json", ("picks", "items")),
        ("morning_live_fund.json", ("picks", "items", "recommendations")),
    ):
        p = ROOT / "output" / name
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for k in keys:
            for it in d.get(k) or []:
                if isinstance(it, dict):
                    add_rest(it.get("code") or it.get("symbol"))
                else:
                    add_rest(it)

    # 启动形态命中
    lp = ROOT / "output" / "launch_patterns_pool.json"
    if lp.exists():
        try:
            d = json.loads(lp.read_text(encoding="utf-8"))
            hits = d.get("hits") or d.get("symbols") or d.get("pool") or []
            if isinstance(hits, dict):
                hits = list(hits.keys())
            for it in hits[:120]:
                if isinstance(it, dict):
                    add_rest(it.get("symbol") or it.get("code"))
                else:
                    add_rest(it)
        except Exception:
            pass

    # 旁路池前 80（控积分）
    bp = ROOT / "output" / "hot_sector_bypass_pool.json"
    if bp.exists():
        try:
            d = json.loads(bp.read_text(encoding="utf-8"))
            items = d.get("items") or d.get("symbols") or []
            if isinstance(items, dict):
                items = list(items.keys())
            for it in items[:80]:
                if isinstance(it, dict):
                    add_rest(it.get("symbol") or it.get("code"))
                else:
                    add_rest(it)
        except Exception:
            pass

    for c in extra or []:
        add_pri(c)

    return priority + rest


def enrich_one(api_key: str, bare: str) -> dict:
    wc = _windcode(bare)
    result = mcp_call(
        api_key,
        "get_stock_price_indicators",
        {"windcode": wc, "indexes": INDEXES},
    )
    row = _extract_row(result)
    if row.get("error"):
        raise RuntimeError(row["error"])
    return {
        "code": bare,
        "windcode": wc,
        "name": row.get("中文简称"),
        "price": _f(row.get("最新成交价")),
        "change_pct": _f(row.get("涨跌幅")),
        "pe_ttm": _f(row.get("市盈率(TTM)")),
        "main_net_today": _f(row.get("当日主力净流入额")),
        "main_net_today_pct": _f(row.get("当日主力净流入占比")),
        "main_net_5d": _f(row.get("近5日主力净流入额")),
        "main_net_5d_pct": _f(row.get("近5日主力净流入占比")),
        "inst_net": _f(row.get("该日机构资金净流入额")),
        "large_net": _f(row.get("该日大户资金净流入额")),
        "mid_net": _f(row.get("该日中户资金净流入额")),
        "retail_net": _f(row.get("该日散户资金净流入额")),
        "raw_keys": list(row.keys()),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", default="", help="逗号分隔额外代码")
    ap.add_argument("--limit", type=int, default=80)
    ap.add_argument("--sleep", type=float, default=0.3)
    ap.add_argument(
        "--session",
        default="manual",
        help="premarket/open/midday/pre_eod/close/manual",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    extra = [x.strip() for x in args.codes.split(",") if x.strip()]
    codes = collect_symbols(extra)[: max(1, args.limit)]
    print(
        f"candidates session={args.session} n={len(codes)}: {','.join(codes[:20])}"
        + ("..." if len(codes) > 20 else ""),
        flush=True,
    )
    if args.dry_run:
        return 0

    api_key = load_api_key()
    items = {}
    errors = []
    for i, c in enumerate(codes, 1):
        try:
            items[c] = enrich_one(api_key, c)
            print(
                f"[{i}/{len(codes)}] {c} net_today={items[c].get('main_net_today')} "
                f"inst={items[c].get('inst_net')} pe={items[c].get('pe_ttm')}",
                flush=True,
            )
        except Exception as e:
            errors.append({"code": c, "error": str(e)[:300]})
            print(f"[{i}/{len(codes)}] FAIL {c}: {e}", flush=True)
        time.sleep(args.sleep)

    payload = {
        "asof": datetime.now().strftime("%Y-%m-%d"),
        "session": args.session,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "wind.mcp.stock_data.get_stock_price_indicators",
        "indexes": INDEXES,
        "n": len(items),
        "n_error": len(errors),
        "items": items,
        "errors": errors,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {OUT} n={len(items)} errors={len(errors)}", flush=True)
    return 0 if items else 1


if __name__ == "__main__":
    raise SystemExit(main())
