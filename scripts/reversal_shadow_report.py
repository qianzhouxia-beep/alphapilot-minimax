#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""尾盘超跌×低开影子 — 结算报告 + 企业微信推送。

T+1 收盘后运行（cron 建议: 工作日 16:30，K线 16:18 已同步）：
  1. 读 output/reversal_shadow_history.jsonl（scanner 逐日写入）
  2. 对每个候选算 T+1 收盘收益（T 收盘价 → T+1 收盘价）
  3. 生成报告（output/reversal_shadow_report.md）+ 逐笔明细
  4. 推送企业微信（markdown 摘要）

口径（与回测一致）: T 尾盘买（≈T 收盘）→ T+1 收盘卖。
用 kline_all.parquet 的 c_next 做结算（服务器 16:18 已同步当日）。

产出:
  - output/reversal_shadow_report.md
  - output/reversal_shadow_report.json
  - 企业微信群 markdown 摘要

用法:
  python scripts/reversal_shadow_report.py                # 结算已到期样本
  python scripts/reversal_shadow_report.py --no-send      # 只生成不推送
  python scripts/reversal_shadow_report.py --force        # 重算（同一天可重复推）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(os.environ.get("ALPHAPILOT_ROOT") or "/home/ubuntu/alphapilot")
if not (ROOT / "data").exists():
    # 本地开发或路径缺失时回退到脚本目录的父级
    candidate = Path(__file__).resolve().parents[1]
    if (candidate / "data").exists():
        ROOT = candidate
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

