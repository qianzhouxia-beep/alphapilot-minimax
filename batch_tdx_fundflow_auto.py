#!/usr/bin/env python3
"""
Top100 TDX 历史资金流批量采集脚本
- 从 daily_recommend.json 读取 Top 50 股票
- 直连 TDX API 拉取历史资金流
- 合并到现有缓存
- 保存 daily + cache 文件
"""

import json
import time
import urllib.request
import urllib.error
import os
import sys
from datetime import date

TDX_URL = "http://tdxhub.icfqs.com:7615/TQLEX?Entry=TdxSharePCCW.tdxf10_gg_jyds"
OUTPUT_DIR = "/home/ubuntu/alphapilot/output/multisource"
DAILY_FILE = os.path.join(OUTPUT_DIR, "fundflow_tdx_daily.json")
CACHE_FILE = os.path.join(OUTPUT_DIR, "fundflow_tdx_cache.json")

# ColName 映射 (从原始响应解析)
COL_MAP = {
    "N001": "main_net",       # 主力净额金额(元)
    "N002": "main_net_pct",   # 主力净额占比(%)
    "N003": "super_large_net", # 超大单净买入金额(元)
    "N004": "super_large_pct", # 超大单净买入占比(%)
    "N005": "large_net",      # 大单净买入金额(元)
    "N006": "large_pct",      # 大单净买入占比(%)
    "N015": "close",          # 收盘价
}

def fetch_tdx(code):
    """调用 TDX API 获取单只股票的资金流"""
    body = json.dumps({"Params": [code, "zjlx", ""]}).encode("utf-8")
    req = urllib.request.Request(
        TDX_URL,
        data=body,
        headers={"Content-Type": "application/json"}
    )
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        raw = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "error": str(e)}

    # 解析原始响应
    try:
        result_sets = raw.get("ResultSets", [])
        if not result_sets:
            return {"ok": False, "error": "Empty ResultSets"}

        rs = result_sets[0]
        col_names = rs.get("ColName", [])
        contents = rs.get("Content", [])

        if not contents or len(contents) == 0:
            return {"ok": True, "records": []}

        # 构建索引映射
        idx_map = {}
        key_order = ["N001", "N002", "N003", "N004", "N005", "N006", "N015"]
        for k in key_order:
            if k in col_names:
                idx_map[k] = col_names.index(k)

        if "N001" not in idx_map and "N003" not in idx_map:
            # 可能是空数据或格式不同
            return {"ok": True, "records": []}

        records = []
        for row in contents:
            rec = {}
            for key, col_key in [("date", None)]:
                pass  # 日期在 ColName 中可能为字符串

            # 提取日期 - 第一列通常是日期字符串
            date_col_idx = 0
            date_val = str(row[date_col_idx]) if len(row) > 0 else ""
            # 清理日期格式
            date_val = date_val.strip().replace("'", "")

            n001 = float(row[idx_map["N001"]]) if "N001" in idx_map and idx_map["N001"] < len(row) and row[idx_map["N001"]] not in (None, "--", "") else 0
            n003 = float(row[idx_map["N003"]]) if "N003" in idx_map and idx_map["N003"] < len(row) and row[idx_map["N003"]] not in (None, "--", "") else 0
            n005 = float(row[idx_map["N005"]]) if "N005" in idx_map and idx_map["N005"] < len(row) and row[idx_map["N005"]] not in (None, "--", "") else 0
            n015 = float(row[idx_map["N015"]]) if "N015" in idx_map and idx_map["N015"] < len(row) and row[idx_map["N015"]] not in (None, "--", "") else 0

            records.append({
                "date": date_val,
                "main_net": n001,
                "super_large_net": n003,
                "large_net": n005,
                "close": n015
            })

        return {"ok": True, "records": records}

    except Exception as e:
        return {"ok": False, "error": f"Parse error: {e}"}


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 1. 读取 daily_recommend.json 获取股票代码
    rec_path = "/home/ubuntu/alphapilot/output/daily_recommend.json"
    d = json.load(open(rec_path))
    all_codes = [r["symbol"] for r in d.get("recommendations", [])[:100] if r.get("symbol")]
    total = len(all_codes)
    print(f"📊 Total stocks to fetch: {total}")

    # 2. 读取现有缓存
    cache = {}
    if os.path.exists(CACHE_FILE):
        try:
            cache = json.load(open(CACHE_FILE))
            print(f"📦 Existing cache: {len(cache)} stocks")
        except:
            print("⚠️  Cache read error, starting fresh")

    # 3. 批量拉取
    results = {}
    success = 0
    empty = 0
    failed = 0

    for i, code in enumerate(all_codes):
        # 跳过已缓存的
        if code in cache and len(cache[code].get("records", [])) > 0:
            print(f"  [{i+1}/{total}] {code} ⏭️ cached")
            results[code] = cache[code]
            continue

        time.sleep(0.15)  # 0.15s 间隔
        resp = fetch_tdx(code)

        if resp["ok"]:
            records = resp["records"]
            entry = {
                "source": "tdx_mcp",
                "records": records,
                "updated": date.today().isoformat()
            }
            results[code] = entry
            cache[code] = entry

            if len(records) > 0:
                success += 1
                print(f"  [{i+1}/{total}] {code} ✅ {len(records)} records (last: {records[-1]['date']})")
            else:
                empty += 1
                print(f"  [{i+1}/{total}] {code} ⚠️  0 records")
        else:
            failed += 1
            print(f"  [{i+1}/{total}] {code} ❌ {resp.get('error','')}")
            # 保留旧缓存（如果有）
            if code in cache:
                results[code] = cache[code]

        # 每 10 只批量保存
        if (i + 1) % 10 == 0:
            print(f"  --- Progress: {i+1}/{total} | S=✅{success} ⚠️{empty} ❌{failed} ---")

    # 4. 也包含旧缓存中不在本批次的股票
    for code, entry in cache.items():
        if code not in results:
            results[code] = entry

    # 5. 保存文件
    # daily: 仅本批次的
    with open(DAILY_FILE, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Saved daily: {DAILY_FILE} ({len(results)} stocks)")

    # cache: 全部历史
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    print(f"💾 Saved cache: {CACHE_FILE} ({len(cache)} stocks)")

    # 6. 统计
    total_records = sum(len(e.get("records", [])) for e in results.values())
    print(f"\n{'='*50}")
    print(f"📈 采集完成")
    print(f"  本批: {total} 只股票")
    print(f"  ✅ 成功: {success}")
    print(f"  ⚠️  空数据: {empty}")
    print(f"  ❌ 失败: {failed}")
    print(f"  缓存总计: {len(cache)} 只股票")
    print(f"  总记录数: {total_records} 条")
    print(f"{'='*50}")

    # 输出状态文件供外部读取
    status = {
        "total": total,
        "success": success,
        "empty": empty,
        "failed": failed,
        "cache_stocks": len(cache),
        "total_records": total_records,
        "daily_file": DAILY_FILE,
        "cache_file": CACHE_FILE,
    }
    with open("/tmp/fundflow_batch_status.json", "w") as f:
        json.dump(status, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
