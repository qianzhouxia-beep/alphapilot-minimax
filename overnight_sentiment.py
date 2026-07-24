"""隔夜情绪因子 V2 — 美股板块+龙头股 → A股板块映射

权重原则（2026-07-21）：
  - 外盘隔夜映射权重 > 昨日 A 股收盘板块资金叙事
  - 收盘研报描述的是「已发生」的 1/2/3/5 日资金结构，用于趋势判断，不直接等于次日流入
  - 美股板块大涨（如半导体）应对次日相关 A 股给更明显的分数优势
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
US_FACTORS = OUT / "us_enhanced_factors.json"
OVERNIGHT_JSON = OUT / "overnight_sentiment.json"
OVERNIGHT_SIGNALS = OUT / "overnight_signals.json"

# 打分乘子：score *= (1 + overnight_bonus)；overnight_bonus = raw_sector_bonus * WEIGHT
OVERNIGHT_SCORE_WEIGHT = float(os.environ.get("OVERNIGHT_SCORE_WEIGHT", "0.45") or 0.45)
# raw 板块加分相对旧版放大（旧版最大约 ±0.03/源）
BONUS_SCALE = float(os.environ.get("OVERNIGHT_BONUS_SCALE", "2.2") or 2.2)

# ==================== 美股- A股板块映射表 ====================
US_SECTOR_MAP = [
    ("gb_nvda", "英伟达", ["AI芯片", "算力", "光模块", "半导体", "通信", "电子"]),
    ("gb_amd", "AMD", ["芯片", "半导体", "CPU", "算力", "电子"]),
    ("gb_aapl", "苹果", ["消费电子", "果链", "苹果概念", "电子"]),
    ("gb_msft", "微软", ["软件", "AI", "云计算", "办公", "计算机"]),
    ("gb_meta", "Meta", ["元宇宙", "VR", "社交", "AI"]),
    ("gb_goog", "谷歌", ["AI", "云计算", "广告", "搜索"]),
    ("gb_amzn", "亚马逊", ["云计算", "电商", "物流"]),
    ("gb_smci", "超微电脑", ["算力", "服务器", "AI芯片"]),
    ("gb_tsm", "台积电", ["半导体", "芯片", "代工", "电子"]),
    ("gb_avgo", "博通", ["芯片", "网络", "通信", "半导体"]),
    ("gb_qcom", "高通", ["芯片", "通信", "5G", "半导体"]),
    ("gb_tsla", "特斯拉", ["新能源车", "锂电池", "汽车零部件", "自动驾驶", "电力设备"]),
    ("gb_rivn", "Rivian", ["新能源车"]),
    ("gb_lcid", "Lucid", ["新能源车"]),
    ("gb_xpev", "小鹏", ["新能源车"]),
    ("gb_nio", "蔚来", ["新能源车"]),
    ("gb_li", "理想", ["新能源车"]),
    ("gb_mcd", "麦当劳", ["消费", "餐饮"]),
    ("gb_nke", "耐克", ["运动", "服装", "消费", "商贸零售"]),
    ("gb_sbux", "星巴克", ["消费", "餐饮"]),
    ("gb_unh", "联合健康", ["医药", "医疗", "保险", "医药生物"]),
    ("gb_jnj", "强生", ["医药", "医疗", "医药生物"]),
    ("gb_pfe", "辉瑞", ["医药", "创新药", "医药生物"]),
    ("gb_lly", "礼来", ["医药", "创新药", "减肥药", "医药生物"]),
    ("gb_jpm", "摩根大通", ["银行", "金融", "券商", "非银金融"]),
    ("gb_gs", "高盛", ["券商", "金融", "投行", "非银金融"]),
    ("gb_bac", "美国银行", ["银行", "金融"]),
    ("gb_xom", "埃克森美孚", ["石油", "石化", "能源", "石油石化"]),
    ("gb_cvx", "雪佛龙", ["石油", "能源", "石油石化"]),
    ("gb_oxy", "西方石油", ["石油", "能源", "石油石化"]),
    ("gb_baba", "阿里巴巴", ["互联网", "电商", "平台"]),
    ("gb_pdd", "拼多多", ["电商", "消费", "商贸零售"]),
    ("gb_bidu", "百度", ["AI", "自动驾驶", "搜索"]),
    ("gb_jd", "京东", ["电商", "物流", "商贸零售"]),
    ("gb_ntes", "网易", ["游戏", "互联网"]),
]

US_ETF_MAP = [
    ("gb_smh", "半导体ETF", ["半导体", "芯片", "电子"]),
    ("gb_xlk", "科技ETF", ["科技", "软件", "通信", "计算机", "电子"]),
    ("gb_xle", "能源ETF", ["石油", "能源", "石化", "石油石化"]),
    ("gb_xlf", "金融ETF", ["银行", "券商", "保险", "非银金融"]),
    ("gb_xlv", "医疗ETF", ["医药", "医疗", "医药生物"]),
    ("gb_xly", "消费ETF", ["消费", "零售", "商贸零售"]),
    ("gb_arkk", "创新ETF", ["创新药", "AI", "成长"]),
    ("gb_kweb", "中概ETF", ["互联网", "平台", "电商"]),
]


def fetch_us_stocks():
    """从新浪拉取美股行情"""
    symbols = [s[0] for s in US_SECTOR_MAP] + [e[0] for e in US_ETF_MAP]
    url = "https://hq.sinajs.cn/list=" + ",".join(symbols)

    headers = {
        "Referer": "https://finance.sina.com.cn/",
        "User-Agent": "Mozilla/5.0",
    }

    result = {}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            for line in r.text.strip().split("\n"):
                if "hq_str_" not in line:
                    continue
                sym = line.split('"')[0].split("hq_str_")[1].rstrip("= ")
                parts = line.split('"')[1].split(",")
                if len(parts) >= 4:
                    name = parts[0]
                    price = float(parts[1]) if parts[1] else 0
                    change_pct = float(parts[2]) if parts[2] else 0
                    result[sym] = {
                        "name": name,
                        "price": price,
                        "change_pct": round(change_pct, 2),
                    }
    except Exception as e:
        result["_error"] = str(e)[:60]

    return result


def _bonus_from_change(chg: float) -> float:
    """单源涨跌 → 原始板块加分（再乘 BONUS_SCALE）。"""
    if abs(chg) < 0.5:
        bonus = 0.0
    elif abs(chg) < 2:
        bonus = 0.008 * (1 if chg > 0 else -1)
    elif abs(chg) < 4:
        bonus = 0.016 * (1 if chg > 0 else -1)
    elif abs(chg) < 6:
        bonus = 0.028 * (1 if chg > 0 else -1)
    else:
        bonus = 0.04 * (1 if chg > 0 else -1)
    return bonus * BONUS_SCALE


def compute_sector_sentiment(us_data):
    """计算美股板块情绪 → A股板块加分"""
    sector_bonus = {}

    for sym, info in us_data.items():
        if sym.startswith("_") or "change_pct" not in info:
            continue
        chg = info["change_pct"]
        affected_sectors = []
        for us_sym, us_name, a_sectors in US_SECTOR_MAP + US_ETF_MAP:
            if us_sym == sym:
                affected_sectors = a_sectors
                break
        bonus = _bonus_from_change(chg)
        for sec in affected_sectors:
            sector_bonus[sec] = sector_bonus.get(sec, 0) + bonus

    # 单板块加分封顶，避免多龙头重复累加爆炸
    for k, v in list(sector_bonus.items()):
        sector_bonus[k] = max(-0.12, min(0.12, v))
    return sector_bonus


def merge_us_enhanced_factors(sector_bonus: dict, us_data: dict) -> dict:
    """若新浪稀薄，用 us_enhanced_factors.json 的板块影响作补充。"""
    if not US_FACTORS.exists():
        return sector_bonus
    try:
        raw = json.loads(US_FACTORS.read_text(encoding="utf-8"))
    except Exception:
        return sector_bonus

    impacts = raw.get("sector_impacts") or {}
    if isinstance(impacts, dict):
        for name, val in impacts.items():
            try:
                v = float(val)
            except (TypeError, ValueError):
                continue
            # impact 常为小数涨跌或已归一；按幅度映射
            add = _bonus_from_change(v * 100 if abs(v) <= 1.5 else v)
            if abs(add) < 1e-6:
                continue
            sector_bonus[name] = max(
                -0.12, min(0.12, sector_bonus.get(name, 0) + add * 0.6)
            )

    # 补充 overnight_stocks 到 us_data 展示
    ov = raw.get("overnight_stocks") or {}
    if isinstance(ov, dict):
        for k, v in ov.items():
            if isinstance(v, dict) and "change_pct" in v and k not in us_data:
                us_data[k] = v
    return sector_bonus


def get_stock_sector_bonus(symbol, stock_name, sector_bonus, stock_sectors=None):
    """计算单只A股的美股板块映射加分（raw，未乘 SCORE_WEIGHT）。"""
    total_bonus = 0.0
    matched = []

    if stock_name:
        for asec, bonus in sector_bonus.items():
            if asec in stock_name:
                total_bonus += bonus
                matched.append(asec)

    if stock_sectors:
        for s in stock_sectors:
            for asec, bonus in sector_bonus.items():
                if asec in str(s):
                    total_bonus += bonus
                    matched.append(str(s))

    # 去重累加过猛时再裁一次
    total_bonus = max(-0.15, min(0.15, total_bonus))
    return round(total_bonus, 4), matched


def apply_overnight_score(base_score: float, raw_bonus: float) -> tuple[float, float]:
    """返回 (new_score, applied_overnight_bonus)。"""
    applied = float(raw_bonus or 0) * OVERNIGHT_SCORE_WEIGHT
    # 只对正加成大幅加权；负加成也生效但幅度对称
    new_score = float(base_score or 0) * (1.0 + applied)
    return round(new_score, 6), round(applied, 4)


def get_full_overnight_data():
    """完整隔夜数据（含板块映射）并落盘。"""
    us_data = fetch_us_stocks()
    sector_bonus = compute_sector_sentiment(us_data)
    sector_bonus = merge_us_enhanced_factors(sector_bonus, us_data)

    indices = {}
    for sym in ["gb_dji", "gb_ixic", "gb_inx"]:
        if sym in us_data:
            name_map = {"gb_dji": "道琼斯", "gb_ixic": "NASDAQ", "gb_inx": "S&P500"}
            indices[name_map[sym]] = us_data[sym]["change_pct"]

    tech_stocks = {}
    for sym in ["gb_nvda", "gb_amd", "gb_aapl", "gb_msft", "gb_tsla", "gb_smci", "gb_avgo", "gb_tsm"]:
        if sym in us_data and isinstance(us_data[sym], dict):
            tech_stocks[us_data[sym].get("name") or sym] = us_data[sym]["change_pct"]

    all_chgs = [
        v["change_pct"]
        for k, v in us_data.items()
        if isinstance(v, dict) and "change_pct" in v
    ]
    avg_chg = sum(all_chgs) / len(all_chgs) if all_chgs else 0
    sentiment = 0.5 + (avg_chg / 20)

    data = {
        "indices": indices,
        "tech_stocks": tech_stocks,
        "sector_bonus": sector_bonus,
        "sentiment_score": round(min(1.0, max(0.0, sentiment)), 4),
        "avg_us_change": round(avg_chg, 2),
        "overnight_score_weight": OVERNIGHT_SCORE_WEIGHT,
        "bonus_scale": BONUS_SCALE,
        "us_symbol_count": len(all_chgs),
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "sina+us_enhanced_merge",
    }

    OUT.mkdir(parents=True, exist_ok=True)
    OVERNIGHT_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    signals = []
    for name, chg in indices.items():
        if abs(chg) >= 0.3:
            signals.append(f"{name}{chg:+.2f}%")
    for name, chg in list(tech_stocks.items())[:5]:
        if abs(chg) >= 1:
            signals.append(f"{name}{chg:+.2f}%")
    top_sectors = sorted(sector_bonus.items(), key=lambda x: -abs(x[1]))[:5]
    for sec, bonus in top_sectors:
        signals.append(f"A股{sec}{'利好' if bonus > 0 else '利空'}({bonus:+.3f})")

    signals_payload = {
        "sentiment_score": data["sentiment_score"],
        "judgment": "；".join(signals[:8]) if signals else "外盘波动有限",
        "signals": signals,
        "fetched_at": data["fetched_at"],
        "avg_us_change": data["avg_us_change"],
        "top_sectors": [{ "name": s, "bonus": b} for s, b in top_sectors],
    }
    OVERNIGHT_SIGNALS.write_text(
        json.dumps(signals_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return data


def get_overnight_bonus():
    """简洁接口给动态重排/选股用"""
    data = get_full_overnight_data()

    signals = []
    indices = data.get("indices", {})
    tech = data.get("tech_stocks", {})

    for name, chg in indices.items():
        if chg > 0.5:
            signals.append(f"{name}+{chg}%")
        elif chg < -0.5:
            signals.append(f"{name}{chg}%")

    for name, chg in list(tech.items())[:3]:
        if abs(chg) > 1:
            signals.append(f"{name}{chg}%")

    sector_bonus = data.get("sector_bonus", {})
    top_sectors = sorted(sector_bonus.items(), key=lambda x: -abs(x[1]))[:3]
    for sec, bonus in top_sectors:
        direction = "利好" if bonus > 0 else "利空"
        signals.append(f"A股{sec} {direction}")

    return {
        "score": data["sentiment_score"],
        "signals": signals,
        "detail": data,
    }


def check_overnight_freshness(max_age_hours: float = 10.0) -> dict:
    """巡检：隔夜文件是否新鲜、外盘标的是否够用。"""
    now = datetime.now()
    issues = []
    info = {
        "ok": True,
        "checked_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "files": {},
    }

    for label, path in (
        ("overnight_sentiment", OVERNIGHT_JSON),
        ("overnight_signals", OVERNIGHT_SIGNALS),
        ("us_enhanced_factors", US_FACTORS),
    ):
        if not path.exists():
            issues.append(f"missing:{label}")
            info["files"][label] = {"exists": False}
            continue
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        age_h = (now - mtime).total_seconds() / 3600.0
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            issues.append(f"bad_json:{label}:{e}")
            payload = {}
        fetched = payload.get("fetched_at") or payload.get("asof") or ""
        n_bonus = len((payload.get("sector_bonus") or {})) if isinstance(payload, dict) else 0
        n_us = int(payload.get("us_symbol_count") or 0)
        row = {
            "exists": True,
            "mtime": mtime.strftime("%Y-%m-%d %H:%M:%S"),
            "age_hours": round(age_h, 2),
            "fetched_at": fetched,
            "sector_bonus_n": n_bonus,
            "us_symbol_count": n_us,
        }
        info["files"][label] = row
        if age_h > max_age_hours:
            issues.append(f"stale:{label}:age={age_h:.1f}h")
        if label == "overnight_sentiment" and n_us < 5 and n_bonus < 1:
            issues.append(f"thin:{label}:us={n_us},bonus={n_bonus}")

    # 交易日凌晨：要求 overnight 落在「今天」或「昨晚 20:00 之后」
    ov = info["files"].get("overnight_sentiment") or {}
    if ov.get("exists"):
        mt = datetime.strptime(ov["mtime"], "%Y-%m-%d %H:%M:%S")
        # 若现在已过凌晨 4 点，隔夜文件应 ≥ 昨天 20:00
        cutoff = (now - timedelta(days=1)).replace(hour=20, minute=0, second=0, microsecond=0)
        if now.hour >= 4 and mt < cutoff:
            issues.append(f"before_cutoff:overnight_mtime={ov['mtime']}<{cutoff}")

    info["issues"] = issues
    info["ok"] = len(issues) == 0
    info["overnight_score_weight"] = OVERNIGHT_SCORE_WEIGHT
    return info


if __name__ == "__main__":
    data = get_full_overnight_data()
    print("Overnight sentiment saved:", OVERNIGHT_JSON)
    print(json.dumps(data, ensure_ascii=False, indent=2)[:2000])
    print("freshness:", json.dumps(check_overnight_freshness(), ensure_ascii=False, indent=2))
