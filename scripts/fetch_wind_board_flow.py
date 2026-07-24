#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拉取万得板块/全A资金流（咨询与研报用，不改交易硬门）。

输出:
  data/wind_board_flow.json           # 最新快照 + prefer/avoid + 轮动标记
  data/wind_board_flow_midday.json    # --session midday 额外归档
  data/wind_board_flow_history.json   # 按日归档（算连续流入）

口径（与 Wind App 对齐）:
  consecutive_inflow_days = 从今日往前连续主力净流入>0 的天数
  inflow_days_5d_window   = 近5日窗口内净流入天数（仅审计，不驱动轮动标签）

轮动标签基于连续天数:
  1–2 → fresh_inflow；3 → rotation_watch；≥4 → rotation_high_risk；当日流出 → outflow

用法:
  python3 scripts/fetch_wind_board_flow.py
  python3 scripts/fetch_wind_board_flow.py --session midday
  python3 scripts/fetch_wind_board_flow.py --limit 10
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
sys.path.insert(0, str(ROOT))

UNIVERSE = ROOT / "config" / "wind_board_universe.json"
OUT = ROOT / "data" / "wind_board_flow.json"
OUT_MIDDAY = ROOT / "data" / "wind_board_flow_midday.json"
HIST = ROOT / "data" / "wind_board_flow_history.json"
INDEX_EP = "https://mcp.wind.com.cn/vserver_index_data/mcp/"
INDEXES = (
    "中文简称,涨跌幅,当日主力净流入额,当日主力净流入占比,"
    "近5日主力净流入额,近5日主力净流入占比,近5日主力净流入天数,"
    "近10日主力净流入天数,"
    "该日机构资金净流入额,该日大户资金净流入额,该日中户资金净流入额,该日散户资金净流入额,"
    "连红天数"
)


