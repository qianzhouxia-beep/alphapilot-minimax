# -*- coding: utf-8 -*-
"""
全市场资金流历史库构建器（服务器端直连通达信 tdxhub，无需 token/桌面 MCP）

接口: POST http://tdxhub.icfqs.com:7615/TQLEX?Entry=TdxSharePCCW.tdxf10_gg_jyds
body: {"Params": [code, "zjlx", ""]}
返回: ResultSets[0].Content 每行 [rq(日期), N001(主力净额), ..., N015(收盘价)]  约20天

输出: data/fund_flow_history.json = {bare_code: {"YYYY-MM-DD": main_net, ...}}
每次运行与已有历史 **合并**（累积延长窗口），保证 point-in-time 训练样本随时间增多。
"""
import json
import time
import urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from data_fetcher import get_stock_list

BASE = Path(__file__).parent
OUT = BASE / "data" / "fund_flow_history.json"
URL = "http://tdxhub.icfqs.com:7615/TQLEX?Entry=TdxSharePCCW.tdxf10_gg_jyds"
WORKERS = 30
RETRY = 2


def pull_one(code):
    """拉单只资金流历史 -> {date: main_net}，失败返回 None"""
    body = json.dumps({"Params": [code, "zjlx", ""]}).encode()
    for attempt in range(RETRY + 1):
        try:
            req = urllib.request.Request(
                URL, data=body, headers={"Content-Type": "application/json"}
            )
            raw = urllib.request.urlopen(req, timeout=15).read().decode()
            d = json.loads(raw)
            rs = d.get("ResultSets") or []
            if not rs or d.get("ErrorCode", -1) != 0:
                return None
            content = rs[0].get("Content") or []
            colname = rs[0].get("ColName") or []
            if "rq" not in colname or "N001" not in colname:
                return None
            i_rq = colname.index("rq")
            i_net = colname.index("N001")
            hist = {}
            for row in content:
                try:
                    date = str(row[i_rq])[:10]
                    net = float(row[i_net])
                    hist[date] = net
                except (ValueError, TypeError, IndexError):
                    continue
            return hist if hist else None
        except Exception:
            if attempt < RETRY:
                time.sleep(0.3)
            continue
    return None


def load_existing():
    if OUT.exists():
        try:
            return json.load(open(OUT, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def main():
    t0 = time.time()
    df = get_stock_list()
    codes = [str(s).zfill(6) for s in df["symbol"].tolist()]
    print(f"全市场股票: {len(codes)} 只，开始拉取资金流历史 (workers={WORKERS})...")

    merged = load_existing()
    print(f"已有历史库: {len(merged)} 只")

    ok = 0
    fail = 0
    done = 0
    results = {}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(pull_one, c): c for c in codes}
        for fut in as_completed(futs):
            code = futs[fut]
            done += 1
            try:
                hist = fut.result()
            except Exception:
                hist = None
            if hist:
                results[code] = hist
                ok += 1
            else:
                fail += 1
            if done % 500 == 0:
                print(f"  进度 {done}/{len(codes)}  成功={ok} 失败={fail}  用时{time.time()-t0:.0f}s")

    # 合并：新数据按日期覆盖/补充旧数据（累积延长窗口）
    for code, hist in results.items():
        if code in merged and isinstance(merged[code], dict):
            merged[code].update(hist)
        else:
            merged[code] = hist

    OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump(merged, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)

    # 统计天数分布
    daycounts = [len(v) for v in merged.values() if isinstance(v, dict)]
    avg_days = sum(daycounts) / len(daycounts) if daycounts else 0
    print(f"\n✅ 完成: 本次成功 {ok} 只 / 失败 {fail} 只")
    print(f"   历史库总计 {len(merged)} 只，平均 {avg_days:.1f} 天/只")
    print(f"   输出: {OUT}  ({OUT.stat().st_size/1024/1024:.1f} MB)")
    print(f"   总用时: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
