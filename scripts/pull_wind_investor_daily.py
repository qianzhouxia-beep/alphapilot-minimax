#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""收盘后拉万得全A（881001.WI）四类净买入，日度落盘。

口译（2026-09-02 用户更正，见 knowledge/data_sources/wind_investor_flow.md）：
  红 机构 = 央妈  -> inst
  橙 大户 = 量化  -> quant     （口头也称主力；不是 API「主力净流入额」）
  浅蓝 中户 = 游资 -> hot_money
  蓝 散户         -> retail

Key：WIND_API_KEY > config/wind_api_key.conf > ~/.wind-aifinmarket/config
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "data" / "wind_investor_flow_daily"
KEY_FILE = ROOT / "config" / "wind_api_key.conf"
HOME_CFG = Path.home() / ".wind-aifinmarket" / "config"
CST = timezone(timedelta(hours=8))
ENDPOINT = "https://mcp.wind.com.cn/vserver_analytics_data/mcp/"
WINDCODE = "881001.WI"
QUESTION_FOUR = (
    "881001.WI万得全A今日机构净买入额大户净买入额中户净买入额散户净买入额"
)
TYPE_MAP = {
    "机构": "inst",
    "大户": "quant",
    "中户": "hot_money",
    "散户": "retail",
}


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def load_key() -> str:
    v = (os.environ.get("WIND_API_KEY") or "").strip()
    if v:
        return v
    if KEY_FILE.exists():
        raw = KEY_FILE.read_text(encoding="utf-8", errors="ignore")
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("WIND_API_KEY="):
                return line.split("=", 1)[1].strip().strip("'\"")
            return line
    if HOME_CFG.exists():
        raw = HOME_CFG.read_text(encoding="utf-8", errors="ignore")
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("WIND_API_KEY="):
                return line.split("=", 1)[1].strip().strip("'\"")
            if line.startswith("export WIND_API_KEY="):
                return line.split("=", 1)[1].strip().strip("'\"")
    raise SystemExit("WIND_API_KEY missing (env / config/wind_api_key.conf / ~/.wind-aifinmarket/config)")


def _parse_sse(text: str) -> dict:
    trimmed = (text or "").strip()
    if trimmed.startswith("{"):
        return json.loads(trimmed)
    last = None
    for line in text.splitlines():
        if line.startswith("data: "):
            last = line[6:]
    if not last:
        raise RuntimeError(f"MCP response not SSE/JSON: {text[:200]!r}")
    return json.loads(last)


def mcp_call(api_key: str, question: str, timeout: int = 90) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }

    def post(method: str, params: dict, to: int) -> dict:
        body = json.dumps({"jsonrpc": "2.0", "id": int(time.time() * 1000), "method": method, "params": params})
        req = urllib.request.Request(ENDPOINT, data=body.encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=to) as resp:
            raw = resp.read().decode("utf-8", "replace")
        payload = _parse_sse(raw)
        if payload.get("error"):
            raise RuntimeError(str(payload["error"]))
        return payload.get("result") or {}

    post(
        "initialize",
        {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "alphapilot-wind-investor", "version": "1.0"},
        },
        30,
    )
    result = post(
        "tools/call",
        {
            "name": "get_financial_data",
            "arguments": {"question": question, "lang": "CNS"},
            "_meta": {"clientVersion": "1.0"},
        },
        timeout,
    )
    if result.get("isError"):
        raise RuntimeError(str(result.get("content")))
    texts = []
    for block in result.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text":
            texts.append(block.get("text") or "")
    blob = "\n".join(texts).strip()
    if not blob or blob == "没找到数据":
        raise RuntimeError(f"no data: {blob[:120]!r}")
    try:
        return json.loads(blob)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"inner JSON parse fail: {e}: {blob[:200]!r}") from e


def _tables(inner: dict) -> list[dict]:
    data = inner.get("data") if isinstance(inner, dict) else None
    if not isinstance(data, dict):
        return []
    tables = data.get("data")
    if isinstance(tables, list):
        return [t for t in tables if isinstance(t, dict)]
    return []


def _col_names(table: dict) -> list[str]:
    cols = table.get("columns") or []
    names = []
    for c in cols:
        if isinstance(c, dict):
            names.append(str(c.get("name") or ""))
        else:
            names.append(str(c))
    return names


def _f(v, default=None):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    if x != x:  # nan
        return default
    return x


# Wide-table column aliases (Wind MCP flipped to 1-row wide schema ~2026-09-03).
_WIDE_VAL = {
    "inst": ("最新机构净买入额", "机构净买入额"),
    "quant": ("最新大户净买入额", "大户净买入额"),
    "hot_money": ("最新中户净买入额", "中户净买入额"),
    "retail": ("最新散户净买入额", "散户净买入额"),
}