def load_api_key() -> str:
    env = (os.environ.get("WIND_API_KEY") or "").strip()
    if env:
        return env
    cfg = Path.home() / ".wind-aifinmarket" / "config"
    if cfg.exists():
        for line in cfg.read_text(encoding="utf-8").splitlines():
            line = line.strip().lstrip("\ufeff")
            if line.startswith("export "):
                line = line[7:].strip()
            if line.startswith("WIND_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("WIND_API_KEY 未配置")


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
        req = urllib.request.Request(INDEX_EP, data=body, headers=headers, method="POST")
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
            "clientInfo": {"name": "alphapilot-wind-board", "version": "1.1"},
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
    if not text:
        return {}
    try:
        inner = json.loads(text) if isinstance(text, str) else text
    except Exception:
        return {"raw": text}
    if isinstance(inner, dict) and inner.get("error"):
        return {"error": inner["error"]}
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


def _i(v):
    x = _f(v)
    return int(x) if x is not None else None


def _to_yi(v):
    """Wind 净流入额多为元；|v|≥1e5 视为元→亿，否则原样当作亿。"""
    x = _f(v)
    if x is None:
        return None
    if abs(x) >= 1e5:
        return round(x / 1e8, 4)
    return round(x, 4)


def is_noisy_concept(name: str, prefixes: list[str]) -> bool:
    n = (name or "").strip()
    if not n:
        return True
    for p in prefixes:
        if n.startswith(p) or p in n:
            return True
    if re.match(r"^全A", n) or "等权" in n and "万得" in n:
        return True
    return False


def load_hist() -> dict:
    if not HIST.exists():
        return {}
    try:
        hist = json.loads(HIST.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return hist if isinstance(hist, dict) else {}


def consecutive_inflow_days(
    windcode: str,
    today_net: float | None,
    hist: dict,
    today: str,
    api_consec: int | None = None,
) -> tuple[int, str]:
    """App 口径：从今日往前连续主力净流入>0 的天数。

    优先用本地 history 推算；若 history 不足且 API 给了连续天数则作补充。
    """
    if today_net is None:
        return 0, "no_today"
    if float(today_net) <= 0:
        return 0, "outflow_today"

    n = 1
    past = sorted((d for d in hist.keys() if str(d) < today), reverse=True)
    used_hist = 0
    for d in past:
        nets = (hist.get(d) or {}).get("industry_nets") or {}
        v = nets.get(windcode)
        if v is None:
            break
        try:
            fv = float(v)
        except (TypeError, ValueError):
            break
        if fv > 0:
            n += 1
            used_hist += 1
        else:
            break

    # history 为空时：今日净流入 → 至少 1；若 API 有连续字段可用则采用
    if used_hist == 0 and not past:
        if api_consec is not None and api_consec >= 1:
            return int(api_consec), "api_consecutive"
        return 1, "today_only"
    if used_hist == 0 and past and api_consec is not None and api_consec >= 1:
        # 历史缺码，退回 API
        return int(api_consec), "api_consecutive_fallback"
    return n, "history_streak"


def fetch_one(api_key: str, windcode: str) -> dict:
    result = mcp_call(
        api_key,
        "get_index_price_indicators",
        {"windcode": windcode, "indexes": INDEXES},
    )
    row = _extract_row(result)
    if row.get("error"):
        return {"windcode": windcode, "error": row["error"]}
    api_consec = _i(
        row.get("连续净流入天数")
        or row.get("连续主力净流入天数")
        or row.get("主力资金连续净流入天数")
    )
    return {
        "windcode": windcode,
        "name": row.get("中文简称") or windcode,
        "change_pct": _f(row.get("涨跌幅")),
        "main_net": _to_yi(row.get("当日主力净流入额")),
        "main_net_pct": _f(row.get("当日主力净流入占比")),
        "main_net_5d": _to_yi(row.get("近5日主力净流入额")),
        "main_net_5d_pct": _f(row.get("近5日主力净流入占比")),
        "inflow_days_5d_window": _i(row.get("近5日主力净流入天数")),
        "inflow_days_10d_window": _i(row.get("近10日主力净流入天数")),
        # 兼容旧字段名（审计）；轮动请用 consecutive_inflow_days
        "inflow_days_5d": _i(row.get("近5日主力净流入天数")),
        "inflow_days_10d": _i(row.get("近10日主力净流入天数")),
        "api_consecutive_inflow_days": api_consec,
        "inst_net": _to_yi(row.get("该日机构资金净流入额")),
        "large_net": _to_yi(row.get("该日大户资金净流入额")),
        "mid_net": _to_yi(row.get("该日中户资金净流入额")),
        "retail_net": _to_yi(row.get("该日散户资金净流入额")),
        "red_days": _i(row.get("连红天数")),
        "unit": "yi",
    }


def classify_rotation(item: dict, rot: dict) -> str:
    """轮动标签：基于连续净流入天数（App 口径）。"""
    days = item.get("consecutive_inflow_days")
    main = item.get("main_net") or 0
    if main < 0:
        return "outflow"
    if days is None:
        return "unknown"
    if days >= int(rot.get("rotation_high_risk_days") or 4):
        return "rotation_high_risk"
    if days >= int(rot.get("rotation_watch_days") or 3):
        return "rotation_watch"
    if 1 <= days <= int(rot.get("fresh_inflow_days_max") or 2):
        return "fresh_inflow"
    if days == 0 and main > 0:
        return "fresh_inflow"
    return "neutral"


def _attach_streak(row: dict, hist: dict, today: str, rot: dict) -> dict:
    streak, src = consecutive_inflow_days(
        str(row.get("windcode") or ""),
        row.get("main_net"),
        hist,
        today,
        api_consec=row.get("api_consecutive_inflow_days"),
    )
    row["consecutive_inflow_days"] = streak
    row["consecutive_source"] = src
    row["rotation_tag"] = classify_rotation(row, rot)
    return row


def build_consult_views(industries: list[dict], concepts: list[dict], all_a: dict | None, rot: dict) -> dict:
    inds = [x for x in industries if x.get("main_net") is not None and not x.get("error")]
    inds_sorted = sorted(inds, key=lambda x: float(x.get("main_net") or 0), reverse=True)
    top_in = inds_sorted[:8]
    top_out = list(reversed(inds_sorted[-8:])) if len(inds_sorted) >= 8 else list(reversed(inds_sorted))

    prefer = []
    avoid = []
    rotation_watch = []
    for x in inds_sorted:
        tag = x.get("rotation_tag") or classify_rotation(x, rot)
        x["rotation_tag"] = tag
        name = re.sub(r"\(申万\)$", "", str(x.get("name") or "")).strip()
        if tag == "fresh_inflow" and (x.get("main_net") or 0) > 0:
            if name not in prefer:
                prefer.append(name)
        if tag in ("rotation_watch", "rotation_high_risk"):
            if name not in rotation_watch:
                rotation_watch.append(name)
        if tag == "outflow" or (x.get("main_net") or 0) < 0:
            if name not in avoid:
                avoid.append(name)

    cons = [x for x in concepts if x.get("main_net") is not None and not x.get("error")]
    cons_sorted = sorted(cons, key=lambda x: float(x.get("main_net") or 0), reverse=True)

    sentiment = None
    if all_a and not all_a.get("error"):
        sentiment = {
            "name": all_a.get("name"),
            "windcode": all_a.get("windcode"),
            "change_pct": all_a.get("change_pct"),
            "main_net": all_a.get("main_net"),
            "inst_net": all_a.get("inst_net"),
            "large_net": all_a.get("large_net"),
            "mid_net": all_a.get("mid_net"),
            "retail_net": all_a.get("retail_net"),
            "consecutive_inflow_days": all_a.get("consecutive_inflow_days"),
            "inflow_days_5d_window": all_a.get("inflow_days_5d_window"),
            "red_days": all_a.get("red_days"),
            "tone": (
                "risk_on"
                if (all_a.get("inst_net") or 0) > 0 and (all_a.get("main_net") or 0) > 0
                else (
                    "mixed"
                    if (all_a.get("main_net") or 0) > 0
                    else "risk_off"
                )
            ),
        }

    def _row_brief(x: dict) -> dict:
        return {
            "name": re.sub(r"\(申万\)$", "", str(x.get("name") or "")),
            "windcode": x.get("windcode"),
            "main_net": x.get("main_net"),
            "main_net_pct": x.get("main_net_pct"),
            "consecutive_inflow_days": x.get("consecutive_inflow_days"),
            "inflow_days_5d_window": x.get("inflow_days_5d_window"),
            "rotation_tag": x.get("rotation_tag"),
        }

    return {
        "industry_top_inflow": [_row_brief(x) for x in top_in],
        "industry_top_outflow": [
            _row_brief(x) for x in top_out if (x.get("main_net") or 0) < 0
        ],
        "concept_top_inflow": [
            {
                "name": x.get("name"),
                "windcode": x.get("windcode"),
                "main_net": x.get("main_net"),
                "consecutive_inflow_days": x.get("consecutive_inflow_days"),
            }
            for x in cons_sorted[:8]
            if (x.get("main_net") or 0) > 0
        ],
        "all_a_sentiment": sentiment,
        "prefer": prefer[:12],
        "avoid": avoid[:12],
        "rotation_watch": rotation_watch[:12],
        "note": (
            "口径=连续净流入天数(App)。prefer=连续1–2日新鲜流入；"
            "rotation_watch=连续≥3日；avoid=当日净流出。"
            "仅咨询/研报/B臂软加权，不进硬 avoid。"
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="smoke: limit industry count")
    ap.add_argument("--sleep", type=float, default=0.25)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--session",
        choices=["close", "midday", "pre_eod", "manual"],
        default="close",
        help="close=收盘主快照；midday/pre_eod=盘中快照(不写日终 history)",
    )
    args = ap.parse_args()

    uni = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    rot = uni.get("rotation") or {}
    prefixes = uni.get("concept_denoise_prefixes") or []
    industries = list(uni.get("industries") or [])
    concepts = list(uni.get("concepts") or [])
    all_a_list = list(uni.get("all_a") or [])
    if args.limit and args.limit > 0:
        industries = industries[: args.limit]

    if args.dry_run:
        print(f"dry-run industries={len(industries)} concepts={len(concepts)}")
        return 0

    api_key = load_api_key()
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hist = load_hist()

    ind_rows = []
    for i, it in enumerate(industries):
        wc = it.get("windcode")
        print(f"[{i+1}/{len(industries)}] {wc} {it.get('name')}", flush=True)
        try:
            row = fetch_one(api_key, wc)
            row["kind"] = "industry"
            _attach_streak(row, hist, today, rot)
            ind_rows.append(row)
        except Exception as e:
            ind_rows.append({"windcode": wc, "name": it.get("name"), "kind": "industry", "error": str(e)})
        time.sleep(max(0.0, args.sleep))

    con_rows = []
    for i, it in enumerate(concepts):
        wc = it.get("windcode")
        print(f"[concept {i+1}/{len(concepts)}] {wc}", flush=True)
        try:
            row = fetch_one(api_key, wc)
            row["kind"] = "concept"
            if is_noisy_concept(str(row.get("name") or it.get("name") or ""), prefixes):
                row["denoised"] = True
                row["skip_reason"] = "style_board"
            else:
                _attach_streak(row, hist, today, rot)
            con_rows.append(row)
        except Exception as e:
            con_rows.append({"windcode": wc, "name": it.get("name"), "kind": "concept", "error": str(e)})
        time.sleep(max(0.0, args.sleep))

    all_a = None
    for it in all_a_list:
        wc = it.get("windcode")
        print(f"[all_a] {wc}", flush=True)
        try:
            all_a = fetch_one(api_key, wc)
            all_a["kind"] = "all_a"
            # 全A 用自身码在 history 的 industry_nets 可能没有；仅用今日+API
            streak, src = consecutive_inflow_days(
                wc,
                all_a.get("main_net"),
                {},
                today,
                api_consec=all_a.get("api_consecutive_inflow_days"),
            )
            all_a["consecutive_inflow_days"] = streak
            all_a["consecutive_source"] = src
        except Exception as e:
            all_a = {"windcode": wc, "error": str(e), "kind": "all_a"}

    cons_use = [c for c in con_rows if not c.get("denoised") and not c.get("error")]
    views = build_consult_views(ind_rows, cons_use, all_a, rot)

    payload = {
        "asof": today,
        "session": args.session,
        "updated_at": now,
        "source": "wind.mcp.index_data.get_index_price_indicators",
        "purpose": "consult_research_only",
        "trading_gate_unchanged": True,
        "inflow_day_definition": "consecutive_net_inflow_gt0_from_today_App口径",
        "n_industry": len(ind_rows),
        "n_concept": len(cons_use),
        "all_a": all_a,
        "industries": ind_rows,
        "concepts": con_rows,
        "consult": views,
        "rotation_policy": rot,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.session == "midday":
        OUT_MIDDAY.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print("wrote", OUT_MIDDAY)
    elif args.session == "pre_eod":
        pre = ROOT / "data" / "wind_board_flow_pre_eod.json"
        pre.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print("wrote", pre)

    # 收盘 session 才写入日终 history（避免盘中覆盖全日）
    if args.session in ("close", "manual"):
        hist[today] = {
            "updated_at": now,
            "session": args.session,
            "consult": views,
            "all_a": {
                "main_net": (all_a or {}).get("main_net"),
                "inst_net": (all_a or {}).get("inst_net"),
                "large_net": (all_a or {}).get("large_net"),
                "retail_net": (all_a or {}).get("retail_net"),
            },
            "industry_nets": {
                (x.get("windcode") or ""): x.get("main_net") for x in ind_rows if x.get("windcode")
            },
        }
        days = sorted(hist.keys())
        if len(days) > 60:
            for d in days[:-60]:
                hist.pop(d, None)
        HIST.write_text(json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8")

    print("wrote", OUT)
    print("prefer", views.get("prefer")[:6])
    print("avoid", views.get("avoid")[:6])
    print("rotation_watch", views.get("rotation_watch")[:6])
    # 抽查连续天数 vs 窗口天数
    for x in (views.get("industry_top_inflow") or [])[:3]:
        print(
            "sample",
            x.get("name"),
            "consec",
            x.get("consecutive_inflow_days"),
            "win5",
            x.get("inflow_days_5d_window"),
            "tag",
            x.get("rotation_tag"),
        )
    if views.get("all_a_sentiment"):
        s = views["all_a_sentiment"]
        print(
            "all_a",
            s.get("tone"),
            "main",
            s.get("main_net"),
            "inst",
            s.get("inst_net"),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
