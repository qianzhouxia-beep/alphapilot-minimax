#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 a-stock-data 的新浪备胎拉 120 日资金流，写入 data/fund_flow_history.json。

背景:
  - 东财 push2his 在上海 IP 被封（pull_fundflow_120d.py 已熔断）
  - 通达信 tdxhub 可用，但单票仅约 20 日
  - 参考 https://github.com/simonlin1212/a-stock-data 的 fund_flow_backup()

产出 schema（与现网一致）:
  { bare_code: { "YYYY-MM-DD": main_net(元, float), ... } }

字段选择:
  优先 r0_net（超大单净流入，接近主力），缺失时回退 netamount。
  注意：与通达信主力净额口径不同，成功拉到新浪后按股票整段覆盖，避免混口径。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path("/home/ubuntu/alphapilot")
OUT = BASE / "data" / "fund_flow_history.json"
PROGRESS = BASE / "data" / "fund_flow_sina_progress.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


def load_json(path: Path, default=None):
    if default is None:
        default = {}
    if not path.exists():
        return default
    raw = path.read_text(encoding="utf-8", errors="ignore")
    if not raw.strip():
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        i = raw.rfind("},")
        if i > 0:
            try:
                return json.loads(raw[: i + 1] + "}")
            except json.JSONDecodeError:
                pass
        return default


def bare(sym) -> str:
    s = str(sym).strip()
    if "." in s:
        s = s.split(".")[0]
    return s.zfill(6)[-6:]


def sina_prefix(code: str) -> str:
    if code.startswith(("6", "9")):
        return "sh" + code
    if code.startswith(("8", "4")):
        return "bj" + code
    return "sz" + code


def fetch_sina(code: str, days: int = 120, retries: int = 3) -> dict:
    """返回 {date: main_net}；失败返回 {}。"""
    pre = sina_prefix(code)
    url = (
        "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        f"MoneyFlow.ssl_qsfx_zjlrqs?page=1&num={days}&sort=opendate&asc=0&daima={pre}"
    )
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": UA, "Referer": "https://finance.sina.com.cn/"},
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                t = r.read().decode("utf-8", "ignore")
            try:
                arr = json.loads(t)
            except json.JSONDecodeError:
                arr = json.loads(t[t.index("["): t.rindex("]") + 1])
            out = {}
            for x in arr or []:
                d = x.get("opendate")
                if not d:
                    continue
                # 优先超大单净流入，回退净流入
                val = x.get("r0_net", None)
                if val is None or val == "":
                    val = x.get("netamount", 0)
                try:
                    out[str(d)[:10]] = float(val)
                except (TypeError, ValueError):
                    continue
            return out
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"{code} sina fail: {last_err}")


def stock_universe() -> list:
    os.chdir(BASE)
    try:
        from data_fetcher import get_stock_list
        return [bare(s) for s in get_stock_list()["symbol"].tolist()]
    except Exception:
        # fallback: existing history keys
        hist = load_json(OUT, {})
        return sorted(bare(k) for k in hist.keys())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=120)
    ap.add_argument("--interval", type=float, default=0.25, help="请求间隔秒")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 只（调试）")
    ap.add_argument("--resume", action="store_true", help="跳过已有深度≥days*0.8 的股票")
    ap.add_argument("--save-every", type=int, default=50)
    args = ap.parse_args()

    os.chdir(BASE)
    (BASE / "data").mkdir(exist_ok=True)

    codes = stock_universe()
    if args.limit:
        codes = codes[: args.limit]
    hist = load_json(OUT, {})
    hist = {bare(k): v for k, v in hist.items() if isinstance(v, dict)}

    print(f"=== 新浪资金流备胎拉取 (a-stock-data fund_flow_backup) ===")
    print(f"股票: {len(codes)} | days={args.days} | interval={args.interval}s")

    # 探针：前 3 只必须成功，否则停
    probe_ok = 0
    for c in codes[:3]:
        try:
            d = fetch_sina(c, args.days)
            print(f"  probe {c}: {len(d)} days")
            if len(d) >= 40:
                probe_ok += 1
                hist[c] = d
        except Exception as e:
            print(f"  probe {c}: FAIL {e}")
    if probe_ok == 0:
        print("❌ 新浪探针失败，中止（不覆盖现有文件）")
        sys.exit(2)
    print(f"✅ 探针通过 {probe_ok}/3，开始全量")

    ok = probe_ok
    fail = 0
    skipped = 0
    t0 = time.time()

    for i, code in enumerate(codes):
        if i < 3:
            # 已在探针处理
            continue
        if args.resume and code in hist and len(hist[code]) >= int(args.days * 0.8):
            skipped += 1
            continue
        try:
            d = fetch_sina(code, args.days)
            if d:
                hist[code] = d
                ok += 1
            else:
                fail += 1
        except Exception as e:
            fail += 1
            if fail <= 5 or fail % 50 == 0:
                print(f"  FAIL {code}: {e}")
        time.sleep(args.interval)

        done = i + 1
        if done % args.save_every == 0 or done == len(codes):
            OUT.write_text(json.dumps(hist, ensure_ascii=False), encoding="utf-8")
            depths = [len(v) for v in hist.values() if v]
            mean_d = sum(depths) / len(depths) if depths else 0
            PROGRESS.write_text(
                json.dumps(
                    {
                        "done": done,
                        "total": len(codes),
                        "ok": ok,
                        "fail": fail,
                        "skipped": skipped,
                        "mean_depth": round(mean_d, 2),
                        "elapsed_s": int(time.time() - t0),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            print(
                f"  [{done}/{len(codes)}] ok={ok} fail={fail} skip={skipped} "
                f"mean_depth={mean_d:.1f} elapsed={int(time.time()-t0)}s"
            )

    OUT.write_text(json.dumps(hist, ensure_ascii=False), encoding="utf-8")
    depths = [len(v) for v in hist.values() if v]
    mean_d = sum(depths) / len(depths) if depths else 0
    print(f"\n✅ 完成: stocks={len(hist)} ok={ok} fail={fail} mean_depth={mean_d:.1f}")
    print(f"输出: {OUT}")


if __name__ == "__main__":
    main()
