# -*- coding: utf-8 -*-
"""情报层：盘前扩源采集 → output/intel_prebrief.json

在现有隔夜层（overnight_sentiment.py / us_enhanced_collector.py 只覆盖美股+美债）基础上扩展：
  - A50 期货（新浪 hf_CHA50CFD）
  - 恒指 / 恒生科技（腾讯 qt）
  - 贵金属金/银、铜、原油（新浪 hf_GC/SI/HG/CL）
  - 国内财经快讯（东财 getFastNewsList）
  - 美元指数暂缺（Yahoo/东财/新浪均不可用）→ 用美债10Y 变化代替

产出 output/intel_prebrief.json（含 overnight + risk_assessment + impacted_sectors）。
逐源容错：任何单源失败只记日志，不阻断整体。被 alphapilot_pipeline_v3.py 第 0 步后调用。
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
if ROOT.name != "alphapilot" and (ROOT / "output").exists():
    ROOT = ROOT
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

OUT_PREBRIEF = ROOT / "output" / "intel_prebrief.json"
OUT_RAW = ROOT / "output" / "intel_raw_snapshot.json"

S = requests.Session()
S.trust_env = False
S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36"})


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ── 新浪 hf_ 期货/指数（A50 / 金银铜油）────────────
SINA_HF = {
    "a50": ("hf_CHA50CFD", "富时A50期货"),
    "gold": ("hf_GC", "纽约黄金"),
    "silver": ("hf_SI", "纽约白银"),
    "copper": ("hf_HG", "美铜"),
    "oil": ("hf_CL", "纽约原油"),
}


def fetch_sina_hf() -> dict:
    """新浪 hf_ 格式：price=parts[0], 昨收=parts[2], 时间=parts[6], 日期=parts[11]。
    涨跌幅 = (price - 昨收) / 昨收 * 100。
    """
    codes = [v[0] for v in SINA_HF.values()]
    url = "https://hq.sinajs.cn/list=" + ",".join(codes)
    out: dict[str, dict] = {}
    try:
        r = S.get(url, headers={**S.headers, "Referer": "https://finance.sina.com.cn/"}, timeout=12)
        r.raise_for_status()
    except Exception as e:
        log(f"  ⚠️ 新浪 hf 请求失败: {e}")
        return out
    for line in r.text.strip().splitlines():
        if "hq_str_" not in line:
            continue
        sym = line.split("hq_str_")[1].split("=")[0].strip()
        body = line.split('"')[1]
        parts = body.split(",")
        if len(parts) < 13:
            continue
        key = None
        for k, (code, name) in SINA_HF.items():
            if code == sym:
                key = k
                break
        if not key:
            continue
        try:
            price = float(parts[0])
            prev = float(parts[2])
            pct = round((price - prev) / prev * 100, 2) if prev else 0.0
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        out[key] = {"name": SINA_HF[key][1], "price": round(price, 3), "change_pct": pct}
    return out


# ── 腾讯 qt（恒指 / 恒生科技）────────────
TX_HK = {
    "hkHSI": ("hsi", "恒生指数"),
    "hkHSTECH": ("hstech", "恒生科技"),
}


def fetch_tx_hk() -> dict:
    """腾讯 qt.gtimg.cn 港股指数：parts[3]=price, parts[4]=prev_close, parts[32]=change_pct。"""
    codes = list(TX_HK.keys())
    url = "http://qt.gtimg.cn/q=" + ",".join(codes)
    out: dict[str, dict] = {}
    try:
        r = S.get(url, headers={**S.headers, "Referer": "https://gu.qq.com/"}, timeout=12)
        r.raise_for_status()
    except Exception as e:
        log(f"  ⚠️ 腾讯港股请求失败: {e}")
        return out
    for line in r.text.strip().splitlines():
        m = line.split('"')
        if len(m) < 2:
            continue
        code = m[0].replace("v_", "").replace("=", "").strip()
        key, name = TX_HK.get(code, (None, None))
        if not key:
            continue
        parts = m[1].split("~")
        try:
            price = float(parts[3])
            prev = float(parts[4])
            pct = round((price - prev) / prev * 100, 2) if prev else 0.0
        except (TypeError, ValueError, IndexError, ZeroDivisionError):
            continue
        out[key] = {"name": name, "price": round(price, 3), "change_pct": pct}
    return out


# ── 东财快讯（国内财经头条）────────────
def fetch_em_fast_news(limit: int = 8) -> list[str]:
    """东财 7x24 快讯。返回标题列表（去掉重复）。"""
    url = "https://np-listapi.eastmoney.com/comm/web/getFastNewsList"
    params = {
        "client": "web", "biz": "web_724", "fastColumn": "102",
        "sortEnd": "", "pageSize": str(limit), "req_trace": "1",
    }
    try:
        r = S.get(url, params=params, headers={**S.headers, "Referer": "https://www.eastmoney.com/"}, timeout=10)
        d = r.json()
        items = (d.get("data") or {}).get("fastNewsList") or []
        titles = []
        for it in items:
            t = str(it.get("title") or "").strip()
            if t and t not in titles:
                titles.append(t[:80])
            if len(titles) >= limit:
                break
        return titles
    except Exception as e:
        log(f"  ⚠️ 东财快讯失败: {e}")
        return []


# ── 合并现有隔夜层（美股/美债）────────────
def merge_us_factors() -> tuple[dict, list[str]]:
    """读 us_enhanced_factors.json 提取纳指/标普/美债。返回 (overnight 增量, 美股新闻)。"""
    ov = {}
    news = []
    p = ROOT / "output" / "us_enhanced_factors.json"
    if not p.exists():
        log("  ⚠️ us_enhanced_factors.json 不存在（5点管线第0步未跑？）")
        return ov, news
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"  ⚠️ us_enhanced_factors.json 解析失败: {e}")
        return ov, news

    idx = d.get("indices") or {}
    # us_market.py 产出 usDIA/usIXIC/usSPY
    for k, out_key in (("usIXIC", "us_nasdaq_pct"), ("usSPY", "us_sp500_pct"), ("usDIA", "us_dow_pct")):
        v = (idx.get(k) or {}).get("change_pct")
        if v is not None:
            try:
                ov[out_key] = round(float(v), 2)
            except (TypeError, ValueError):
                pass
    eco = d.get("economic_data") or {}
    if eco.get("us_10y_yield") is not None:
        ov["us_10y_yield"] = round(float(eco["us_10y_yield"]), 3)
    if eco.get("us_2y_yield") is not None:
        ov["us_2y_yield"] = round(float(eco["us_2y_yield"]), 3)
    news = list(d.get("news_headlines") or [])[:5]
    return ov, news


def load_prev_10y() -> float | None:
    """从昨日 intel_prebrief 取美债10Y 作为 move 基准。"""
    p = ROOT / "output" / "intel_prebrief.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return (d.get("overnight") or {}).get("us_10y_yield")
    except Exception:
        return None


def sweep() -> dict:
    """执行一次全量情报采集。"""
    t0 = time.time()
    log("情报层 sweep 开始")
    sources: list[str] = []

    hf = fetch_sina_hf()
    log(f"  新浪 hf: { {k: v['change_pct'] for k, v in hf.items()} }")
    hk = fetch_tx_hk()
    log(f"  腾讯港股: { {k: v['change_pct'] for k, v in hk.items()} }")
    news = fetch_em_fast_news(limit=8)
    log(f"  国内快讯: {len(news)} 条")
    us_ov, us_news = merge_us_factors()
    log(f"  美股/美债: {us_ov}")

    overnight = {}
    for k, v in hf.items():
        overnight[k + "_pct"] = v["change_pct"]
    for k, v in hk.items():
        overnight[k + "_pct"] = v["change_pct"]
    overnight.update(us_ov)
    overnight_prev = {}
    prev10y = load_prev_10y()
    if prev10y is not None:
        overnight_prev["us_10y_yield"] = prev10y

    all_news = news + us_news
    # 去重
    seen = set()
    dedup_news = []
    for n in all_news:
        if n not in seen:
            seen.add(n)
            dedup_news.append(n)

    raw = {
        "asof": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "overnight": overnight,
        "overnight_prev": overnight_prev,
        "sina_hf_raw": hf,
        "tx_hk_raw": hk,
        "news_headlines": dedup_news[:12],
        "sources": sources,
        "us_enhanced_factors_asof": (json.loads((ROOT / "output" / "us_enhanced_factors.json").read_text(encoding="utf-8")).get("fetched_at") if (ROOT / "output" / "us_enhanced_factors.json").exists() else None),
    }
    OUT_RAW.parent.mkdir(parents=True, exist_ok=True)
    OUT_RAW.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    from intel_map import build_prebrief

    prebrief = build_prebrief(raw)
    OUT_PREBRIEF.write_text(json.dumps(prebrief, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"  ✅ intel_prebrief.json 已写 (risk={prebrief['risk_assessment']['level']}, "
        f"prefer={prebrief['impacted_sectors']['prefer_hint']}, "
        f"avoid={prebrief['impacted_sectors']['avoid_hint']})")
    log(f"情报层 sweep 完成, 耗时 {time.time()-t0:.1f}s")
    return prebrief


if __name__ == "__main__":
    p = sweep()
    print(json.dumps(p, ensure_ascii=False, indent=2))
