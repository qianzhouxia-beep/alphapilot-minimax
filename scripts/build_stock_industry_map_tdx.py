#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用通达信（mootdx F10）拉全市场股票→行业映射。

数据源：Quotes.F10() → 公司概况「行业类别」
  例：食品饮料-白酒Ⅱ-白酒Ⅲ / 电子-半导体-集成电路制造 / 银行-国有大型银行Ⅱ-国有大型银行Ⅲ

产出:
  data/stock_industry_map.json
    {
      "600519": {
        "name": "贵州茅台",
        "industry": "白酒Ⅲ",          # 最细（供门控匹配）
        "industry_l1": "食品饮料",
        "industry_l2": "白酒Ⅱ",
        "industry_l3": "白酒Ⅲ",
        "industry_path": "食品饮料-白酒Ⅱ-白酒Ⅲ",
        "source": "tdx_f10"
      },
      ...
    }

用法（建议上海机）:
  python3 scripts/build_stock_industry_map_tdx.py
  python3 scripts/build_stock_industry_map_tdx.py --concurrency 16
  python3 scripts/build_stock_industry_map_tdx.py --limit 100
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path("/home/ubuntu/alphapilot")
if not (ROOT / "data").exists():
    ROOT = Path(__file__).resolve().parents[1]

DATA = ROOT / "data"
OUT = DATA / "stock_industry_map.json"
PROG = DATA / "stock_industry_map_tdx_progress.json"
LOG = DATA / "stock_industry_map_tdx.log"


def bare(code: str) -> str:
    s = str(code or "").lower().replace("sh", "").replace("sz", "").replace("bj", "")
    return s[-6:] if s else ""


def is_a_share(code: str) -> bool:
    c = bare(code)
    if not (c.isdigit() and len(c) == 6):
        return False
    # 排除明显指数/债券：9 开头多数为指数；8/4 北交所可选保留
    if c.startswith("9"):
        return False
    return True


def list_codes() -> list[str]:
    """优先用交易相关股票池，避免 mootdx.stocks() 混入大量无效代码。"""
    codes = set()
    # 1) 资金流库（最贴近交易股票池，约 5000）
    ff = DATA / "fund_flow_history.json"
    if ff.exists():
        try:
            d = json.loads(ff.read_text(encoding="utf-8"))
            codes.update(bare(k) for k in d.keys())
            print(f"codes from fund_flow_history: {len(codes)}", flush=True)
        except Exception as e:
            print("fund_flow_history read fail:", e, flush=True)

    # 2) K 线 parquet symbol
    for kp in (
        DATA / "kline_cache" / "kline_all.parquet",
        ROOT / "kline_all.parquet",
    ):
        if not kp.exists():
            continue
        try:
            import pandas as pd

            s = pd.read_parquet(kp, columns=["symbol"])["symbol"].astype(str).map(bare)
            before = len(codes)
            codes.update(x for x in s.unique().tolist() if is_a_share(x))
            print(f"codes after kline {kp.name}: +{len(codes)-before} -> {len(codes)}", flush=True)
            break
        except Exception as e:
            print("kline read fail:", e, flush=True)

    # 3) 仅当上面都空时，才退回 mootdx（并严格过滤）
    if len(codes) < 1000:
        try:
            from mootdx.quotes import Quotes

            q = Quotes.factory(market="std")
            df = q.stocks()
            if df is not None and len(df):
                for c, name in zip(df["code"].astype(str), df["name"].astype(str)):
                    bc = bare(c)
                    # 排除名称含「指数」等
                    if "指数" in name or "基金" in name:
                        continue
                    if is_a_share(bc) and (
                        bc.startswith(("00", "30", "60", "68")) or bc.startswith(("8", "4"))
                    ):
                        codes.add(bc)
            print(f"codes after mootdx filter: {len(codes)}", flush=True)
        except Exception as e:
            print("mootdx stocks fail:", e, flush=True)

    # 最终：只要主板/创业/科创/北交常见号段
    out = sorted(
        c
        for c in codes
        if is_a_share(c)
        and (
            c.startswith(("000", "001", "002", "003", "300", "301", "600", "601", "603", "605", "688", "689"))
            or c.startswith(("8", "4"))
        )
    )
    return out


