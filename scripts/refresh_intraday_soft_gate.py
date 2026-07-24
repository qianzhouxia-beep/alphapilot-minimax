#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""刷新盘中软门控快照（东财资金流排名 + 批量行情），供 soft_intraday_gate 使用。"""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "intraday_soft_gate.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
S = requests.Session()
S.trust_env = False  # 避开本机坏代理
S.headers.update({"User-Agent": UA, "Referer": "https://data.eastmoney.com/"})


def bare(code: str) -> str:
    return str(code or "").lower().replace("sh", "").replace("sz", "").replace("bj", "")[-6:]


def fetch_rank(indicator: str = "today") -> dict:
    """分页拉全市场资金流排名（按主力净流入降序）。"""
    fid_map = {"today": "f62", "3day": "f267", "5day": "f164", "10day": "f174"}
    fid = fid_map.get(indicator, "f62")
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    m = {}
    rank = 0
    page = 1
    while page <= 60:
        params = {
            "fid": fid,
            "po": 1,
            "pz": 100,
            "pn": page,
            "np": 1,
            "fltt": 2,
            "invt": 2,
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
            "fields": "f12,f14,f2,f3,f62,f184,f267,f164,f174",
        }
        r = S.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json().get("data") or {}
        diff = data.get("diff") or []
        if not diff:
            break
        for it in diff:
            code = bare(it.get("f12"))
            if not code or code in m:
                continue
            main = it.get(fid) if indicator != "today" else it.get("f62")
            try:
                main_v = float(main) if main not in (None, "-", "") else None
            except Exception:
                main_v = None
            try:
                chg = float(it.get("f3")) if it.get("f3") not in (None, "-", "") else None
            except Exception:
                chg = None
            try:
                price = float(it.get("f2")) if it.get("f2") not in (None, "-", "") else None
            except Exception:
                price = None
            rank += 1
            m[code] = {
                "rank": rank,
                "name": it.get("f14"),
                "mainNetInflow": main_v,
                "changePercent": chg,
                "price": price,
            }
        total = int(data.get("total") or 0)
        if rank >= total or len(diff) < 100:
            break
        page += 1
        time.sleep(0.05)
    return m


def fetch_quotes(codes: list[str]) -> dict:
    """新浪批量行情（轻量）。"""
    out = {}
    # batch 80
    for i in range(0, len(codes), 80):
        batch = codes[i : i + 80]
        tags = []
        for c in batch:
            tags.append(("sh" if c.startswith(("5", "6", "9")) else "sz") + c)
        url = "https://hq.sinajs.cn/list=" + ",".join(tags)
        try:
            r = S.get(url, headers={**S.headers, "Referer": "https://finance.sina.com.cn"}, timeout=15)
            text = r.content.decode("gbk", errors="ignore")
        except Exception:
            continue
        for line in text.splitlines():
            if '="' not in line:
                continue
            left, right = line.split('="', 1)
            code = bare(left.split("_")[-1])
            parts = right.rstrip('";').split(",")
            if len(parts) < 10:
                continue
            try:
                price = float(parts[3]) if parts[3] else None
                prev = float(parts[2]) if parts[2] else None
                chg = ((price / prev - 1) * 100) if price and prev else None
            except Exception:
                price = chg = None
            out[code] = {"price": price, "changePercent": chg, "name": parts[0]}
        time.sleep(0.05)
    return out


def main():
    print("refresh intraday soft gate (EM rank + sina quotes)...")
    today = fetch_rank("today")
    d5 = fetch_rank("5day")
    top = [c for c, _ in sorted(today.items(), key=lambda x: x[1]["rank"])[:200]]
    quotes = fetch_quotes(top)
    payload = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": "eastmoney+sina",
        "n_rank_today": len(today),
        "n_rank_5day": len(d5),
        "n_quotes": len(quotes),
        "rank_today": today,
        "rank_5day": d5,
        "quotes": quotes,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print("saved", OUT, {k: payload[k] for k in ("n_rank_today", "n_rank_5day", "n_quotes")})


if __name__ == "__main__":
    main()
