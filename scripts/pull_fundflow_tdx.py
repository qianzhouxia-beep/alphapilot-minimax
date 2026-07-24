#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通达信 tdxhub 全市场资金流历史拉取 → data/fund_flow_history.json

API（现网已验证）:
  POST http://tdxhub.icfqs.com:7615/TQLEX?Entry=TdxSharePCCW.tdxf10_gg_jyds
  body: {"Params":["600519","zjlx",""]}

产出 schema:
  { "600519": {"YYYY-MM-DD": main_net, ...}, ... }

用法（建议在上海机跑）:
  python3 scripts/pull_fundflow_tdx.py --probe
  python3 scripts/pull_fundflow_tdx.py --concurrency 8
  python3 scripts/pull_fundflow_tdx.py --replace-prod
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
if not (ROOT / "data").exists() and Path("/home/ubuntu/alphapilot/data").exists():
    ROOT = Path("/home/ubuntu/alphapilot")

OUT = ROOT / "data" / "fund_flow_history.tdx.json"
PROG = ROOT / "data" / "fund_flow_tdx_progress.json"
PROD = ROOT / "data" / "fund_flow_history.json"
BACKUP = ROOT / "data" / "fund_flow_history.prev_backup.json"
TDX_URL = "http://tdxhub.icfqs.com:7615/TQLEX?Entry=TdxSharePCCW.tdxf10_gg_jyds"

S = requests.Session()
S.trust_env = False
S.headers.update({"Content-Type": "application/json", "User-Agent": "AlphaPilot-TDX/1.0"})


def bare(code: str) -> str:
    s = str(code or "").lower().replace("sh", "").replace("sz", "").replace("bj", "")
    return s[-6:]


def parse_records(raw: dict) -> dict[str, float]:
    """兼容 Data/rows 与 ResultSets 两种返回。"""
    hist: dict[str, float] = {}

    # 格式 A: Data[0].rows[{日期, 主力净额金额(元)}]
    tables = raw.get("Data") or []
    if tables:
        rows = tables[0].get("rows") or []
        for row in rows:
            d = str(row.get("日期") or row.get("date") or "")[:10]
            v = row.get("主力净额金额(元)", row.get("main_net"))
            if d and v not in (None, "", "--"):
                try:
                    hist[d] = float(v)
                except Exception:
                    pass
        if hist:
            return hist

    # 格式 B: ResultSets[0].ColName + Content
    rss = raw.get("ResultSets") or []
    if not rss:
        return hist
    rs = rss[0]
    cols = rs.get("ColName") or []
    contents = rs.get("Content") or []
    if not contents:
        return hist

    # 日期列：优先名字含日期，否则第 0 列
    date_idx = 0
    for i, c in enumerate(cols):
        if "日期" in str(c) or str(c).lower() == "date":
            date_idx = i
            break
    main_idx = None
    for key in ("N001", "主力净额金额(元)", "主力净额"):
        if key in cols:
            main_idx = cols.index(key)
            break
    if main_idx is None:
        # 常见：N001 就是主力净额
        if "N001" in cols:
            main_idx = cols.index("N001")
        elif len(cols) > 1:
            main_idx = 1

    for row in contents:
        if not row:
            continue
        d = str(row[date_idx]).strip().replace("'", "")[:10]
        if len(d) == 8 and d.isdigit():
            d = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        try:
            v = float(row[main_idx]) if main_idx is not None and main_idx < len(row) else None
        except Exception:
            v = None
        if d and v is not None:
            hist[d] = v
    return hist


def fetch_one(code: str) -> dict[str, float]:
    code = bare(code)
    r = S.post(TDX_URL, json={"Params": [code, "zjlx", ""]}, timeout=20)
    r.raise_for_status()
    return parse_records(r.json())


def list_codes_from_kline() -> list[str]:
    import pandas as pd

    for p in [
        ROOT / "data/kline_cache/kline_all.parquet",
        ROOT / "kline_all.parquet",
    ]:
        if p.exists():
            df = pd.read_parquet(p, columns=["symbol"])
            codes = sorted({bare(x) for x in df["symbol"].astype(str).tolist() if bare(x).isdigit()})
            return codes
    # fallback: existing fund history keys
    if PROD.exists():
        d = json.loads(PROD.read_text(encoding="utf-8"))
        return sorted(bare(k) for k in d.keys())
    return []


def probe(sample: list[str]) -> None:
    for c in sample:
        t0 = time.time()
        try:
            h = fetch_one(c)
            ds = sorted(h)
            print(
                f"{c}: days={len(ds)} range={ds[0] if ds else None}~{ds[-1] if ds else None} "
                f"last={h.get(ds[-1]) if ds else None} {time.time()-t0:.2f}s"
            )
        except Exception as e:
            print(f"{c}: FAIL {e}")
        time.sleep(0.15)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--sample", default="600519,000858,000034,300750")
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--replace-prod", action="store_true", help="写回 fund_flow_history.json（先备份）")
    ap.add_argument(
        "--overlay",
        action="store_true",
        default=True,
        help="用 TDX 近端覆盖已有长历史（默认开；tdxhub~20日）",
    )
    ap.add_argument("--no-overlay", action="store_true", help="整库替换为纯 TDX（仅约20日）")
    args = ap.parse_args()
    if args.no_overlay:
        args.overlay = False

    if args.probe:
        probe([bare(x) for x in args.sample.split(",") if x.strip()])
        return

    codes = list_codes_from_kline()
    if args.limit:
        codes = codes[: args.limit]
    print(f"=== TDX 资金流拉取 codes={len(codes)} concurrency={args.concurrency}")

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
        for a in range(3):
            try:
                h = fetch_one(c)
                return c, h, None
            except Exception as e:
                time.sleep(0.4 * (a + 1) + random.random() * 0.2)
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
                if fail <= 20:
                    print("fail", c, err)
            if i % 50 == 0 or i == len(futs):
                PROG.parent.mkdir(parents=True, exist_ok=True)
                PROG.write_text(
                    json.dumps({"data": data, "ok": ok, "fail": fail, "ts": time.time()}, ensure_ascii=False),
                    encoding="utf-8",
                )
                depths = [len(v) for v in data.values()]
                mean = sum(depths) / len(depths) if depths else 0
                print(
                    f"  {i}/{len(futs)} ok={ok} fail={fail} mean_days={mean:.1f} {int(time.time()-t0)}s",
                    flush=True,
                )
            time.sleep(0.05)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    depths = [len(v) for v in data.values()]
    mean = sum(depths) / len(depths) if depths else 0
    print("saved", OUT, "stocks", len(data), "mean_days", round(mean, 1))

    if args.replace_prod:
        if PROD.exists() and not BACKUP.exists():
            BACKUP.write_text(PROD.read_text(encoding="utf-8"), encoding="utf-8")
            print("backup", BACKUP)
        # 默认：长历史保留 + TDX 近端覆盖（tdxhub 仅约 20 日）
        if args.overlay and PROD.exists():
            base = json.loads(PROD.read_text(encoding="utf-8"))
            n_over = 0
            for k, v in data.items():
                if not isinstance(v, dict) or not v:
                    continue
                cur = dict(base.get(k) or {})
                cur.update(v)
                base[k] = cur
                n_over += 1
            PROD.write_text(json.dumps(base, ensure_ascii=False), encoding="utf-8")
            print("overlay-prod", PROD, "tdx_stocks", n_over, "total", len(base))
        else:
            PROD.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            print("replaced", PROD)


if __name__ == "__main__":
    main()