def _parse_four_wide(names: list[str], row: list) -> tuple[dict, str, str]:
    """Parse 1-row wide table: 最新机构/大户/中户/散户净买入额 (+ .交易时间/.日期)."""
    out: dict = {}
    asof = ""
    day = ""
    name_to_i = {n: i for i, n in enumerate(names)}

    def _cell(col: str):
        i = name_to_i.get(col)
        if i is None or i >= len(row):
            return None
        return row[i]

    for key, aliases in _WIDE_VAL.items():
        for alias in aliases:
            v = _f(_cell(alias))
            if v is not None:
                out[key] = v
                break
            # also accept exact alias without 最新 prefix already covered
        # companion time/date prefer 机构 column
    for alias in _WIDE_VAL["inst"]:
        t = _cell(f"{alias}.交易时间")
        d = _cell(f"{alias}.日期")
        if t:
            asof = str(t)
        if d:
            day = str(d).replace("-", "")[:8]
        if asof or day:
            break
    return out, asof, day


def _parse_four_long(names: list[str], rows: list) -> tuple[dict, str, str]:
    """Legacy long table: 类型/投资者类型 + 净买入/净流入."""
    out: dict = {}
    asof = ""
    day = ""
    type_i = next((i for i, n in enumerate(names) if n in ("类型", "投资者类型")), None)
    val_i = next((i for i, n in enumerate(names) if "净买入" in n or "净流入" in n), None)
    time_i = next((i for i, n in enumerate(names) if "交易时间" in n), None)
    date_i = next((i for i, n in enumerate(names) if n in ("日期",)), None)
    if type_i is None or val_i is None:
        return out, asof, day
    for row in rows:
        if not isinstance(row, list):
            continue
        t = str(row[type_i] if type_i < len(row) else "")
        key = TYPE_MAP.get(t)
        if not key:
            continue
        out[key] = _f(row[val_i] if val_i < len(row) else None)
        if time_i is not None and time_i < len(row) and row[time_i]:
            asof = str(row[time_i])
        if date_i is not None and date_i < len(row) and row[date_i]:
            day = str(row[date_i]).replace("-", "")[:8]
    return out, asof, day


def parse_four(inner: dict) -> tuple[dict, str, str]:
    """Return (net_buy_yi, asof, date_yyyymmdd).

    Supports:
      - long: rows keyed by 类型=机构/大户/中户/散户 (pre-2026-09-03)
      - wide: one row with 最新机构/大户/中户/散户净买入额 (current Wind MCP)
    """
    out: dict = {}
    asof = ""
    day = ""
    for table in _tables(inner):
        names = _col_names(table)
        rows = table.get("rows") or []
        if not names or not rows:
            continue
        # Prefer wide schema when those columns exist.
        if any(n.startswith("最新机构净买入") or n == "机构净买入额" for n in names):
            row0 = rows[0] if isinstance(rows[0], list) else None
            if row0 is not None:
                out, asof, day = _parse_four_wide(names, row0)
                if out:
                    break
        long_out, long_asof, long_day = _parse_four_long(names, rows)
        if long_out:
            out, asof, day = long_out, long_asof, long_day
            break
    missing = [k for k in ("inst", "quant", "hot_money", "retail") if out.get(k) is None]
    if missing:
        raise RuntimeError(f"four-bucket parse missing {missing}; keys={list(out)}")
    return out, asof, day


def regime(net: dict) -> dict:
    inst = float(net["inst"])
    quant = float(net["quant"])
    yangma_in = inst > 0
    quant_in = quant > 0
    return {
        "yangma_in": yangma_in,
        "quant_in": quant_in,
        "both_in": yangma_in and quant_in,
        "yangma_in_quant_off": yangma_in and (not quant_in),
    }


def today_cst() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d")


def _norm_day(d: str) -> str:
    """'20260902' / '2026-09-02' -> '2026-09-02'; 无法识别返回 ''。"""
    s = str(d or "").strip().replace("-", "").replace("/", "")
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="", help="YYYY-MM-DD 请求日期，默认今天（上海）")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    req_day = args.date.strip() or today_cst()

    key = load_key()
    log(f"fetch four buckets {WINDCODE} -> requested {req_day}")
    four_inner = mcp_call(key, QUESTION_FOUR)
    net, asof, wind_day = parse_four(four_inner)

    # 落盘文件名用 Wind 返回的真实交易日，不用本机日期：
    # 盘后/凌晨跑时「今日」仍返回最近交易日，用本机日期会把数据写到错的一天。
    day = _norm_day(wind_day) or req_day
    if day != req_day:
        log(f"NOTE: wind trade day {day} != requested {req_day}; file follows wind day")
    out_path = OUT_DIR / f"{day}.json"
    if out_path.exists() and not args.force:
        log(f"exists {out_path} (use --force to overwrite)")
        return 0

    payload = {
        "date": day,
        "requested_date": req_day,
        "windcode": WINDCODE,
        "name": "万得全A",
        "asof": asof,
        "wind_date": wind_day,
        "unit": "yi",
        "mapping": {
            "inst": "红线 机构=央妈",
            "quant": "橙线 大户=量化（口头主力；非API主力净流入）",
            "hot_money": "浅蓝 中户=游资",
            "retail": "蓝线 散户",
        },
        "net_buy_yi": net,
        "regime": regime(net),
        "source": "wind_mcp analytics_data.get_financial_data",
        "pulled_at": datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S"),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(out_path)
    log(f"wrote {out_path} net={net} regime={payload['regime']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:  # noqa: BLE001
        log(f"FAIL: {e}")
        raise SystemExit(1)
