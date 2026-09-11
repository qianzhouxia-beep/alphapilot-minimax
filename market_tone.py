#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""开盘前外围环境门：A50 + 离岸人民币(CNH) → market_tone。

背景：豆包盘前清单里「A50 看外资情绪、离岸人民币看北向倾向」是可靠性第一梯队，
但这两个因子在系统里之前只在 intel_prebrief.json 落盘、不参与选股。
本模块把它们转成 09:35 scanner 可消费的环境门：

  - fetch: 实时抓 A50（新浪 hf_CHA50CFD）+ CNH（新浪 fx_susdcnh）
  - tone:  A50>=+0.5 偏多 +1 / <=-0.5 偏空 -1；CNH 升值(现价<昨收) +1 / 贬值 -1
          score>=2 -> risk_on, score<=-2 -> risk_off, 其余 neutral
  - gate:  risk_off 时给 scanner 建议提高 min_change_pct（当日涨幅门槛），
          只收紧「当日非上涨」硬门，不改打分、不硬剔具体板块。
  - 落盘: output/market_tone.json（asof + tone + 原始值 + gate 建议）

只产出上下文（不改打分/不硬剔），任何单源失败 -> neutral 不阻断，与情报层同原则。
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
if ROOT.name != "alphapilot" and (ROOT / "output").exists():
    ROOT = ROOT
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

OUT = ROOT / "output" / "market_tone.json"

S = requests.Session()
S.trust_env = False
S.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://finance.sina.com.cn/",
    }
)

# 阈值：A50 涨跌幅（%），CNH 现价 vs 昨收涨跌幅（%，负=人民币升值=偏多）
A50_BULL = 0.5   # A50 >= +0.5% 视为偏多
A50_BEAR = -0.5  # A50 <= -0.5% 视为偏空
CNH_BULL = -0.10  # CNH <= -0.10%（人民币升值）视为偏多
CNH_BEAR = 0.10   # CNH >= +0.10%（人民币贬值）视为偏空

# risk_off 时的资金门收紧参数（env 可调，默认 +1.0% 当日涨幅门槛）
RISK_OFF_MIN_CHANGE = float(os.environ.get("MARKET_TONE_RISK_OFF_MIN_CHANGE", "1.0") or 1.0)
# risk_on 时放宽到 0.0（即维持现状：只要当日非下跌）
RISK_ON_MIN_CHANGE = float(os.environ.get("MARKET_TONE_RISK_ON_MIN_CHANGE", "0.0") or 0.0)
NEUTRAL_MIN_CHANGE = float(os.environ.get("MARKET_TONE_NEUTRAL_MIN_CHANGE", "0.0") or 0.0)

ENABLED = os.environ.get("MARKET_TONE_ENABLE", "1").strip().lower() not in (
    "0", "false", "no", "off",
)


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] market_tone: {msg}", flush=True)


def fetch_a50() -> dict | None:
    """新浪 hf_CHA50CFD：parts[0]=price, parts[2]=昨收。返回 {price, change_pct}。"""
    try:
        r = S.get("https://hq.sinajs.cn/list=hf_CHA50CFD", timeout=10)
        r.raise_for_status()
        for line in r.text.strip().splitlines():
            if "hq_str_hf_CHA50CFD" not in line:
                continue
            body = line.split('"')[1]
            parts = body.split(",")
            if len(parts) < 13:
                return None
            price = float(parts[0])
            prev = float(parts[2])
            pct = round((price - prev) / prev * 100, 2) if prev else 0.0
            return {"price": round(price, 3), "change_pct": pct}
    except Exception as e:
        log(f"⚠️ A50 抓取失败: {e}")
    return None


