# -*- coding: utf-8 -*-
"""
服务器端收盘资金流全自动回填（替代本地 WorkBuddy automation-1784036531028）
=====================================================================
数据源: tdxhub 直连（http://tdxhub.icfqs.com:7615/TQLEX），无需 token / MCP / 本地 WorkBuddy
流程:
  1) 从 output/daily_recommend.json + morning_live_picks.json + score_top10.json 取推荐股并集
  2) tdxhub 批量拉取每只近20日主力净额（N001 列, 倒序, 最新在前）
  3) 计算 main_net_today / 5d / 10d
  4) 合并更新 data/fund_flow_cache.json（⚠️ 只更新推荐股，保留全市场 ~5000 只）
  5) 回填三个文件: daily_recommend / morning_live_picks / score_top10
  6) 日期校验: tdxhub 最新日期必须 == 当日, 否则跳过回填（防止用旧数据伪装今日）
用法: python3 server_close_fundflow.py [--force]
cron: 15 16 * * 1-5  (收盘后 16:15, 确保当日数据已就绪)
"""
import json, os, sys, time, urllib.request, subprocess
from datetime import datetime, date

BASE = "/home/ubuntu/alphapilot"
URL = "http://tdxhub.icfqs.com:7615/TQLEX?Entry=TdxSharePCCW.tdxf10_gg_jyds"
CACHE = os.path.join(BASE, "data", "fund_flow_cache.json")
LOG = os.path.join(BASE, "output", "logs", "server_close_fundflow.log")

def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def today_str():
    return date.today().strftime("%Y-%m-%d")

def fetch_tdxhub(code, retries=3):
    """tdxhub 拉取主力净额, 返回 [(rq, N001), ...] 倒序(最新在前), 失败返回 None"""
    body = json.dumps({"Params": [code, "zjlx", ""]}).encode()
    for i in range(retries):
        try:
            req = urllib.request.Request(URL, data=body, headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0",
            })
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.loads(r.read().decode())
            rs = d.get("ResultSets") or []
            if not rs:
                return None
            col = rs[0].get("ColName") or []
            i_net = col.index("N001") if "N001" in col else 1
            content = rs[0].get("Content") or []
            rows = [(row[0], float(row[i_net])) for row in content if len(row) > i_net]
            return rows if rows else None
        except Exception as e:
            if i == retries - 1:
                log(f"  {code} 拉取失败({retries}次): {type(e).__name__} {e}")
                return None
            time.sleep(3 * (i + 1))
    return None

def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def collect_symbols():
    """从三个输出文件收集推荐股并集（symbol 6位）"""
    syms = {}
    for fname, key in [
        ("output/daily_recommend.json", "recommendations"),
        ("output/morning_live_picks.json", "picks"),
        ("output/score_top10.json", "items"),
    ]:
        d = load_json(os.path.join(BASE, fname))
        if not d:
            log(f"  [warn] 无法读取 {fname}")
            continue
        for it in d.get(key) or []:
            sym = str(it.get("symbol") or "")[-6:]
            if len(sym) == 6 and sym.isdigit():
                syms.setdefault(sym, it.get("name") or "")
    return syms

def patch_recommend_file(fname, key, cache):
    """通用回填: morning_live_picks(picks) / score_top10(items)"""
    path = os.path.join(BASE, fname)
    d = load_json(path)
    if not d:
        log(f"  [warn] {fname} 无法读取, 跳过")
        return 0
    try:
        sys.path.insert(0, BASE)
        from light_categorize import classify_phase_v18
    except Exception:
        classify_phase_v18 = None
    updated = 0
    for it in d.get(key) or []:
        sym = str(it.get("symbol") or "")[-6:]
        fc = cache.get(sym)
        if not fc:
            continue
        it["main_net"] = fc.get("main_net_today", it.get("main_net", 0))
        it["main_net_5d"] = fc.get("main_net_5d", 0)
        it["main_net_10d"] = fc.get("main_net_10d", 0)
        it["main_net_20d"] = fc.get("main_net_20d", 0)
        it["fund_days"] = fc.get("fund_days", 0)
        it["fund_source"] = fc.get("fund_source", "tdxhub")
        abr = 0.5 + fc.get("main_net_5d", 0) / 2e9
        it["active_buy_ratio"] = round(max(0.30, min(0.95, abr)), 4)
        if classify_phase_v18:
            try:
                ph, pl = classify_phase_v18(it)
                it["money_phase"] = ph
                it["money_phase_label"] = pl
            except Exception as e:
                log(f"  [{sym}] classify err: {e}")
        updated += 1
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    return updated

def main():
    force = "--force" in sys.argv
    log("=" * 60)
    log("收盘资金流自动回填 开始")

    # 1) 收集推荐股
    syms = collect_symbols()
    log(f"推荐股并集: {len(syms)} 只: {list(syms.keys())}")
    if not syms:
        log("无推荐股, 退出"); return

    # 2) tdxhub 批量拉取
    result = {}
    latest_ok = True
    for i, code in enumerate(syms, 1):
        rows = fetch_tdxhub(code)
        if not rows:
            continue
        latest = rows[0][0]
        flows = [v for _, v in rows]
        if latest != today_str():
            if not force:
                log(f"  [{i}/{len(syms)}] {code}: ⚠️ 最新日期 {latest} != 今日 {today_str()}, 数据未就绪(force 可跳过校验)")
                latest_ok = False
                continue
            log(f"  [{i}/{len(syms)}] {code}: ⚠️ 最新 {latest}(force 模式仍写入)")
        result[code] = {
            "main_net_today": round(flows[0], 2),
            "main_net_5d": round(sum(flows[:5]), 2),
            "main_net_10d": round(sum(flows[:10]), 2),
            "fund_days": min(10, len(flows)),
            "fund_source": "tdxhub",
            "today_date": latest.replace("-", ""),
            "last_date": latest,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        log(f"  [{i}/{len(syms)}] {code} {syms[code]}: {latest} today={result[code]['main_net_today']/1e8:+.2f}亿 5d={result[code]['main_net_5d']/1e8:+.2f}亿 10d={result[code]['main_net_10d']/1e8:+.2f}亿")
        time.sleep(0.3)

    if not result:
        log("全部拉取失败, 退出"); return
    if not latest_ok and not force:
        log("存在非今日数据且未 force, 跳过回填"); return

    # 3) 合并更新全市场缓存（只更新推荐股）
    cache = load_json(CACHE) or {}
    n_before = len(cache)
    for code, v in result.items():
        cache[code] = v
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    log(f"缓存合并: 更新 {len(result)} 只, 总 {n_before} -> {len(cache)} 只")

    # 4) 回填 daily_recommend.json（复用 fund_flow.enrich_recommendations）
    try:
        sys.path.insert(0, BASE)
        os.chdir(BASE)
        from fund_flow import enrich_recommendations
        n1 = enrich_recommendations()
        log(f"daily_recommend 回填: {n1} 只")
    except Exception as e:
        log(f"daily_recommend 回填失败: {type(e).__name__} {e}")

    # 5) 回填 morning_live_picks + score_top10
    n2 = patch_recommend_file("output/morning_live_picks.json", "picks", cache)
    log(f"morning_live_picks 回填: {n2} 只")
    n3 = patch_recommend_file("output/score_top10.json", "items", cache)
    log(f"score_top10 回填: {n3} 只")

    log(f"完成 ✅  推荐 {len(result)} 只 / daily {n1} / morning {n2} / top10 {n3}")
    log("=" * 60)

if __name__ == "__main__":
    main()
