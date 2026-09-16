#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拉取近 N 日龙虎榜，写入 data/lhb_history.json

格式: {code: {"dates": {"YYYY-MM-DD": buy_inst_count}, "has_lhb_days": n}}
供 train_v25 / vm25 在对应日期打 has_lhb / buy_inst_count。

2026-09-15 修复：
  - 根因：04:45 cron 过早（当日 lhb 未出）+ 仅周五 22:30 晚拉 → 周一~四收盘后缺口
  - 增量跳过改为 meta.fetched_ok 日期集（不再用「全市场股票都有该日」的错误 all()）
  - 单日失败自动重试（默认 3 次、间隔 30s；--retry-sleep 可改）
  - 连续失败写入 data/lhb_pull_health.json 供闸门/告警

2026-09-17 修复（v1.2，lhb_stale 复发）：
  - 根因：**空响应被当成"确认无数据"永久记入 fetched_ok**。22:35 拉取时交易所尚未发布
    （或 akshare 瞬时 NoneType）→ 该交易日被标记为已完成 → 之后所有 run（含 00:30 预检
    repair）全部跳过，缺口逐日累积到 lag≥2 触发 lhb_stale；且 00:30 还会把"今天"也预标，
    导致今晚 22:35 又跳过 09-17，隔日再报——即复发机制。
  - 修法：以 **K 线缓存（真实交易日历）** 判定空响应是否可确认：
      · 在 K 线日历内（真交易日）却空 → **不记 fetched_ok**，下次重试（最多 MAX_EMPTY_ATTEMPTS，
        且须已过 2 天，避免长期真无数据日无限重试）；
      · 不在 K 线日历内且早于 K 线最新日（周末/节假日）→ 确认无数据，记 fetched_ok；
      · 无 K 线日历时退化为「周末 或 早于 7 天」才算确认。
  - 自愈：每次运行把「近期在 K 线日历内、但 LHB 缺失、且已在 fetched_ok」的日期强制剔除重拉，
    修复历史污染并防止再次累积。
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(os.environ.get("ALPHAPILOT_ROOT", "/home/ubuntu/alphapilot"))
os.chdir(ROOT)

PATH_LHB = ROOT / "data" / "lhb_history.json"
PATH_META = ROOT / "data" / "lhb_pull_meta.json"
PATH_HEALTH = ROOT / "data" / "lhb_pull_health.json"
PATH_KLINE = ROOT / "data" / "kline_cache" / "kline_all.parquet"

MAX_EMPTY_ATTEMPTS = 3  # 交易日连续空响应达此数且已过 2 天 → 放弃（避免无限重试）


def bare(sym: str) -> str:
    s = str(sym).strip()
    if "." in s:
        s = s.split(".")[0]
    return s.zfill(6)[-6:]


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _is_empty_response_err(err: str) -> bool:
    """akshare often raises NoneType on weekend/holiday/unpublished day."""
    e = (err or "").lower()
    return (
        "nonetype" in e
        or "not subscriptable" in e
        or "object is not subscriptable" in e
    )


def load_kline_calendar():
    """Return (dates_set, max_date) of CN trading days from the kline cache.

    This is the authoritative trading calendar on the server: a date absent here
    (and older than its max) is a non-trading day (weekend/holiday).
    """
    try:
        import pandas as pd

        df = pd.read_parquet(PATH_KLINE, columns=["date"])
        ds = {str(x)[:10] for x in df["date"].tolist()}
        ds = {x for x in ds if len(x) == 10}
        return ds, (max(ds) if ds else None)
    except Exception as e:  # noqa: BLE001
        print(f"  WARN kline calendar unavailable ({e}); using weekday heuristic", flush=True)
        return set(), None


def is_confirmed_non_trading(d_dash, kline_dates, kline_max, today_dash):
    """True only when an empty LHB response can be treated as final.

    A date that IS a kline trading day must never be confirmed on an empty
    response — that is exactly the 09-15/09-16/09-17 poisoning (not-yet-published
    marked as done, then skipped forever). Dates newer than the kline max are
    also never confirmed (the calendar hasn't caught up yet).
    """
    if kline_dates and kline_max:
        return (d_dash not in kline_dates) and (d_dash < kline_max)
    try:
        dd = datetime.strptime(d_dash, "%Y-%m-%d").date()
        td = datetime.strptime(today_dash, "%Y-%m-%d").date()
    except Exception:  # noqa: BLE001
        return False
    return dd.weekday() >= 5 or (td - dd).days > 7