HISTORY = ROOT / "output" / "reversal_shadow_history.jsonl"
KLINE = ROOT / "data" / "kline_cache" / "kline_all.parquet"
OUT_MD = ROOT / "output" / "reversal_shadow_report.md"
OUT_JSON = ROOT / "output" / "reversal_shadow_report.json"
MARKER = ROOT / "output" / "reversal_shadow" / ".sent_report"


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def load_history() -> list[dict]:
    if not HISTORY.exists():
        return []
    out = []
    for line in HISTORY.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-send", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    today = datetime.now().strftime("%Y-%m-%d")
    if MARKER.exists() and not args.force:
        log("今日已推送过（--force 可重发）")
        return 0

    hist = load_history()
    if not hist:
        log("无影子历史记录")
        return 0
    log(f"历史 {len(hist)} 天")

    # 当日 K 线（含最新，用于 T+1 结算）
    k = pd.read_parquet(KLINE)
    k["symbol"] = k["symbol"].astype(str)
    k["date"] = k["date"].astype(str).str[:10]
    k = k.sort_values(["symbol", "date"])
    g = k.groupby("symbol", sort=False)
    k["c_next"] = g["close"].shift(-1)
    k["ret_t1"] = k["c_next"] / k["close"] - 1

    # 结算所有候选（无 c_next 的说明 T+1 未到，跳过）
    rows = []
    settled_days = set()
    for rec in hist:
        d = rec["date"]
        for c in rec.get("candidates", []):
            sym = str(c["symbol"]).zfill(6)
            sub = k[(k["symbol"] == sym) & (k["date"] == d)]
            if sub.empty:
                continue
            ret = sub["ret_t1"].iloc[0]
            if not np.isfinite(ret):
                continue
            settled_days.add(d)
            rows.append({
                "date": d,
                "symbol": sym,
                "open_gap": c.get("open_gap"),
                "down_streak": c.get("down_streak"),
                "ret_t1": float(ret),
            })
    if not rows:
        log("无到期样本（T+1 未到）")
        return 0

    rdf = pd.DataFrame(rows)
    # 按天聚合: 每天取 1 只（open_gap 最深）作为"模拟买入 1 只"
    rdf = rdf.sort_values(["date", "open_gap"])
    daily = rdf.groupby("date").head(1)
    all_cand = rdf

    # 汇总指标（日选 1 只）
    n_days = len(daily)
    wr = (daily["ret_t1"] > 0).mean() * 100
    mean_ret = daily["ret_t1"].mean() * 100
    med = daily["ret_t1"].median() * 100
    # 全候选口径（不限 1 只，评估组合）
    n_all = len(all_cand)
    wr_all = (all_cand["ret_t1"] > 0).mean() * 100
    mean_all = all_cand["ret_t1"].mean() * 100

    # ── P2 候选甜蜜区 vs 非甜蜜区 结算（2026-08-29）──
    p2_rows = []
    for rec in hist:
        d = rec["date"]
        for c in rec.get("p2_candidates", []):
            sym = str(c["symbol"]).zfill(6)
            sub = k[(k["symbol"] == sym) & (k["date"] == d)]
            if sub.empty:
                continue
            ret = sub["ret_t1"].iloc[0]
            if not np.isfinite(ret):
                continue
            p2_rows.append({
                "date": d,
                "symbol": sym,
                "rank": c.get("rank"),
                "open_gap": c.get("open_gap"),
                "sweet": bool(c.get("sweet")),
                "ret_t1": float(ret),
            })
    p2_section = None
    if p2_rows:
        p2 = pd.DataFrame(p2_rows)
        sweet = p2[p2["sweet"]]["ret_t1"]
        nonsweet = p2[~p2["sweet"]]["ret_t1"]
        s_n = len(sweet)
        ns_n = len(nonsweet)
        p2_section = {
            "n": len(p2),
            "n_days": p2["date"].nunique(),
            "sweet_n": s_n, "sweet_wr": (sweet > 0).mean() * 100 if s_n else None,
            "sweet_mean": sweet.mean() * 100 if s_n else None,
            "nonsweet_n": ns_n, "nonsweet_wr": (nonsweet > 0).mean() * 100 if ns_n else None,
            "nonsweet_mean": nonsweet.mean() * 100 if ns_n else None,
        }
        log(f"P2 甜蜜区: n={s_n} wr={(sweet>0).mean()*100:.1f}% mean={sweet.mean()*100:+.2f}% | "
            f"非甜蜜区: n={ns_n} wr={(nonsweet>0).mean()*100:.1f}% mean={nonsweet.mean()*100:+.2f}%")

    lines = []
    lines.append("## 📊 超跌×低开 尾盘影子结算\n")
    lines.append(f"> 报告时间 {today} · 样本 {n_days} 个交易日 / {n_all} 笔候选")
    lines.append("")
    lines.append(f"**日选1只口径**: 胜率 **{wr:.1f}%** | 平均 **{mean_ret:+.2f}%** | 中位 {med:+.2f}%")
    lines.append(f"**全部候选口径**: 胜率 **{wr_all:.1f}%** | 平均 **{mean_all:+.2f}%**")
    lines.append("")
    lines.append("| 日期 | 代码 | 低开% | 连跌 | T+1收益 |")
    lines.append("|---|---|---|---|---|")
    for _, r in daily.iterrows():
        gap = f"{r['open_gap']*100:+.1f}" if r["open_gap"] is not None else "?"
        lines.append(f"| {r['date']} | {r['symbol']} | {gap}% | {int(r['down_streak'])} | {r['ret_t1']*100:+.2f}% |")
    lines.append("")
    lines.append(f"📎 参考: 回测基准 62.4% / +0.71%（2025-01~2026-08, n=16,357）。样本 <30 天结论仅供参考。")
    lines.append("")
    if p2_section:
        s = p2_section
        lines.append("## 🍬 P2 候选甜蜜区 vs 非甜蜜区\n")
        lines.append(f"> P2 Top10 候选按开盘缺口分甜蜜区(gap∈[-1.5%,0])，T+1 收盘结算。样本 n={s['n']} / {s['n_days']} 天")
        lines.append("")
        lines.append("| 组 | n | 胜率 | 平均 |")
        lines.append("|---|---|---|---|")
        lines.append(f"| 🍬 甜蜜区 | {s['sweet_n']} | {s['sweet_wr']:.1f}% | {s['sweet_mean']:+.2f}% |" if s["sweet_n"] else "| 🍬 甜蜜区 | 0 | - | - |")
        lines.append(f"| 非甜蜜区 | {s['nonsweet_n']} | {s['nonsweet_wr']:.1f}% | {s['nonsweet_mean']:+.2f}% |" if s["nonsweet_n"] else "| 非甜蜜区 | 0 | - | - |")
        lines.append("")
        lines.append("> 参考: 回测 4~7月合成样本 甜蜜区 71.6%/+3.01% vs 非甜蜜区 56.3%/+0.11% (p=0.0034)")
        lines.append("")
    lines.append("> ⚠️ 影子阶段仅记录，不对单。企业微信提醒不构成投资建议。")
    md = "\n".join(lines)

    # 写报告
    report = {
        "asof": today,
        "n_days": n_days,
        "n_candidates": n_all,
        "daily_win_rate": wr,
        "daily_mean_ret": mean_ret,
        "all_win_rate": wr_all,
        "all_mean_ret": mean_all,
        "settled_days": sorted(settled_days),
        "detail": rdf.to_dict(orient="records"),
    }
    if p2_section:
        report["p2_sweet"] = p2_section
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_MD.write_text(md, encoding="utf-8")
    log(f"报告已写入 {OUT_MD}")

    # 推送
    if args.no_send:
        log("--no-send，跳过推送")
        return 0
    try:
        from wecom_push import send_markdown
        ok, err = send_markdown(md)
        log(f"企业微信推送 -> ok={ok} err={err}")
        if ok:
            MARKER.parent.mkdir(parents=True, exist_ok=True)
            MARKER.write_text(datetime.now().isoformat(), encoding="utf-8")
        return 0 if ok else 1
    except Exception as e:
        log(f"推送异常: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