def parse_industry_path(text: str) -> str | None:
    if not text:
        return None
    # 行业类别｜食品饮料-白酒Ⅱ-白酒Ⅲ
    m = re.search(r"行业类别\s*｜\s*([^｜\r\n]+)", text)
    if m:
        p = m.group(1).strip().replace(" ", "").replace("　", "")
        if p and p != "-":
            return p
    # 【所属行业】\n食品饮料--白酒Ⅱ--白酒Ⅲ共(21)家
    m = re.search(r"【所属行业】\s*[\r\n]+\s*([^\r\n]+)", text)
    if m:
        p = m.group(1).strip()
        p = re.sub(r"共\(\d+\)家.*$", "", p)
        p = p.replace("--", "-").replace(" ", "")
        if p:
            return p
    return None


def split_path(path: str) -> tuple[str, str, str, str]:
    parts = [x for x in path.replace("--", "-").split("-") if x]
    l1 = parts[0] if len(parts) > 0 else ""
    l2 = parts[1] if len(parts) > 1 else ""
    l3 = parts[2] if len(parts) > 2 else ""
    # 门控用最细一层；没有则退回上一级
    finest = l3 or l2 or l1
    return finest, l1, l2, l3


def fetch_one(code: str) -> dict | None:
    from mootdx.quotes import Quotes

    q = Quotes.factory(market="std")
    last_err = None
    for attempt in range(3):
        try:
            f = q.F10(symbol=code)
            if not isinstance(f, dict):
                return None
            path = parse_industry_path(str(f.get("公司概况") or ""))
            if not path:
                path = parse_industry_path(str(f.get("行业分析") or ""))
            if not path:
                return None
            finest, l1, l2, l3 = split_path(path)
            # 尝试简称
            name = ""
            gk = str(f.get("公司概况") or "")
            m = re.search(r"证券简称\s*｜\s*([^｜\r\n]+)", gk)
            if m:
                name = m.group(1).strip()
            return {
                "name": name,
                "industry": finest,
                "industry_l1": l1,
                "industry_l2": l2,
                "industry_l3": l3,
                "industry_path": path,
                "source": "tdx_f10",
            }
        except Exception as e:
            last_err = e
            time.sleep(0.25 * (attempt + 1))
    if last_err:
        raise last_err
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, default=12)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--codes", default="", help="逗号分隔测试代码")
    args = ap.parse_args()

    os.chdir(ROOT)
    DATA.mkdir(parents=True, exist_ok=True)

    if args.codes:
        codes = [bare(x) for x in args.codes.split(",") if bare(x)]
    else:
        codes = list_codes()
    if args.limit:
        codes = codes[: args.limit]

    data = {}
    if PROG.exists():
        try:
            data = json.loads(PROG.read_text(encoding="utf-8")).get("data") or {}
            print("resume", len(data), flush=True)
        except Exception:
            data = {}

    todo = [c for c in codes if c not in data]
    print(
        f"=== TDX F10 行业映射 codes={len(codes)} todo={len(todo)} "
        f"concurrency={args.concurrency}",
        flush=True,
    )

    ok = fail = 0
    t0 = time.time()

    def worker(c):
        try:
            info = fetch_one(c)
            return c, info, None
        except Exception as e:
            return c, None, str(e)

    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as ex:
        futs = [ex.submit(worker, c) for c in todo]
        for i, fut in enumerate(as_completed(futs), 1):
            c, info, err = fut.result()
            if info:
                data[c] = info
                ok += 1
            else:
                fail += 1
                if fail <= 30:
                    print(f"  fail {c} {err or 'empty'}", flush=True)
            if i % 50 == 0 or i == len(futs):
                PROG.write_text(
                    json.dumps(
                        {"data": data, "ok": ok, "fail": fail, "ts": time.time()},
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                print(
                    f"  {i}/{len(futs)} ok={ok} fail={fail} "
                    f"total_map={len(data)} {int(time.time()-t0)}s",
                    flush=True,
                )

    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    # 简单质检
    sample = {k: data[k] for k in list(data)[:5]}
    l1s = {}
    for v in data.values():
        l1 = v.get("industry_l1") or ""
        l1s[l1] = l1s.get(l1, 0) + 1
    top_l1 = sorted(l1s.items(), key=lambda x: -x[1])[:15]
    print("saved", OUT, "stocks", len(data), "ok", ok, "fail", fail)
    print("top_l1", top_l1)
    print("sample", json.dumps(sample, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