def fetch_cnh() -> dict | None:
    """新浪 fx_susdcnh：parts[1]=现价, parts[5]=昨收。返回 {price, change_pct}。

    change_pct 为负 = 美元兑人民币下跌 = 人民币升值 = 偏多。
    """
    try:
        r = S.get("https://hq.sinajs.cn/list=fx_susdcnh", timeout=10)
        r.raise_for_status()
        for line in r.text.strip().splitlines():
            if "hq_str_fx_susdcnh" not in line:
                continue
            body = line.split('"')[1]
            parts = body.split(",")
            if len(parts) < 6:
                return None
            price = float(parts[1])
            prev = float(parts[5])
            pct = round((price - prev) / prev * 100, 4) if prev else 0.0
            return {"price": round(price, 4), "change_pct": pct, "prev_close": prev}
    except Exception as e:
        log(f"⚠️ CNH 抓取失败: {e}")
    return None


def compute_tone(a50: dict | None, cnh: dict | None) -> tuple[str, int, list[str]]:
    """返回 (tone, score, reasons)。逐源容错：缺源时另一源仍可给出方向。"""
    score = 0
    reasons: list[str] = []
    if a50 is not None:
        p = float(a50["change_pct"])
        if p >= A50_BULL:
            score += 1
            reasons.append(f"A50 +{p}% 偏多")
        elif p <= A50_BEAR:
            score -= 1
            reasons.append(f"A50 {p}% 偏空")
        else:
            reasons.append(f"A50 {p}% 中性")
    if cnh is not None:
        p = float(cnh["change_pct"])
        if p <= CNH_BULL:
            score += 1
            reasons.append(f"CNH {p}% 人民币升值")
        elif p >= CNH_BEAR:
            score -= 1
            reasons.append(f"CNH +{p}% 人民币贬值")
        else:
            reasons.append(f"CNH {p}% 中性")
    if score >= 2:
        tone = "risk_on"
    elif score <= -2:
        tone = "risk_off"
    else:
        tone = "neutral"
    return tone, score, reasons


def gate_suggestion(tone: str) -> dict:
    """risk_off 时建议收紧资金门（提高当日涨幅门槛）；其余维持现状。"""
    if tone == "risk_off":
        return {
            "min_change_pct": RISK_OFF_MIN_CHANGE,
            "mode": "tighten",
            "note": f"外围偏空(risk_off)：当日涨幅 < {RISK_OFF_MIN_CHANGE}% 不参与 09:35 排序",
        }
    if tone == "risk_on":
        return {
            "min_change_pct": RISK_ON_MIN_CHANGE,
            "mode": "normal",
            "note": "外围偏多(risk_on)：维持当日非下跌即可",
        }
    return {
        "min_change_pct": NEUTRAL_MIN_CHANGE,
        "mode": "normal",
        "note": "外围中性(neutral)：维持当日非下跌即可",
    }


def build() -> dict:
    """执行一次采集+映射+落盘，返回 market_tone dict。"""
    a50 = fetch_a50()
    cnh = fetch_cnh()
    if a50:
        log(f"A50 {a50['price']} ({a50['change_pct']}%)")
    if cnh:
        log(f"CNH {cnh['price']} ({cnh['change_pct']}%)")
    tone, score, reasons = compute_tone(a50, cnh)
    gate = gate_suggestion(tone)
    payload = {
        "asof": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "enabled": ENABLED,
        "tone": tone,
        "score": score,
        "reasons": reasons,
        "sources": {
            "a50": a50,
            "cnh": cnh,
        },
        "gate": gate,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"tone={tone} score={score} → {OUT.name}")
    return payload


def load() -> dict:
    """读落盘结果（供 09:35 scanner）。缺失/异常 → neutral 默认，不阻断。"""
    if not ENABLED:
        return {
            "enabled": False,
            "tone": "neutral",
            "score": 0,
            "reasons": ["MARKET_TONE_ENABLE=off"],
            "gate": {"min_change_pct": 0.0, "mode": "normal", "note": "disabled"},
        }
    try:
        if OUT.exists():
            return json.loads(OUT.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"⚠️ market_tone.json 解析失败，按 neutral 处理: {e}")
    return {
        "enabled": True,
        "tone": "neutral",
        "score": 0,
        "reasons": ["no_snapshot"],
        "gate": {"min_change_pct": 0.0, "mode": "normal", "note": "no snapshot → neutral"},
    }


if __name__ == "__main__":
    p = build()
    print(json.dumps(p, ensure_ascii=False, indent=2))
