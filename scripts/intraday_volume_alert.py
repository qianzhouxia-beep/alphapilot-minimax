#!/usr/bin/env python3
"""
P4 盘中量比异动监测 — 追量不追价，捕捉起涨前兆

三个领先指标：
  ① 异常量比 — 当前1分钟成交量 > 前5分钟均量的 3 倍
  ② 盘口失衡 — 主动买入占比 > 65% 且持续放大
  ③ 板块联动 — 同板块 >=3 只同时触发异动

运行时机: 10:00, 10:30, 14:00 各跑一次
输出: output/intraday_volume_alert.json
"""
import json
import os
import sys
import time
from collections import defaultdict, Counter
from datetime import datetime
from pathlib import Path

import requests
import numpy as np

ROOT = Path("/home/ubuntu/alphapilot")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

OUTPUT = ROOT / "output" / "intraday_volume_alert.json"
INDUSTRY_MAP_PATH = ROOT / "data" / "stock_industry_map.json"

TENCENT_API = "https://qt.gtimg.cn/q="
BATCH = 80
TIMEOUT = 10
VOL_SURGE_THRESHOLD = 3.0  # 量比阈值
ACTIVE_BUY_THRESHOLD = 0.65  # 主动买入占比
SECTOR_LINKAGE_MIN = 3  # 板块联动最少只数

_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://gu.qq.com/",
}


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _bare(sym: str) -> str:
    return str(sym).replace("sh", "").replace("sz", "").replace("bj", "")[-6:]


def _prefix(sym: str) -> str:
    if sym.startswith("6"):
        return "sh"
    if sym.startswith(("4", "8", "9")):
        return "bj"
    return "sz"


def fetch_quotes(symbols: list[str]) -> dict[str, dict]:
    out = {}
    for i in range(0, len(symbols), BATCH):
        chunk = symbols[i:i + BATCH]
        secs = [_prefix(s) + s for s in chunk]
        try:
            r = requests.get(TENCENT_API, params={"q": ",".join(secs)},
                             headers=_HEADERS, timeout=TIMEOUT)
            for line in r.text.strip().split(";"):
                if "=" not in line:
                    continue
                body = line.split('="', 1)[1].rsplit('"', 1)[0]
                f = body.split("~")
                if len(f) < 48:
                    continue
                try:
                    sym = f[2][-6:] if len(f[2]) >= 6 else f[2]
                    out[sym] = {
                        "price": float(f[3]),
                        "volume": float(f[6]),
                        "amount": float(f[37]),
                        "turnover": float(f[38]) if len(f) > 38 else 0,
                        "change_pct": float(f[32]),
                        "vol_ratio": float(f[47]) if len(f) > 47 else 1.0,
                        "active_buy": float(f[7]) / max(float(f[7]) + float(f[8]), 1) if len(f) > 8 else 0.5,
                    }
                except (ValueError, IndexError):
                    continue
        except Exception:
            continue
    return out


def load_industry_map() -> dict:
    if not INDUSTRY_MAP_PATH.exists():
        return {}
    try:
        return json.loads(INDUSTRY_MAP_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def detect_volume_surge(quotes: dict, industry_map: dict) -> dict:
    """检测量比异动 + 板块联动"""
    alerts = []

    # 1. 个股异动
    for sym, q in quotes.items():
        vol_ratio = q.get("vol_ratio", 1.0)
        active_buy = q.get("active_buy", 0.5)
        chg = q.get("change_pct", 0)
        turnover = q.get("turnover", 0)

        if vol_ratio < VOL_SURGE_THRESHOLD:
            continue
        if chg > 5:  # 已经涨起来的不算"起涨前兆"
            continue
        if turnover < 0.5:  # 换手太低无意义
            continue

        alert = {
            "symbol": sym,
            "vol_ratio": round(vol_ratio, 2),
            "active_buy": round(active_buy, 2),
            "change_pct": round(chg, 2),
            "price": q["price"],
            "amount_wan": round(q["amount"], 0),
            "signal": "vol_surge",
            "confidence": "high" if (vol_ratio > 5 and active_buy > 0.7) else "medium",
        }

        # 盘口失衡信号
        if active_buy > ACTIVE_BUY_THRESHOLD and vol_ratio > 2:
            alert["signal"] = "order_imbalance"
            alert["confidence"] = "high"

        alerts.append(alert)

    # 2. 板块联动
    sector_alerts = defaultdict(list)
    for a in alerts:
        sym = a["symbol"]
        imap = industry_map.get(sym, {})
        sector = imap.get("industry_l1", "其他")
        sector_alerts[sector].append(a)
        a["sector"] = sector

    # 3. 标记联动板块
    linked_sectors = []
    for sector, sector_list in sector_alerts.items():
        if len(sector_list) >= SECTOR_LINKAGE_MIN:
            linked_sectors.append(sector)
            for a in sector_list:
                a["sector_linkage"] = True
                a["sector_linkage_count"] = len(sector_list)

    # 4. 排序（联动板块优先，量比降序）
    alerts.sort(key=lambda x: (
        -(x.get("sector_linkage_count", 0)),
        -x.get("vol_ratio", 0)
    ))

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "n_alerts": len(alerts),
        "n_linked_sectors": len(linked_sectors),
        "linked_sectors": linked_sectors,
        "alerts": alerts[:30],  # Top30
    }


def main():
    log("P4 盘中量比异动监测")

    # 1. 获取池内候选
    rec_path = ROOT / "output" / "daily_recommend.json"
    symbols = []
    if rec_path.exists():
        try:
            data = json.loads(rec_path.read_text(encoding="utf-8"))
            items = data.get("recommendations", data.get("items", []))
            symbols = [str(it.get("symbol", ""))[-6:] for it in items[:100] if it.get("symbol")]
        except Exception:
            pass

    if not symbols:
        log("无候选池，扫描全市场样本")
        # 降级方案：扫描有代表性的股票
        industry_map = load_industry_map()
        symbols = list(industry_map.keys())[:500]

    # 2. 拉行情
    t0 = time.time()
    quotes = fetch_quotes(symbols)
    log(f"行情拉取: {len(quotes)}/{len(symbols)} 只, {time.time()-t0:.1f}s")

    # 3. 检测
    industry_map = load_industry_map()
    result = detect_volume_surge(quotes, industry_map)

    # 4. 输出
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    log(f"异动: {result['n_alerts']} 只, 联动板块: {result['n_linked_sectors']} 个")
    for a in result["alerts"][:5]:
        link = f" [联动×{a.get('sector_linkage_count','')}]" if a.get("sector_linkage") else ""
        log(f"  {a['symbol']} {a.get('sector','?')} vol={a['vol_ratio']:.1f}x ab={a['active_buy']:.0%} {a['signal']}{link}")


if __name__ == "__main__":
    main()
