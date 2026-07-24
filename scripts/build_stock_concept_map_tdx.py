#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通达信题材/概念映射（快轮动锋面）。

数据源: tdxhub
  POST TQLEX?Entry=TdxSharePCCW.tdxf10_gg_rdtc
  Params: [code, "zttzbkz"]

产出 data/stock_concept_map.json:
  {
    "300750": {
      "name": "宁德时代",
      "concepts": ["固态电池", "储能", "锂电池概念", "新能源车", ...],
      "raw_count": 24,
      "source": "tdx_rdtc"
    }
  }

用法:
  python3 scripts/build_stock_concept_map_tdx.py --concurrency 20
"""
from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

ROOT = Path("/home/ubuntu/alphapilot")
if not (ROOT / "data").exists():
    ROOT = Path(__file__).resolve().parents[1]

DATA = ROOT / "data"
OUT = DATA / "stock_concept_map.json"
PROG = DATA / "stock_concept_map_tdx_progress.json"
TDX_URL = "http://tdxhub.icfqs.com:7615/TQLEX?Entry=TdxSharePCCW.tdxf10_gg_rdtc"

# 标签型/风格型噪声，不参与轮动判断
CONCEPT_NOISE = {
    "通达信88",
    "通达信热股",
    "含H股",
    "含GDR",
    "大盘股",
    "小盘股",
    "中盘股",
    "非周期股",
    "周期股",
    "百元股",
    "昨成交20",
    "昨成交50",
    "基金重仓",
    "保险重仓",
    "社保重仓",
    "QFII重仓",
    "高分红股",
    "高应收款",
    "行业龙头",
    "定增股",
    "并购重组股",
    "股权转让",
    "ST板块",
    "融资融券",
    "深股通",
    "沪股通",
    "标普道琼斯",
    "富时罗素",
    "MSCI中国",
    "机构重仓",
    "一线龙头",
    "二线龙头",
    "中特估",
    "中字头",
    "B股",
    "次新股",
    "注册制次新股",
    "新股与次新股",
}


def bare(code: str) -> str:
    s = str(code or "").lower().replace("sh", "").replace("sz", "").replace("bj", "")
    return s[-6:]


def list_codes() -> list[str]:
    codes = set()
    ff = DATA / "fund_flow_history.json"
    if ff.exists():
        d = json.loads(ff.read_text(encoding="utf-8"))
        codes.update(bare(k) for k in d)
    ind = DATA / "stock_industry_map.json"
    if ind.exists():
        d = json.loads(ind.read_text(encoding="utf-8"))
        codes.update(bare(k) for k in d)
    allow_pref = (
        "000",
        "001",
        "002",
        "003",
        "300",
        "301",
        "600",
        "601",
        "603",
        "605",
        "688",
        "689",
    )
    return sorted(c for c in codes if c.isdigit() and len(c) == 6 and c.startswith(allow_pref))


def is_noise(name: str) -> bool:
    n = str(name or "").strip()
    if not n or n in CONCEPT_NOISE:
        return True
    for kw in ("重仓", "股通", "罗素", "MSCI", "成交", "盘股", "季报", "年报", "预减", "预增", "中特估", "中字头"):
        if kw in n:
            return True
    return False


def fetch_concepts(code: str) -> dict | None:
    S = requests.Session()
    S.trust_env = False
    S.headers.update({"Content-Type": "application/json", "User-Agent": "AlphaPilot-TDX/1.0"})
    last_err = None
    for attempt in range(3):
        try:
            r = S.post(TDX_URL, json={"Params": [code, "zttzbkz"]}, timeout=20)
            r.raise_for_status()
            j = r.json()
            if j.get("ErrorCode") not in (0, "0", None) and j.get("ErrorCode") != 0:
                # some responses use ErrorCode 0 only
                if j.get("ErrorCode"):
                    raise RuntimeError(j.get("ErrorInfo") or j.get("ErrorCode"))
            rs = (j.get("ResultSets") or [{}])[0]
            cols = rs.get("ColName") or []
            rows = rs.get("Content") or []
            try:
                i_name = cols.index("ztmc")
            except ValueError:
                i_name = 2
            concepts = []
            for row in rows:
                if not isinstance(row, list) or len(row) <= i_name:
                    continue
                name = str(row[i_name]).strip()
                if is_noise(name):
                    continue
                if name not in concepts:
                    concepts.append(name)
            return {
                "concepts": concepts,
                "raw_count": len(rows),
                "source": "tdx_rdtc",
            }
        except Exception as e:
            last_err = e
            time.sleep(0.25 * (attempt + 1))
    raise RuntimeError(str(last_err))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, default=20)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--codes", default="")
    args = ap.parse_args()

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

    # 附带名称
    names = {}
    ip = DATA / "stock_industry_map.json"
    if ip.exists():
        try:
            im = json.loads(ip.read_text(encoding="utf-8"))
            for k, v in im.items():
                if isinstance(v, dict) and v.get("name"):
                    names[bare(k)] = v["name"]
        except Exception:
            pass

    todo = [c for c in codes if c not in data]
    print(f"=== TDX 概念映射 codes={len(codes)} todo={len(todo)} conc={args.concurrency}", flush=True)

    ok = fail = 0
    t0 = time.time()

    def one(c):
        try:
            info = fetch_concepts(c)
            info["name"] = names.get(c, "")
            return c, info, None
        except Exception as e:
            return c, None, str(e)

    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as ex:
        futs = [ex.submit(one, c) for c in todo]
        for i, fut in enumerate(as_completed(futs), 1):
            c, info, err = fut.result()
            if info is not None:
                data[c] = info
                ok += 1
            else:
                fail += 1
                if fail <= 20:
                    print("fail", c, err, flush=True)
            if i % 50 == 0 or i == len(futs):
                PROG.write_text(
                    json.dumps({"data": data, "ok": ok, "fail": fail, "ts": time.time()}, ensure_ascii=False),
                    encoding="utf-8",
                )
                print(
                    f"  {i}/{len(futs)} ok={ok} fail={fail} map={len(data)} {int(time.time()-t0)}s",
                    flush=True,
                )

    OUT.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    # stats
    n_c = [len(v.get("concepts") or []) for v in data.values()]
    mean = sum(n_c) / len(n_c) if n_c else 0
    print("saved", OUT, "stocks", len(data), "mean_concepts", round(mean, 1), "ok", ok, "fail", fail)


if __name__ == "__main__":
    main()
