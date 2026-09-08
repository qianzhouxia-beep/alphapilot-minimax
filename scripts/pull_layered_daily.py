#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""收盘后全A四层资金日度积累（2026-09-02 起，方向3 数据基建）。

背景：用户假设「大盘资金方向（机构/量化/大户/散户）决定追高是否危险」需
分层资金历史回测。调查结论（knowledge/inbox/2026-09-02-layered-flow-data-sources.md）：
  - Wind 四层 = 东财同源的委托单大小切分（超大/大/中/小单），需 API 授权 → 否决
  - 东财 push2his 历史四层接口在本地与服务器均被拒（网络层）→ 历史不可回补
  - 东财 push2delay 实时接口服务器可用，收盘后含当日全量四层 → 从今日起自积累
产出：data/layered_flow_daily/YYYY-MM-DD.json（逐日，幂等可重跑）。

字段语义（与 live_fund_flow.py 08-18 修复后一致）：
  f62=主力净流入 f66=超大单 f72=大单 f78=中单 f84=小单（元）；f124=数据时间戳
分层对应：超大单+大单≈机构/大户，中单≈中户/量化代理，小单≈散户（按委托单大小切分）。

用法：
  python3 scripts/pull_layered_daily.py [--date YYYY-MM-DD] [--force]
cron：工作日 21:05（build_fund_flow 21:00 之后错峰）
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "layered_flow_daily"

import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://data.eastmoney.com/",
}
_URL = "https://push2delay.eastmoney.com/api/qt/ulist.np/get"
_UT = "7eea3edcaed734bea9telecast"
_FLOW_FIELDS = "f2,f3,f12,f14,f62,f66,f72,f78,f84,f124"
CHUNK = 100
SLEEP = 0.25
MIN_OK = 4800  # 覆盖阈值：低于即判失败，不写盘


def _secid(c: str) -> str:
    return f"{'1' if c.startswith('6') else '0'}.{c}"


def fetch_codes(codes: list[str]) -> tuple[dict, str]:
    """全量分页拉取，返回 {code: row} 与数据时间戳字符串。"""
    out: dict[str, dict] = {}
    max_ts = 0
    n_fail = 0
    for i in range(0, len(codes), CHUNK):
        part = codes[i:i + CHUNK]
        params = {
            "secids": ",".join(_secid(c) for c in part),
            "fields": _FLOW_FIELDS,
            "fltt": "2", "invt": "2", "np": "1", "ut": _UT,
        }
        got = False
        for _attempt in range(4):
            try:
                r = requests.get(_URL, params=params, headers=_HEADERS, timeout=10)
                diff = ((r.json() or {}).get("data") or {}).get("diff") or []
                for it in diff:
                    code = str(it.get("f12") or "")
                    if len(code) == 6 and code.isdigit():
                        out[code] = it
                        try:
                            ts = int(it.get("f124") or 0)
                            if ts > max_ts:
                                max_ts = ts
                        except (TypeError, ValueError):
                            pass
                got = True
                break
            except Exception:
                time.sleep(1.2)
        if not got:
            n_fail += 1
        if (i // CHUNK) % 10 == 9:
            print(f"  [{i + len(part)}/{len(codes)}] ok={len(out)} fail_chunks={n_fail}", flush=True)
        time.sleep(SLEEP)
    ts_s = ""
    if max_ts:
        try:
            ts_s = datetime.fromtimestamp(max_ts).strftime("%Y-%m-%d %H:%M:%S")
        except (OverflowError, OSError, ValueError):
            ts_s = str(max_ts)
    return out, ts_s


def _f(v, default: float = 0.0) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    return default if x != x else x  # nan guard


def _tot(out: dict, field: str) -> float:
    s = 0.0
    for it in out.values():
        s += _f(it.get(field))
    return round(s, 2)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    out_dir = OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"{args.date}.json"
    if dst.exists() and not args.force:
        print(f"exists {dst} (--force 重跑)")
        return 0

    try:
        from data_fetcher import get_stock_list
    except Exception as e:
        print(f"get_stock_list 失败: {e}")
        return 1
    df = get_stock_list()
    codes = sorted(str(s).split(".")[0].zfill(6) for s in df["symbol"].tolist())
    print(f"=== 全A四层积累 {args.date} codes={len(codes)} ===")
    if not codes:
        print("空清单")
        return 1

    t0 = time.time()
    out, ts_s = fetch_codes(codes)
    print(f"拉取完成: ok={len(out)}/{len(codes)} elapsed={time.time()-t0:.0f}s ts={ts_s}")

    if len(out) < MIN_OK:
        print(f"覆盖不足 ok={len(out)} < {MIN_OK} → 不写盘（可重试）")
        return 2

    super_large = _tot(out, "f66")
    large = _tot(out, "f72")
    mid = _tot(out, "f78")
    small = _tot(out, "f84")
    main_net = _tot(out, "f62")
    stocks = {}
    for code, it in out.items():
        stocks[code] = {
            "name": it.get("f14"),
            "price": _f(it.get("f2")),
            "change_pct": _f(it.get("f3")),
            "main_net": _f(it.get("f62")),
            "super_large_net": _f(it.get("f66")),
            "large_net": _f(it.get("f72")),
            "mid_net": _f(it.get("f78")),
            "small_net": _f(it.get("f84")),
        }
    payload = {
        "date": args.date,
        "pulled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data_ts": ts_s,
        "n_codes": len(codes),
        "n_ok": len(out),
        "market_yi": {
            "main_net": round(main_net / 1e8, 2),
            "super_large_net": round(super_large / 1e8, 2),
            "large_net": round(large / 1e8, 2),
            "mid_net": round(mid / 1e8, 2),
            "small_net": round(small / 1e8, 2),
        },
        "stocks": stocks,
    }
    tmp = dst.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(dst)
    print(f"✅ {dst} ({len(stocks)} 只) market_yi={payload['market_yi']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
