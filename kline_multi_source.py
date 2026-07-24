#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多源日K线获取 + 源健康巡检。

优先级默认: sina → tdx(mootdx) → eastmoney → tencent
健康状态落盘: output/kline_source_health.json
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

import pandas as pd

ROOT = Path(__file__).resolve().parent
HEALTH_PATH = ROOT / "output" / "kline_source_health.json"


def _bare(sym: str) -> str:
    s = str(sym or "").lower().replace("sh", "").replace("sz", "").replace("bj", "")
    return s[-6:] if len(s) >= 6 else s


def _normalize(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    colmap = {}
    for a, b in (
        ("日期", "date"),
        ("开盘", "open"),
        ("收盘", "close"),
        ("最高", "high"),
        ("最低", "low"),
        ("成交量", "volume"),
        ("成交额", "amount"),
    ):
        if a in out.columns and b not in out.columns:
            colmap[a] = b
    if colmap:
        out = out.rename(columns=colmap)
    if "date" not in out.columns:
        return pd.DataFrame()
    out["date"] = pd.to_datetime(out["date"])
    out["symbol"] = _bare(symbol)
    keep = [c for c in ("date", "open", "high", "low", "close", "volume", "amount", "symbol") if c in out.columns]
    return out[keep].sort_values("date").reset_index(drop=True)


def _get_sina(symbol: str, start_date: str) -> pd.DataFrame:
    from data_fetcher import _get_kline_sina

    return _normalize(_get_kline_sina(symbol, start_date), symbol)


def _get_tdx(symbol: str, start_date: str) -> pd.DataFrame:
    try:
        from mootdx.quotes import Quotes

        client = Quotes.factory(market="std")
        code = _bare(symbol)
        df = client.bars(symbol=code, frequency=9, offset=800)
        if df is None or df.empty:
            return pd.DataFrame()
        if "datetime" in df.columns:
            df = df.rename(columns={"datetime": "date"})
        df = _normalize(df, symbol)
        if start_date:
            sd = pd.to_datetime(start_date)
            df = df[df["date"] >= sd].reset_index(drop=True)
        return df
    except Exception:
        return pd.DataFrame()


def _get_em(symbol: str, start_date: str) -> pd.DataFrame:
    import akshare as ak

    code = _bare(symbol)
    end = datetime.now().strftime("%Y%m%d")
    df = ak.stock_zh_a_hist(
        symbol=code,
        period="daily",
        start_date=start_date,
        end_date=end,
        adjust="qfq",
    )
    return _normalize(df, symbol)


def _get_tencent(symbol: str, start_date: str) -> pd.DataFrame:
    """腾讯日K兜底（字段较简）。"""
    import requests

    code = _bare(symbol)
    prefix = "sh" if code.startswith("6") else "sz"
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    params = {
        "param": f"{prefix}{code},day,{start_date[:4]}-01-01,,640,qfq",
    }
    r = requests.get(url, params=params, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
    data = r.json()
    node = (data.get("data") or {}).get(f"{prefix}{code}") or {}
    rows = node.get("qfqday") or node.get("day") or []
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["date", "open", "close", "high", "low", "volume"])
    for c in ("open", "close", "high", "low", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return _normalize(df, symbol)


SOURCES: dict[str, dict] = {
    "sina": {"func": _get_sina, "priority": 1},
    "tdx": {"func": _get_tdx, "priority": 2},
    "em": {"func": _get_em, "priority": 3},
    "tencent": {"func": _get_tencent, "priority": 4},
}


def _ordered_sources() -> list[str]:
    health = {}
    if HEALTH_PATH.exists():
        try:
            health = json.loads(HEALTH_PATH.read_text(encoding="utf-8")).get("sources") or {}
        except Exception:
            health = {}
    # 健康优先：ok 的排前面，再按 priority
    items = []
    for name, meta in SOURCES.items():
        h = health.get(name) or {}
        ok = h.get("ok", True)
        items.append((0 if ok else 1, meta["priority"], name))
    items.sort()
    return [x[2] for x in items]


def get_kline_multi(
    symbol: str,
    start_date: str | None = None,
    preferred: str | None = None,
) -> pd.DataFrame:
    """依次尝试各源，返回第一个非空结果。"""
    if not start_date:
        start_date = (datetime.now() - timedelta(days=400)).strftime("%Y%m%d")
    order = _ordered_sources()
    if preferred and preferred in order:
        order = [preferred] + [x for x in order if x != preferred]
    last_err = None
    for name in order:
        fn: Callable = SOURCES[name]["func"]
        try:
            df = fn(symbol, start_date)
            if df is not None and not df.empty and "close" in df.columns:
                df = df.copy()
                df.attrs["kline_source"] = name
                return df
        except Exception as e:
            last_err = e
            continue
    if last_err:
        print(f"  kline_multi fail {symbol}: {last_err}", flush=True)
    return pd.DataFrame()


def check_kline_sources(probe_symbol: str = "600519") -> dict:
    """巡检各源可用性，落盘健康状态。"""
    start = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
    report = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "probe": probe_symbol, "sources": {}}
    for name, meta in SOURCES.items():
        t0 = time.time()
        ok = False
        n = 0
        err = None
        try:
            df = meta["func"](probe_symbol, start)
            ok = df is not None and not df.empty
            n = 0 if df is None else len(df)
        except Exception as e:
            err = str(e)[:120]
        report["sources"][name] = {
            "ok": ok,
            "rows": n,
            "elapsed_ms": int((time.time() - t0) * 1000),
            "error": err,
            "priority": meta["priority"],
        }
    HEALTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    HEALTH_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(check_kline_sources(), ensure_ascii=False, indent=2))
    df = get_kline_multi("000001")
    print("rows", len(df), "source", getattr(df, "attrs", {}).get("kline_source"))
