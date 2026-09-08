#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""情报层：盘前简报生成 + 微信推送。

读 output/intel_prebrief.json（intel_sweep.py 产出），生成 markdown 简报，
复用 scripts/wecom_push.py 推送到企业微信。工作日 08:50 跑（A50 早盘已开）。

用法:
  python3 scripts/intel_brief.py            # 生成 + 推送
  python3 scripts/intel_brief.py --no-send  # 只生成不推送
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

PREBRIEF = ROOT / "output" / "intel_prebrief.json"
OUT_MD = ROOT / "output" / "intel_prebrief.md"


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def fmt_pct(v, nd=2):
    if v is None:
        return "—"
    try:
        return f"{float(v):+.{nd}f}%"
    except (TypeError, ValueError):
        return str(v)


def build_md(p: dict) -> str:
    """生成盘前简报 markdown（纯文本行，企业微信 markdown 不支持表格）。"""
    ov = p.get("overnight") or {}
    risk = p.get("risk_assessment") or {}
    sectors = p.get("impacted_sectors") or {}
    events = p.get("events") or []
    news = p.get("news_headlines") or []

    level_name = {
        "normal": "正常",
        "elevated": "⚠️ 偏高",
        "high": "⚠️ 高",
        "extreme": "🚨 极高",
    }.get(risk.get("level"), risk.get("level", "—"))
    cap = risk.get("suggest_expo_cap")
    cap_s = f"（建议 expo ≤ {int(cap*100)}%）" if cap else "（建议满仓）"

    lines = [
        f"## 🌅 隔夜情报 {datetime.now().strftime('%m-%d')}",
        "",
        f"**风险等级**: {level_name} {cap_s}",
        "",
        "**隔夜外盘**",
    ]
    rows = [
        ("A50期货", ov.get("a50_pct")),
        ("恒指", ov.get("hsi_pct")),
        ("恒生科技", ov.get("hstech_pct")),
        ("纳指", ov.get("us_nasdaq_pct")),
        ("标普500", ov.get("us_sp500_pct")),
        ("黄金", ov.get("gold_pct")),
        ("白银", ov.get("silver_pct")),
        ("美铜", ov.get("copper_pct")),
        ("原油", ov.get("oil_pct")),
    ]
    pairs = " | ".join(f"{k} {fmt_pct(v)}" for k, v in rows if v is not None)
    lines.append(f"> {pairs}")
    if ov.get("us_10y_yield") is not None:
        lines.append(f"> 美债10Y: {ov['us_10y_yield']}%")
    lines.append("")

    if events:
        lines.append("**事件判定**")
        for e in events[:6]:
            d = "利好" if e["direction"] == "bull" else "利空"
            secs = "、".join(e["sectors"]) if e["sectors"] else "大盘"
            lines.append(f"> {d} {secs}: {e['reason']}")
        lines.append("")

    pref = sectors.get("prefer_hint") or []
    avoid = sectors.get("avoid_hint") or []
    if pref or avoid:
        lines.append("**今日可能受影响板块**")
        if pref:
            lines.append(f"> 利好: {'、'.join(pref)}")
        if avoid:
            lines.append(f"> 利空: {'、'.join(avoid)}")
        lines.append("")

    if news:
        lines.append("**今日头条**")
        for n in news[:5]:
            lines.append(f"> - {n}")
        lines.append("")

    lines.append("---")
    lines.append("*仅作情报参考，不改变生产选股结果（权重默认0）。*")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-send", action="store_true", help="只生成不推送")
    args = ap.parse_args()

    if not PREBRIEF.exists():
        log(f"{PREBRIEF} 不存在，跳过（先跑 intel_sweep.py）")
        return 0
    try:
        p = json.loads(PREBRIEF.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"解析失败: {e}")
        return 1

    md = build_md(p)
    OUT_MD.write_text(md, encoding="utf-8")
    log(f"已写 {OUT_MD}")

    if args.no_send:
        return 0

    try:
        from wecom_push import send_markdown

        ok, err = send_markdown(md)
        log(f"wecom push: ok={ok} {err}")
    except Exception as e:
        log(f"wecom push skip: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
