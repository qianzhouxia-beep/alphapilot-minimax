#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Top2 历史选股 T+1~T+5 每日自动累积统计。

数据源：output/daily_picks_archive/YYYY-MM-DD/top2.json（每日 09:40 由 archive_daily_picks.py 归档）
回填：用 data/kline_cache/kline_all.parquet（16:15 已更新至当日）计算每只 Top2 的 T+1..T+5 收盘累计涨幅。
输出：
  output/top2_t1t5.json       — 全量累积明细（幂等，可反复运行）
  output/top2_t1t5_report.md  — 人读报告
建议 cron：工作日 16:25（K 线 fix_kline_server.py 于 16:15 完成后）

2026-08-15 DHS 修复：
  1. close_on() 目标日无数据时返回 None（原回退到前一日收盘，误记为 0 涨幅）
  2. 仅处理真实交易日归档（剔除周末/节假日手动归档，如 2026-07-26 周日）
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(os.environ.get("ALPHAPILOT_ROOT") or "/home/ubuntu/alphapilot")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

ARCHIVE_ROOT = ROOT / "output" / "daily_picks_archive"
KLINE = ROOT / "data" / "kline_cache" / "kline_all.parquet"
OUT_JSON = ROOT / "output" / "top2_t1t5.json"
OUT_MD = ROOT / "output" / "top2_t1t5_report.md"
HOLD_DAYS = 5


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def load_picks_days() -> list[tuple[str, list[dict]]]:
    """扫描归档目录, 返回 [(day, top2_picks)] 按日期升序。"""
    days: list[tuple[str, list[dict]]] = []
    if not ARCHIVE_ROOT.exists():
        return days
    for d in sorted(p.name for p in ARCHIVE_ROOT.iterdir() if p.is_dir()):
        tp = ARCHIVE_ROOT / d / "top2.json"
        if not tp.exists():
            continue
        try:
            data = json.loads(tp.read_text(encoding="utf-8"))
        except Exception as e:
            log(f"  skip {d}/top2.json: {e}")
            continue
        picks = data.get("picks") or [] if isinstance(data, dict) else []
        if picks:
            days.append((d, picks))
    return days


def load_kline() -> pd.DataFrame:
    df = pd.read_parquet(KLINE, columns=["symbol", "date", "close"])
    df["date"] = pd.to_datetime(df["date"])
    return df


