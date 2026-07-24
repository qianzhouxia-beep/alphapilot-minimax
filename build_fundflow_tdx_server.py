#!/usr/bin/env python3
import json, os, time, requests
from pathlib import Path

OUTPUT_DIR = "/home/ubuntu/alphapilot/output/multisource"
DAILY_FILE = os.path.join(OUTPUT_DIR, "fundflow_tdx_daily.json")
CACHE_FILE = os.path.join(OUTPUT_DIR, "fundflow_tdx_cache.json")
TDX_URL = "http://tdxhub.icfqs.com:7615/TQLEX"
today = time.strftime("%Y-%m-%d")

def fetch_one(code):
    try:
        resp = requests.post(f"{TDX_URL}?Entry=TdxSharePCCW.tdxf10_gg_jyds", json={"Params":[code,"zjlx",""]}, timeout=15)
        data = resp.json()
        tables = data.get("Data", [])
        if not tables:
            return None
        capital_flow = tables[0].get("rows", [])
        records = []
        for row in capital_flow:
            records.append({"date":row.get("日期",""),"main_net":row.get("主力净额金额(元)",0),"super_large_net":row.get("超大单净买入金额(元)",0),"large_net":row.get("大单净买入金额(元)",0),"close":row.get("收盘价",0)})
        return records if records else None
    except Exception as e:
        print(f"  [ERR] {code}: {e}")
        return None

def main():
    with open("/home/ubuntu/alphapilot/output/daily_recommend.json") as f:
        rec = json.load(f)
    codes = [r["symbol"] for r in rec.get("recommendations",[])[:100] if r.get("symbol")]
    print(f"[INFO] 获取到 {len(codes)} 只股票")
    
    cache = {}
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE) as f:
            cache = json.load(f)
    daily = {}
    
    total = len(codes)
    for i, code in enumerate(codes, 1):
        print(f"[{i}/{total}] {code} ...", end=" ", flush=True)
        records = fetch_one(code)
        if records:
            entry = {"source":"tdx_mcp","records":records,"updated":today}
            daily[code] = entry
            cache[code] = entry
            print(f"{len(records)} 条", flush=True)
        else:
            print("空数据", flush=True)
        if i % 10 == 0:
            print(f"  --- 进度: {i}/{total} ---", flush=True)
        time.sleep(0.1)
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(DAILY_FILE, "w") as f:
        json.dump(daily, f, ensure_ascii=False, default=int)
    print(f"[OK] daily 文件保存: {DAILY_FILE} ({len(daily)} 只)")
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, ensure_ascii=False, default=int)
    print(f"[OK] cache 文件保存: {CACHE_FILE} ({len(cache)} 只累计)")
    
    empty = total - len(daily)
    total_records = sum(len(v["records"]) for v in daily.values())
    print(f"\n=== 完成统计 ===")
    print(f"总股票: {total}")
    print(f"完整数据: {len(daily)} 只")
    print(f"空数据: {empty} 只")
    print(f"总记录数: {total_records} 条")
    print(f"cache 累计: {len(cache)} 只")

if __name__ == "__main__":
    main()
