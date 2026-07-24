#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盘前/午间舆情增量更新 — 扩展现有 LLM 审核的新闻源与调度。

建议 cron:
  09:00  python3 -u scripts/sentiment_update.py --session preopen
  13:05  python3 -u scripts/sentiment_update.py --session midday

落盘: output/news_sentiment.json
晨间选股 / 管线 LLM 层可读取加权。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"
REC = OUT / "daily_recommend.json"
SENT = OUT / "news_sentiment.json"

LLM_KEY = os.getenv("DEEPSEEK_API_KEY") or ""
LLM_URL = "https://api.deepseek.com/v1/chat/completions"


def _bare(sym: str) -> str:
    s = str(sym or "")
    for p in ("sh", "sz", "bj", "SH", "SZ", "BJ"):
        s = s.replace(p, "")
    return s[-6:]


def fetch_news_em(symbol: str) -> list[str]:
    news = []
    try:
        import akshare as ak

        df = ak.stock_news_em(symbol=_bare(symbol))
        if df is not None and not df.empty:
            for _, row in df.head(4).iterrows():
                title = str(row.get("新闻标题") or row.get("title") or "")
                if title and len(title) > 5:
                    news.append(title[:100])
    except Exception:
        pass
    return news


def fetch_news_sina() -> list[str]:
    news = []
    try:
        r = requests.get(
            "https://feed.mix.sina.com.cn/api/roll/get",
            params={"pageid": "153", "lid": "2510", "num": 8},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=8,
        )
        if r.status_code == 200:
            for item in (r.json().get("result") or {}).get("data") or []:
                t = item.get("title") or ""
                if t and len(t) > 5:
                    news.append(t[:100])
    except Exception:
        pass
    return news


def llm_sentiment(name: str, symbol: str, news: list[str]) -> dict | None:
    if not news or not LLM_KEY:
        return None
    prompt = (
        "分析以下股票最新新闻标题，判断短期情绪（利好/中性/利空），"
        "返回情绪分（-0.02到+0.03）和一句话理由。"
        f"\n股票: {name}({symbol})\n新闻:\n"
        + "\n".join(f"- {n}" for n in news[:6])
        + '\n\n格式: JSON {"sentiment": float, "reason": str}'
    )
    try:
        r = requests.post(
            LLM_URL,
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 200,
            },
            headers={"Authorization": f"Bearer {LLM_KEY}"},
            timeout=12,
        )
        if r.status_code != 200:
            return None
        content = r.json()["choices"][0]["message"]["content"]
        m = re.search(r'"sentiment"\s*:\s*(-?[\d.]+)', content)
        if not m:
            return None
        sent = max(-0.02, min(0.03, float(m.group(1))))
        return {"sentiment": sent, "reason": content[:120], "news": news[:4]}
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", default="preopen", choices=["preopen", "midday", "manual"])
    ap.add_argument("--top", type=int, default=30)
    args = ap.parse_args()

    if not REC.exists():
        print(f"missing {REC}")
        return 1
    recs = json.loads(REC.read_text(encoding="utf-8"))
    items = list(recs.get("recommendations") or [])[: args.top]

    sina_macro = fetch_news_sina()
    results = {}
    for it in items:
        sym = it.get("symbol") or ""
        name = it.get("name") or ""
        if not sym:
            continue
        news = fetch_news_em(sym)
        # 宏观快讯只附加到前 10 只，避免噪声
        if len(results) < 10 and sina_macro:
            news = news + sina_macro[:2]
        if not news:
            results[_bare(sym)] = {
                "symbol": sym,
                "name": name,
                "sentiment": 0.0,
                "reason": "无新闻-中性",
            }
            continue
        lr = llm_sentiment(name, sym, news)
        if lr:
            results[_bare(sym)] = {"symbol": sym, "name": name, **lr}
        else:
            results[_bare(sym)] = {
                "symbol": sym,
                "name": name,
                "sentiment": 0.0,
                "reason": "llm_fail",
                "news": news[:3],
            }
        time.sleep(0.15)

    payload = {
        "asof": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "session": args.session,
        "n": len(results),
        "items": results,
        "note": "盘前/午间舆情增量；asof相对当日，不写死日历",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    SENT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ sentiment {args.session}: {len(results)} → {SENT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