def main() -> int:
    log("Top2 T+1~T+5 累积统计开始")

    df = load_kline()
    trading_days = sorted(df["date"].unique())
    log(f"K线: {len(df)} 行, 交易日 {len(trading_days)} 个, {trading_days[0].date()} ~ {trading_days[-1].date()}")

    # 每只股票 {date: close}
    stock_series: dict[str, pd.Series] = {}

    def close_on(sym: str, d) -> float | None:
        s = stock_series.get(sym)
        if s is None or len(s) == 0:
            return None
        # side="right": 返回第一个 > d 的位置，则 idx-1 是 <= d 的最近交易日；
        # 若该日正是目标日则命中，否则（停牌/未上市）视为缺失，不回退到前一日。
        idx = np.searchsorted(s.index.values, np.datetime64(d), side="right")
        if idx == 0:
            return None
        exact = s.index.values[idx - 1]
        if exact != np.datetime64(d):
            return None
        return float(s.iloc[idx - 1])

    def next_n_days(after_d, n):
        arr = np.array(trading_days)
        pos = np.searchsorted(arr, np.datetime64(after_d), side="right")
        return trading_days[pos:pos + n]

    # 仅保留真实交易日（剔除周末/节假日手动归档）
    day_set = set(str(d.date()) for d in trading_days)
    all_days = load_picks_days()
    before = len(all_days)
    days = [(d, picks) for d, picks in all_days if d in day_set]
    dropped = before - len(days)
    if dropped:
        dropped_days = [d for d, _ in all_days if d not in day_set]
        log(f"剔除非交易日归档 {dropped} 天: {dropped_days}")
    log(f"归档选股日: {len(days)} 天")

    # 读取已有累积结果
    existing = {}
    if OUT_JSON.exists():
        try:
            existing = {r["asof"]: r for r in json.loads(OUT_JSON.read_text(encoding="utf-8")).get("rows", [])}
        except Exception:
            existing = {}

    rows = []
    for day, picks in days:
        # 历史快照可能包含周日手动归档等; 统一以 asof 日期为准
        rec = existing.get(day, {
            "asof": day, "picks": [], "t1t5_dates": {},
            "first_backfill_at": None, "last_backfill_at": None,
        })
        rec["asof"] = day
        t0 = pd.Timestamp(day)
        future = next_n_days(t0, HOLD_DAYS)

        # 收集该日的 picks (symbol/name/buy_price)
        day_picks = []
        for i, p in enumerate(picks[:2]):
            sym = str(p.get("symbol") or "")[-6:]
            if not sym:
                continue
            if sym not in stock_series:
                sub = df[df["symbol"] == sym][["date", "close"]].set_index("date")["close"]
                stock_series[sym] = sub
            base = close_on(sym, day)
            day_picks.append({
                "symbol": sym,
                "name": p.get("name") or "",
                "rank": i + 1,
                "buy_price": p.get("buy_price"),
                "t0_close": round(base, 2) if base else None,
            })
        rec["picks"] = day_picks

        # 回填每只股票 T+1..T+5
        for dp in rec["picks"]:
            sym = dp["symbol"]
            if sym not in stock_series:
                sub = df[df["symbol"] == sym][["date", "close"]].set_index("date")["close"]
                stock_series[sym] = sub
            base = close_on(sym, day)
            dp["t0_close"] = round(base, 2) if base else None
            rets = {}
            dates = {}
            for i in range(1, HOLD_DAYS + 1):
                if i > len(future):
                    break
                d = future[i - 1]
                dates[i] = str(d.date())
                c = close_on(sym, d)
                if c is None or base is None or base <= 0:
                    rets[i] = None
                else:
                    rets[i] = round((c / base - 1) * 100, 2)
            dp["rets"] = rets
        # 用最新 future 更新日期映射
        rec["t1t5_dates"] = rec.get("t1t5_dates") or {}
        for i in range(1, HOLD_DAYS + 1):
            if i <= len(future):
                rec["t1t5_dates"][str(i)] = str(future[i - 1].date())
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if rec.get("first_backfill_at") is None:
            rec["first_backfill_at"] = now
        rec["last_backfill_at"] = now
        rows.append(rec)

    # ── 汇总统计 ──
    def all_rets(day_key: str, i: int):
        vals = []
        for r in rows:
            for dp in r["picks"]:
                v = dp.get("rets", {}).get(i)
                if v is not None:
                    vals.append((r["asof"], dp["symbol"], dp["name"], v))
        return vals

    summary = {}
    for i in range(1, HOLD_DAYS + 1):
        vals = all_rets(None, i)
        if not vals:
            continue
        nums = [x[3] for x in vals]
        summary[str(i)] = {
            "n": len(nums),
            "avg_pct": round(float(np.mean(nums)), 2),
            "median_pct": round(float(np.median(nums)), 2),
            "pos_count": int(sum(1 for v in nums if v > 0)),
            "best": round(float(max(nums)), 2),
            "worst": round(float(min(nums)), 2),
        }

    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "method": "Top2选股 T0收盘买入, T+n收盘累计涨幅%",
        "hold_days": HOLD_DAYS,
        "rows": rows,
        "summary": summary,
        "asof_last_trading_day": str(trading_days[-1].date()) if trading_days else None,
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    log(f"已写 {OUT_JSON}")

    # ── 报告 ──
    md = [f"# Top2 选股 T+1~T+5 累积统计", "",
          f"生成时间: {payload['generated_at']}  ·  数据到: {payload['asof_last_trading_day']}  ·  样本日: {len(rows)} 天",
          "", "## 汇总", "", "| 持有期 | 样本数 | 平均% | 中位% | 正收益 | 最好% | 最差% |", "|---|---|---|---|---|---|---|"]
    for i in range(1, HOLD_DAYS + 1):
        s = summary.get(str(i))
        if not s:
            continue
        md.append(f"| T+{i} | {s['n']} | {s['avg_pct']:+.2f} | {s['median_pct']:+.2f} | {s['pos_count']}/{s['n']} | {s['best']:+.2f} | {s['worst']:+.2f} |")
    md += ["", "## 明细", "", "| 选股日 | 代码 | 名称 | T0收盘 | T+1% | T+2% | T+3% | T+4% | T+5% |", "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        for dp in r["picks"]:
            def f(v):
                return "—" if v is None else f"{v:+.2f}"
            md.append(f"| {r['asof']} | {dp['symbol']} | {dp['name']} | {dp.get('t0_close') or '—'} | "
                      f"{f(dp.get('rets',{}).get(1))} | {f(dp.get('rets',{}).get(2))} | {f(dp.get('rets',{}).get(3))} | "
                      f"{f(dp.get('rets',{}).get(4))} | {f(dp.get('rets',{}).get(5))} |")
    md += ["", "---", "*说明: 涨幅相对选股日 T0 收盘买入; 未到持有期显示 — 表示等待后续交易日回填。*"]
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    log(f"已写 {OUT_MD}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
