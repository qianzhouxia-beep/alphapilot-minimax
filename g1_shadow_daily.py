#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G1（走低否决）每日只读影子 — 2026-09-10 Cursor

目的: 2 周只读影子。每天(交易日) 16:45 评估"当日 09:35 选出的 top10_ungated
      当日(买入日) 09:36 买 + G1 v2+0.6% 否决窗(09:40..10:00)"本应如何,
      只记日志不碰 sim/生产。S0(全买) vs G1(否决后) 的 T0 对比。

为什么 EOD 而非盘中 10:00: 否决窗只需买入日 <=10:00 的 5m bar,
  ⚠️ build_kline5m.py cron = 16:20 (* * 1-5) -> 当日 5m 在 16:20 之后才齐全,
  故本脚本必须排在 16:45 之后(原版写 15:30 是错的, 那时当日 bar 还不存在);
  切片到 10:00 结果与盘中实时判定完全一致, 规避服务器盘中 5m 实时源依赖。
  若未来要"盘中实时否决", 另接实时源(腾讯 mkline 需先验上海可达性)。

口径(对齐生产 D 09:36 入场; 2026-09-11 Cursor 修正):
  - 选股日 = 买入日 = 本交易日 T (生产 09:35 选、09:36 买; 原版误用"上一 archive"= 结构性晚一天)
  - prev_close = T-1 收盘 (5m 缓存中 < T 的最后一个 bar 的 close)
  - entry = T 首根5m(09:35 bar) 的 close (≈09:35 价; bar 按"结束时刻"标注,
            bar(09:35) 覆盖 09:30-09:35, 其 open=当日开盘; 生产 09:36 买 ≈ 09:35 价)
  - gap=(entry-prev_close)/prev_close, |.|>0.3% => 高/低开
  - 走向 T0 = T 收盘 vs entry
  - G1 v2+0.6: 09:40..10:00(入场后) 末根 close < entry*(1-0.006) => 否决

⚠️ 2026-09-11 沿用修正: 原版 ①候选=上一日(晚一天) ②买入价=09:30 open(高估) 两点都会
   系统性恶化影子结论, 已一并改为生产口径 (见 knowledge/inbox/2026-09-11-gap-bug-recheck.md).

只读生产文件; 唯一写入: /home/ubuntu/alphapilot/output/g1_shadow/{T}.json
用法:
  python3 g1_shadow_daily.py [YYYY-MM-DD]   # 默认自动取"最近可评估买入日"