def fetch_day(ak, d: str, retries: int, sleep_s: float):
    """Return (df_or_None, err_str, empty_ok).

    empty_ok=True means treat as successful no-data day (weekend / not published).
    """
    last_err = ""
    for attempt in range(1, retries + 1):
        try:
            df = ak.stock_lhb_detail_em(start_date=d, end_date=d)
            return df, "", False
        except Exception as e:
            last_err = str(e)
            if _is_empty_response_err(last_err):
                # no retry storm on structural empty
                return None, last_err, True
            print(f"  retry {attempt}/{retries} {d}: {e}", flush=True)
            if attempt < retries:
                time.sleep(sleep_s)
    return None, last_err, False


def main(days: int = 250, retries: int = 3, retry_sleep: float = 30.0) -> int:
    import akshare as ak

    out = _load_json(PATH_LHB, {})
    if not isinstance(out, dict):
        out = {}
    meta = _load_json(PATH_META, {"fetched_ok": []})
    fetched_ok = set(meta.get("fetched_ok") or [])
    empty_attempts = {k: int(v) for k, v in (meta.get("empty_attempts") or {}).items()}

    d0 = datetime.now()
    today_dash = d0.strftime("%Y-%m-%d")
    kline_dates, kline_max = load_kline_calendar()

    # all dates currently present in LHB data
    lhb_dates = set()
    for slot in out.values():
        if isinstance(slot, dict):
            lhb_dates.update((slot.get("dates") or {}).keys())

    window = [
        (d0 - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)
    ]

    # ── self-heal: recent dates that look like a poisoned "empty" are re-fetched.
    # Remove from fetched_ok any recent date that (a) has no LHB rows and
    # (b) cannot be confirmed as non-trading. Repairs historical poisoning AND
    # stops the accumulation that produced the lhb_stale recurrence.
    healed = []
    for d_dash in window:
        if d_dash not in fetched_ok or d_dash in lhb_dates:
            continue
        if is_confirmed_non_trading(d_dash, kline_dates, kline_max, today_dash):
            continue
        fetched_ok.discard(d_dash)
        empty_attempts.pop(d_dash, None)
        healed.append(d_dash)
    if healed:
        print(f"  self-heal: re-fetching {len(healed)} poisoned empty date(s): "
              f"{healed[:10]}", flush=True)

    seen_days = 0
    fail_days = []
    ok_new = []
    retry_days = []

    def _note_empty(d_dash, why):
        """Record an empty response; only confirm=true goes into fetched_ok."""
        if is_confirmed_non_trading(d_dash, kline_dates, kline_max, today_dash):
            fetched_ok.add(d_dash)
            empty_attempts.pop(d_dash, None)
            ok_new.append(d_dash)
            print(f"  empty {d_dash} ({why}) [non-trading, confirmed]", flush=True)
            return
        n = int(empty_attempts.get(d_dash, 0)) + 1
        empty_attempts[d_dash] = n
        old_enough = True
        try:
            dd = datetime.strptime(d_dash, "%Y-%m-%d").date()
            td = datetime.strptime(today_dash, "%Y-%m-%d").date()
            old_enough = (td - dd).days >= 2
        except Exception:  # noqa: BLE001
            pass
        if n >= MAX_EMPTY_ATTEMPTS and old_enough:
            fetched_ok.add(d_dash)
            print(f"  empty {d_dash} ({why}) [gave up after {n} tries]", flush=True)
        else:
            retry_days.append(d_dash)
            print(f"  empty {d_dash} ({why}) [trading day, attempt {n} -> will retry]",
                  flush=True)

    for i in range(days):
        d = (d0 - timedelta(days=i)).strftime("%Y%m%d")
        d_dash = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        if d_dash in fetched_ok:
            continue

        df, err, empty_ok = fetch_day(ak, d, retries=retries, sleep_s=retry_sleep)
        if empty_ok:
            _note_empty(d_dash, err or "no rows")
            continue
        if err:
            print(f"  FAIL {d}: {err}", flush=True)
            fail_days.append({"date": d_dash, "error": err})
            continue

        # Weekend / holiday: empty is OK — mark fetched so we don't hammer.
        if df is None or getattr(df, "empty", True):
            _note_empty(d_dash, "no rows")
            continue

        code_col = next((c for c in df.columns if "代码" in str(c)), None)
        if not code_col:
            print(f"  FAIL {d}: no code column cols={list(df.columns)[:8]}", flush=True)
            fail_days.append({"date": d_dash, "error": "no_code_column"})
            continue

        seen_days += 1
        if seen_days % 20 == 0:
            print(f"  ...{d} 已处理 {seen_days} 个有数据交易日", flush=True)

        n_rows = 0
        for _, row in df.iterrows():
            code = bare(row[code_col])
            if len(code) != 6:
                continue
            inst = 0
            for k in ("买方机构数", "买入营业部数量", "机构买入次数"):
                if k in row.index:
                    try:
                        inst = int(float(row.get(k) or 0))
                        break
                    except Exception:
                        pass
            slot = out.setdefault(code, {"dates": {}, "has_lhb_days": 0})
            prev = int(slot["dates"].get(d_dash, 0) or 0)
            slot["dates"][d_dash] = max(prev, inst, 1)
            n_rows += 1

        fetched_ok.add(d_dash)
        empty_attempts.pop(d_dash, None)
        ok_new.append(d_dash)
        print(f"  ok {d_dash} rows={n_rows}", flush=True)

    for code, slot in out.items():
        slot["has_lhb_days"] = len(slot.get("dates") or {})

    _save_json(PATH_LHB, out)

    # keep meta bounded
    fetched_list = sorted(fetched_ok)[-400:]
    meta = {
        "fetched_ok": fetched_list,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_run_ok_new": ok_new[:20],
        "last_run_fail": fail_days[:20],
        "last_run_retry": retry_days[:20],
        "healed": healed[:20],
        "kline_max": kline_max,
        "empty_attempts": {k: v for k, v in sorted(empty_attempts.items())[-30:]},
    }
    _save_json(PATH_META, meta)

    # health: consecutive calendar fails on recent trading-ish window
    # Use max date present in data vs today
    all_dates = set()
    for slot in out.values():
        all_dates.update((slot.get("dates") or {}).keys())
    max_lhb = max(all_dates) if all_dates else None
    health = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "max_lhb_date": max_lhb,
        "kline_max_date": kline_max,
        "symbols": len(out),
        "fail_count_this_run": len(fail_days),
        "fail_days": fail_days[:10],
        "ok_new": ok_new[:10],
        "retry_days": retry_days[:10],
        "healed": healed[:10],
        "level": "ok" if not fail_days else ("error" if len(fail_days) >= 2 else "warn"),
        "note": (
            "ok" if not fail_days else
            "pull failures this run — check network/akshare; evening cron should cover post-close publish"
        ),
    }
    _save_json(PATH_HEALTH, health)

    print(
        f"saved {PATH_LHB} symbols={len(out)} max={max_lhb} "
        f"new_ok={len(ok_new)} fail={len(fail_days)} retry={len(retry_days)} "
        f"level={health['level']}",
        flush=True,
    )
    # Hard-fail exit only on real network/parse errors (not empty/NoneType days).
    # Exclude "today" — LHB usually publishes after ~22:00.
    today = d0.strftime("%Y-%m-%d")
    recent_fail = [
        f for f in fail_days
        if f["date"] >= (d0 - timedelta(days=5)).strftime("%Y-%m-%d")
        and f["date"] < today
    ]
    return 1 if recent_fail else 0


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=250)
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--retry-sleep", type=float, default=30.0)
    args = ap.parse_args()
    raise SystemExit(
        main(days=args.days, retries=args.retries, retry_sleep=args.retry_sleep)
    )
