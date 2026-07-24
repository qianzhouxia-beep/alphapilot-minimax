#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""东财个股资金流历史批量拉取（与 stock-sdk / Cursor MCP 同源）。

输出对齐 fund_flow_history.json: {code: {date: main_net, ...}}
推荐在本机 Windows 跑（上海机东财 120d 常被墙），完成后 scp 到服务器。

用法:
  python scripts/pull_fundflow_em.py --validate
  python scripts/pull_fundflow_em.py --concurrency 8
  python scripts/pull_fundflow_em.py --limit 20
"""
from __future__ import annotations

import argparse
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "fund_flow_history.stock_sdk.json"
PROG = ROOT / "data" / "fund_flow_em_progress.json"
OLD = ROOT / "data" / "fund_flow_history.json"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
SESSION = requests.Session()
SESSION.trust_env = False  # 避开本机坏代理
SESSION.headers.update({"User-Agent": UA, "Referer": "https://data.eastmoney.com/"})


def bare(code: str) -> str:
    s = str(code or "").lower().replace("sh", "").replace("sz", "").replace("bj", "")
    return s[-6:]


def secid(code: str) -> str:
    c = bare(code)
    if c.startswith(("5", "6", "9")):
        return f"1.{c}"
    return f"0.{c}"


def fetch_hist(code: str, lmt: int = 120) -> dict[str, float]:
    """返回 {YYYY-MM-DD: mainNetInflow}。"""
    url = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
    params = {
        "lmt": lmt,
        "klt": 101,
        "secid": secid(code),
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
        "_": str(int(time.time() * 1000)),
    }
    r = SESSION.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json().get("data") or {}
    klines = data.get("klines") or []
    hist = {}
    for row in klines:
        # date,mainNet,small,med,large,superLarge,...
        parts = str(row).split(",")
        if len(parts) < 2:
            continue
        d = parts[0][:10]
        try:
            hist[d] = float(parts[1])
        except ValueError:
            continue
    return hist


def list_a_share_codes() -> list[str]:
    """东财全 A 列表（轻量）。"""
    url = "https://80.push2.eastmoney.com/api/qt/clist/get"
    codes = []
    for fs in ("m:1+t:2,m:1+t:23", "m:0+t:6,m:0+t:80"):
        page = 1
        while True:
            params = {
                "pn": page,
                "pz": 100,
                "po": 1,
                "np": 1,
                "fltt": 2,
                "invt": 2,
                "fid": "f12",
                "fs": fs,
                "fields": "f12,f14",
            }
            r = SESSION.get(url, params=params, timeout=20)
            r.raise_for_status()
            diff = (r.json().get("data") or {}).get("diff") or []
            if not diff:
                break
            for it in diff:
                c = bare(it.get("f12"))
                if c.isdigit() and len(c) == 6:
                    codes.append(c)
            if len(diff) < 100:
                break
            page += 1
            time.sleep(0.05)
    return sorted(set(codes))


def validate(sample: list[str]) -> None:
    old = {}
    if OLD.exists():
        old = json.loads(OLD.read_text(encoding="utf-8"))
    report = []
    for code in sample:
        hist = fetch_hist(code)
        o = old.get(bare(code)) or {}
        dates = sorted(hist)
        diffs = []
        agree = cmp = 0
        for d in dates[-5:]:
            if d not in o:
                continue
            cmp += 1
            a, b = float(hist[d]), float(o[d])
            if abs(a - b) / max(1.0, abs(b)) < 0.05:
                agree += 1
            else:
                diffs.append({"date": d, "em": a, "sina": b})
        report.append(
            {
                "code": bare(code),
                "em_days": len(dates),
                "em_first": dates[0] if dates else None,
                "em_last": dates[-1] if dates else None,
                "compare_n": cmp,
                "agree_5pct": agree,
                "diffs": diffs,
            }
        )
        time.sleep(0.2)
    outp = ROOT / "output" / "fund_flow_sdk_vs_sina.json"
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps({"source": "eastmoney", "report": report}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("saved", outp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--sample", default="000034,600519,000858")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    if args.validate:
        validate([bare(x) for x in args.sample.split(",") if x.strip()])
        return

    out_path = Path(args.out)
    codes = list_a_share_codes()
    if args.limit:
        codes = codes[: args.limit]
    print(f"codes={len(codes)} concurrency={args.concurrency}")

    data = {}
    if PROG.exists():
        try:
            data = json.loads(PROG.read_text(encoding="utf-8")).get("data") or {}
            print("resume", len(data))
        except Exception:
            pass
    todo = [c for c in codes if c not in data]
    ok = fail = 0
    t0 = time.time()

    def one(c):
        for attempt in range(3):
            try:
                h = fetch_hist(c)
                if h:
                    return c, h, None
                return c, {}, "empty"
            except Exception as e:
                time.sleep(0.3 * (attempt + 1) + random.random() * 0.2)
                err = str(e)
        return c, {}, err

    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = [ex.submit(one, c) for c in todo]
        for i, fut in enumerate(as_completed(futs), 1):
            c, h, err = fut.result()
            if h:
                data[c] = h
                ok += 1
            else:
                fail += 1
            if i % 50 == 0 or i == len(futs):
                PROG.parent.mkdir(parents=True, exist_ok=True)
                PROG.write_text(
                    json.dumps({"data": data, "ok": ok, "fail": fail, "ts": time.time()}, ensure_ascii=False),
                    encoding="utf-8",
                )
                print(f"  {i}/{len(futs)} ok={ok} fail={fail} {int(time.time()-t0)}s", flush=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    depths = [len(v) for v in data.values()]
    mean = sum(depths) / len(depths) if depths else 0
    print("saved", out_path, "stocks", len(data), "mean_depth", round(mean, 1), "ok", ok, "fail", fail)


if __name__ == "__main__":
    main()