"""
from __future__ import annotations

import glob
import json
import os
import sys
from datetime import datetime, timedelta

import pandas as pd

ROOT = "/home/ubuntu/alphapilot"
ARCH = os.path.join(ROOT, "output/daily_picks_archive")
K5 = os.path.join(ROOT, "data/kline5m")
OUTD = os.path.join(ROOT, "output/g1_shadow")
GAP_TOL = 0.003
THR = 0.006  # v2+0.6%


def folders() -> list[str]:
    out = []
    for d in sorted(os.listdir(ARCH)):
        if os.path.isdir(os.path.join(ARCH, d)) and \
                os.path.exists(os.path.join(ARCH, d, "top10_ungated.json")):
            out.append(d)
    return out


def day_close(code: str, d: str) -> float | None:
    p = os.path.join(K5, code + ".parquet")
    if not os.path.exists(p) or os.path.getsize(p) == 0:
        return None
    try:
        df = pd.read_parquet(p, columns=["datetime", "close"])
    except Exception:
        return None
    m = df[df["datetime"].astype(str).str[:10] == d]
    return float(m["close"].iloc[-1]) if len(m) else None


def prev_day_close(code: str, d: str) -> float | None:
    """T-1 收盘：5m 缓存中日期 < d 的最后一个 bar 的 close。"""
    p = os.path.join(K5, code + ".parquet")
    if not os.path.exists(p) or os.path.getsize(p) == 0:
        return None
    try:
        df = pd.read_parquet(p, columns=["datetime", "close"])
    except Exception:
        return None
    df = df[df["datetime"].astype(str).str[:10] < d].sort_values("datetime")
    return float(df["close"].iloc[-1]) if len(df) else None


def eval_buy_day(buy: str) -> list[dict]:
    """生产口径：选股日 = 买入日 = buy（同日）；候选 = 同日 archive/top10_ungated.json。"""
    fds = folders()
    if buy in fds:
        sel, mode = buy, "same_day_prod"
    else:
        prev = [d for d in fds if d < buy]
        if not prev:
            return []
        sel, mode = prev[-1], "late_prevday_fallback"
    try:
        j = json.load(open(os.path.join(ARCH, sel, "top10_ungated.json"), encoding="utf-8"))
    except Exception as e:
        return [{"sel": sel, "buy": buy, "mode": mode, "error": f"load: {e}"}]
    rows = []
    for pk in j.get("picks", []):
        code = str(pk.get("symbol"))
        p = os.path.join(K5, code + ".parquet")
        rows.append({"sel": sel, "buy": buy, "code": code,
                     "name": pk.get("name", ""), "rank": pk.get("rank")})
        if not os.path.exists(p) or os.path.getsize(p) == 0:
            rows[-1]["error"] = "no_k5"
            continue
        try:
            df = pd.read_parquet(p, columns=["datetime", "open", "close", "low"])
        except Exception as e:
            rows[-1]["error"] = f"read: {e}"
            continue
        m = df[df["datetime"].astype(str).str[:10] == buy].sort_values("datetime")
        if not len(m):
            rows[-1]["error"] = "no_bar_buydate"
            continue
        entry_bar = m[m["datetime"].astype(str).str[11:16] == "09:35"]
        pc = prev_day_close(code, buy)
        row = rows[-1]
        if not len(entry_bar):
            row["error"] = "no_0935_bar"
            continue
        ob = float(entry_bar["close"].iloc[0])   # 生产 09:36 入场价 ≈ 09:35 bar 收盘
        cb = float(m["close"].iloc[-1])
        row["mode"] = mode
        row["gap"] = (ob / pc - 1.0) if pc else None
        row["bucket"] = ("高开" if row["gap"] and row["gap"] > GAP_TOL else
                         "低开" if row["gap"] and row["gap"] < -GAP_TOL else "平开") + \
                        ("走高" if cb > ob else "走低" if cb < ob else "平走")
        row["ob"] = ob
        row["cb"] = cb
        row["r0"] = cb / ob - 1.0
        # 否决窗 = 入场后(09:40..10:00)
        w = m[(m["datetime"].astype(str).str[11:16] >= "09:40") &
              (m["datetime"].astype(str).str[11:16] <= "10:00")]
        last_w = float(w["close"].iloc[-1]) if len(w) else None
        row["veto_v2_006"] = bool(last_w is not None and last_w < ob * (1 - THR))
        row["win_late"] = w["datetime"].astype(str).str[11:16].tolist()
    return rows


def main():
    fds = folders()
    if len(sys.argv) > 1:
        buy = sys.argv[1]
    else:
        # 自动: 最近有完整(前一 archive 存在)的交易日
        today = datetime.now().strftime("%Y-%m-%d")
        cand = [d for d in fds if d <= today]
        buy = cand[-1] if cand else today
    rows = eval_buy_day(buy)
    print(f"[g1s] buy={buy} rows={len(rows)} sel={rows[0]['sel'] if rows else '-'}", flush=True)
    s0 = [r for r in rows if "r0" in r]
    veto = [r for r in s0 if r["veto_v2_006"]]
    exe = [r for r in s0 if not r["veto_v2_006"]]
    if s0:
        import statistics as st
        print(f"[g1s] S0全买 n={len(s0)} T0={st.mean([r['r0'] for r in s0])*100:+.2f}% | "
              f"G1执行 n={len(exe)} T0={(st.mean([r['r0'] for r in exe])*100 if exe else float('nan')):+.2f}% | "
              f"否决 n={len(veto)} (走高误杀 {sum(1 for r in veto if r['bucket'].endswith('走高'))})", flush=True)
    for r in rows:
        print(json.dumps(r, ensure_ascii=False), flush=True)
    if not os.path.isdir(OUTD):
        os.makedirs(OUTD, exist_ok=True)
    out_path = os.environ.get("G1S_OUT") or os.path.join(OUTD, f"{buy}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    print(f"[g1s] wrote {out_path}", flush=True)


if __name__ == "__main__":
    main()
