#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sources: 数据抓取与落地（K线 / 南向持股 / 池子）。

数据源与坑（实测，见 knowledge/inbox/2026-09-10-hk-us-phase0-probe.md）:
  - HK 日K: web.ifzq.gtimg.cn/appstock/app/hkfqkline/get?param=hk{code},day,,,N,qfq
  - US 日K: .../usfqkline/get?param=us{TICKER}.{EX},day,,,N,qfq   （必须带交易所后缀）
  - 南向持股: datacenter-web.eastmoney.com ...RPT_MUTUAL_STOCK_HOLDRANKS
      * 新加坡 WAF: filter 只 URL 编码【引号】，括号/等号保持原样，否则 400
      * MUTUAL_TYPE 002/004 同构；HOLD_DATE 为 T+1 披露
"""
import time

import config as C
import dataio as io


# ---------------- K线 ----------------
def fetch_hk_kline(code: str, n: int = None) -> list[dict] | None:
    n = n or C.KLINE_N
    url = (f"https://web.ifzq.gtimg.cn/appstock/app/hkfqkline/get?"
           f"param=hk{code},day,,,{n},qfq")
    d = io.get_json(url)
    node = (d.get("data") or {}).get(f"hk{code}") or {}
    rows = node.get("qfqday") or node.get("day") or []
    return _norm_bars(rows)


def fetch_us_kline(ticker: str, exch: str = "OQ", n: int = None) -> list[dict] | None:
    n = n or C.KLINE_N
    sym = f"us{ticker}.{exch}"
    url = (f"https://web.ifzq.gtimg.cn/appstock/app/usfqkline/get?"
           f"param={sym},day,,,{n},qfq")
    d = io.get_json(url)
    node = (d.get("data") or {}).get(sym) or {}
    rows = node.get("qfqday") or node.get("day") or []
    return _norm_bars(rows)


def _norm_bars(rows) -> list[dict] | None:
    out = []
    for r in rows:
        if len(r) < 6 or not str(r[0]).startswith("20"):
            continue
        try:
            out.append({"d": r[0], "o": float(r[1]), "c": float(r[2]),
                        "h": float(r[3]), "l": float(r[4]), "v": float(r[5])})
        except (TypeError, ValueError):
            continue
    return out or None


def update_kline(codes: list[str], market: str = "HK", n: int = None,
                 pause: float = 0.12) -> dict:
    """增量更新日K，返回统计。失败逐只记录，不中断。"""
    kline = io.load(C.F_KLINE, {}) or {}
    fail = {}
    added = 0
    t0 = time.time()
    for i, code in enumerate(codes, 1):
        if code in kline and kline[code]:
            continue
        try:
            bars = fetch_hk_kline(code, n) if market == "HK" else fetch_us_kline(code, n=n)
            if bars:
                kline[code] = bars
                added += 1
            else:
                fail[code] = "empty"
        except Exception as e:  # noqa: BLE001
            fail[code] = str(e)[:100]
        if i % 100 == 0:
            io.save_atomic(kline, C.F_KLINE)
        time.sleep(pause)
    io.save_atomic(kline, C.F_KLINE)
    return {"codes": len(codes), "added": added, "fail": len(fail),
            "fail_sample": dict(list(fail.items())[:5]), "sec": int(time.time() - t0)}


def refresh_kline_tail(codes: list[str], market: str = "HK") -> dict:
    """刷新全部（用于每日增量；K线上方 update 跳过已存在，需 daily_update 判断尾部）。"""
    kline = io.load(C.F_KLINE, {}) or {}
    fail = {}
    upd = 0
    for code in codes:
        try:
            bars = fetch_hk_kline(code) if market == "HK" else fetch_us_kline(code)
            if bars:
                if not kline.get(code) or bars[-1]["d"] >= kline[code][-1]["d"]:
                    kline[code] = bars
                    upd += 1
        except Exception as e:  # noqa: BLE001
            fail[code] = str(e)[:80]
        time.sleep(0.12)
    io.save_atomic(kline, C.F_KLINE)
    return {"updated": upd, "fail": len(fail)}


# ---------------- 南向持股 ----------------
def fetch_south_cross_section(date: str, mutual_type: str = "002") -> dict:
    """某持股日的全市场截面 -> {code: {...}}。WAF 安全 filter。"""
    f = f'(MUTUAL_TYPE="{mutual_type}")(INTERVAL_TYPE="1")(HOLD_DATE=\'{date}\')'
    fenc = f.replace('"', "%22").replace("'", "%27")   # 只编码引号（SG WAF）
    out = {}
    page = 1
    while True:
        url = ("https://datacenter-web.eastmoney.com/api/data/v1/get?"
               "sortColumns=HOLD_DATE,SECURITY_CODE&sortTypes=-1,1&pageSize=500"
               f"&pageNumber={page}&reportName=RPT_MUTUAL_STOCK_HOLDRANKS&columns=ALL"
               f"&filter={fenc}")
        d = io.get_json(url)
        res = d.get("result") or {}
        rows = res.get("data") or []
        for r in rows:
            code = r.get("SECURITY_CODE")
            if not code:
                continue
            out[code] = {"r": r.get("HOLD_SHARES_RATIO"), "s": r.get("HOLD_SHARES"),
                         "m": r.get("HOLD_MARKET_CAP"), "chg": r.get("HOLD_SHARES_CHANGE"),
                         "amp": r.get("ADD_SHARES_AMP")}
        if page * 500 >= (res.get("count") or 0) or not rows:
            break
        page += 1
        time.sleep(0.25)
    return out


def update_southbound(dates: list[str]) -> dict:
    """增量补齐缺失的持股日截面。"""
    hist = io.load(C.F_SOUTH, {}) or {}
    added = 0
    for d in dates:
        if d in hist and hist[d]:
            continue
        try:
            xs = fetch_south_cross_section(d)
            if xs:
                hist[d] = xs
                added += 1
            time.sleep(0.25)
        except Exception as e:  # noqa: BLE001
            print(f"  [south] {d} fail: {str(e)[:80]}")
    io.save_atomic(hist, C.F_SOUTH)
    return {"days": len(hist), "added": added}


# ---------------- 池子 ----------------
def build_pool(kline: dict, south_hist: dict) -> dict:
    """池 = 最新南向截面出现过的港股通标的，过流动性 + K线完整度。"""
    latest = max(south_hist.keys())
    xs = south_hist[latest]
    rows = []
    for code, hold in xs.items():
        bars = kline.get(code)
        if not bars or len(bars) < C.POOL_MIN_BARS:
            continue
        amts = sorted(b["c"] * b["v"] for b in bars[-60:])
        med = amts[len(amts) // 2]
        if med < C.POOL_MIN_MED_AMOUNT:
            continue
        rows.append({"code": code, "med_amt": med, "hold_ratio": hold.get("r"),
                     "hold_cap": hold.get("m")})
    rows.sort(key=lambda r: -(r["hold_cap"] or 0))
    pool = {"date": latest, "asof_kline": max(b[-1]["d"] for b in kline.values() if b),
            "n": len(rows), "codes": [r["code"] for r in rows], "rows": rows}
    io.save_atomic(pool, C.F_POOL)
    return pool
