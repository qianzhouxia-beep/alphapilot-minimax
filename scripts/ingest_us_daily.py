#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ingest_us_daily.py — 美股日线 ingest 模块（WB-Mac 交付件 v1.0，2026-09-15）

来源依据：E25 已实测新浪美股日线接口全历史可用、免鉴权
  https://stock.finance.sina.com.cn/usstock/api/json_v2.php/US_MinKService.getDailyK?symbol=<sym>
对照测试：stooq（JS 盾拦截）、yahoo chart（直连不通）均不可用。

设计目标（对应老板落地要求：消息/海外数据 → ingest 对接联通）：
  1. 每次运行把指定美股标的日线全量拉回，与本地缓存合并增量落盘；
  2. 输出统一 schema：{"symbol","date","open","high","low","close","volume"}（date=美东交易日 YYYY-MM-DD）；
  3. 提供 A 股交易日对齐信号函数 signal_for_cn_dates()：
     A 股日 D ← 日历上最近一个美市日 u（u 收盘在北京时间 D 日 05:00 之前，J14：信号早于收益窗）；
     返回逐日 {cn_date: {nvda_ret, qqq_ret}}，可直接喂门控（G1 overnight_us_ai_gate）。
     v1.1（2026-09-16 修）：预期美市日 u 未入库时**显式标 stale**（us_date=u, rets=null,
     g1_flag=stale），**绝不前滚复用更旧的美市日**。旧逻辑回扫 5 天、静默复用，
     致 cn 09-16 拿到 us 09-14 陈旧值（上游新浪 05:30 尚未发布 09-15 bar）。
  4. 纯标准库（urllib），服务器无需装依赖；失败重试 3 次；单标的失败不阻塞其余。

用法：
  python3 ingest_us_daily.py --out-dir /path/to/us_daily --symbols nvda,qqq
  python3 ingest_us_daily.py --out-dir ./us_daily --emit-signal   # 额外输出 overnight_signal.json

输出文件：
  <out-dir>/<symbol>.json          全量日线缓存（增量合并）
  <out-dir>/ingest_us_daily.log    运行日志（stdout 同步）
  <out-dir>/overnight_signal.json  （--emit-signal）A股日期 → 隔夜美股收益 + G1 门控原始值

接入约定（给 Cursor 的工单规格，详见 knowledge/ops/gate_spec_G1G2_20260915.md）：
  - 建议挂载点：服务器每日 05:10（A 股盘前、隔夜池重算之前）执行一次；
  - 门控消费方：morning pipeline 在 05:00 隔夜池重算与 09:36 排序之间读取 overnight_signal.json；
  - 本模块只做只读采集，不写任何生产目录；落盘位置由调用方决定。
"""
import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta

API = ("https://stock.finance.sina.com.cn/usstock/api/json_v2.php/"
       "US_MinKService.getDailyK?symbol={sym}")
DEFAULT_SYMBOLS = ["nvda", "qqq"]
FIELDS = {"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}

# G1 门控阈值（E25 五分位口径：Q4 = 样本内前 20% 分位 ≈ +2.9%；Q0 ≈ −3.1%）
# 规格文档为唯一真值来源，此处数值须与 knowledge/ops/gate_spec_G1G2_20260915.md 同步维护
G1_NVDA_UP = 0.029    # NVDA 隔夜涨幅 ≥ +2.9% ⇒ ai_chase_guard（AI 票收紧追高）
G1_NVDA_DN = -0.031   # NVDA 隔夜跌幅 ≤ −3.1% ⇒ ai_rebound_watch（AI 票低开修复观察）


def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)


def fetch_one(symbol, retries=3, timeout=30):
    """拉取单个标的全历史日线，返回 [{date,open,high,low,close,volume}] 或抛异常。"""
    url = API.format(sym=symbol)
    last_err = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = json.loads(r.read().decode("utf-8"))
            if not isinstance(raw, list) or not raw:
                raise ValueError(f"empty/invalid payload ({type(raw).__name__}, n={len(raw) if isinstance(raw, list) else '-'})")
            out = []
            for row in raw:
                try:
                    out.append({
                        "symbol": symbol.upper(),
                        "date": row["d"],
                        "open": float(row["o"]),
                        "high": float(row["h"]),
                        "low": float(row["l"]),
                        "close": float(row["c"]),
                        "volume": float(row["v"]),
                    })
                except (KeyError, ValueError, TypeError):
                    continue  # 脏行跳过，不阻塞
            if not out:
                raise ValueError("all rows dirty")
            out.sort(key=lambda x: x["date"])
            return out
        except Exception as e:  # noqa: BLE001 — 网络容错，逐次重试
            last_err = e
            log(f"  {symbol} attempt {i+1}/{retries} failed: {e}")
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"{symbol} fetch failed after {retries} retries: {last_err}")


def merge_incremental(symbol, rows, out_dir):
    """与本地缓存合并（以文件内已有数据为准，只追加更新的行），返回合并后行数。"""
    import os
    path = os.path.join(out_dir, f"{symbol}.json")
    old = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                old = json.load(f)
        except Exception as e:  # noqa: BLE001 — 缓存损坏则重建
            log(f"  WARN cache corrupted, rebuilding: {e}")
            old = []
    old_by_date = {r["date"]: r for r in old}
    for r in rows:
        old_by_date[r["date"]] = r  # 新数据覆盖旧值
    merged = sorted(old_by_date.values(), key=lambda x: x["date"])
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False)
    os.replace(tmp, path)
    return len(merged)


def load_series(out_dir, symbol):
    import os
    path = os.path.join(out_dir, f"{symbol}.json")
    with open(path, "r", encoding="utf-8") as f:
        rows = json.load(f)
    return {r["date"]: r for r in rows}


# US market full-closure holidays (NYSE/Nasdaq), used to compute the calendar
# expected session for a CN date. Observed-date shifts included (e.g. 2026-07-03
# stands in for Jul-4 which fell on a Saturday). Extend annually.
US_MARKET_HOLIDAYS = {
    "2025-01-01", "2025-01-20", "2025-02-17", "2025-04-18", "2025-05-26",
    "2025-06-19", "2025-07-04", "2025-09-01", "2025-11-27", "2025-12-25",
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
    "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
}


def is_us_session(d):
    """True if date d is a regular US trading session (weekday, non-holiday)."""
    return d.weekday() < 5 and d.isoformat() not in US_MARKET_HOLIDAYS


def expected_us_session(cn_date):
    """Latest US session strictly before cn_date (calendar-aware), ISO string.

    Its close (US 16:00 ET = next-day 04:00/05:00 Beijing) is the most recent
    close knowable before the A-share cn_date session (J14). This is the ONLY
    session a cn_date row may use; using an older one is a silent forward-roll.
    """
    d = datetime.strptime(cn_date, "%Y-%m-%d").date()
    u = d - timedelta(days=1)
    for _ in range(10):
        if is_us_session(u):
            return u.isoformat()
        u -= timedelta(days=1)
    return None


def prev_us_session(us_by_date, cn_date, cutoff_hour=5):
    """Calendar-expected US session for cn_date, ONLY IF present in cache.

    NEVER falls back to an older session. On 2026-09-16 the 05:30 ingest ran
    before Sina had published the 09-15 bar; the old "walk back up to 5 days"
    logic silently reused 09-14 for cn 09-16 (a fresh cn_date carrying stale
    foreign values, with no flag). If the expected session is absent the caller
    emits an explicit stale row instead.
    """
    exp = expected_us_session(cn_date)
    if exp is not None and exp in us_by_date:
        return exp
    return None


def signal_for_cn_dates(cn_dates, out_dir, backfill_notes=None):
    """
    输出：[{cn_date, us_date, nvda_ret, qqq_ret, g1_flag, [backfilled]}]
    g1_flag ∈ {ai_chase_guard, ai_rebound_watch, none, stale}

    stale      = 日历预期美市日未入库（上游延迟/ingest 缺口）。显式出错行，
                 **绝不前滚复用更旧的美市日**（2026-09-16 事故：us 09-15 缺失，
                 旧逻辑把 us 09-14 复用到 cn 09-16，且无任何标注）。
    backfilled = cn 日期在 <out_dir>/backfill_notes.json 里（人工订正行，附说明）。
    """
    nv = load_series(out_dir, "nvda")
    qq = load_series(out_dir, "qqq")
    backfill_notes = backfill_notes or {}

    def ret_series(by_date):
        dates = sorted(by_date)
        rets = {}
        for a, b in zip(dates, dates[1:]):
            c0 = by_date[a]["close"]
            if c0:
                rets[b] = by_date[b]["close"] / c0 - 1
        return rets

    nv_ret, qq_ret = ret_series(nv), ret_series(qq)
    out = []
    for cn in cn_dates:
        exp = expected_us_session(cn)
        if exp is None:
            continue
        u = prev_us_session(nv, cn)
        if u is None:
            # explicit missing: never forward-roll to an older session
            out.append({"cn_date": cn, "us_date": exp,
                        "nvda_ret": None, "qqq_ret": None,
                        "g1_flag": "stale",
                        "stale_reason": "expected_us_session_not_ingested"})
            continue
        nr, qr = nv_ret.get(u), qq_ret.get(u)
        flag = "none"
        if nr is not None:
            if nr >= G1_NVDA_UP:
                flag = "ai_chase_guard"
            elif nr <= G1_NVDA_DN:
                flag = "ai_rebound_watch"
        row = {"cn_date": cn, "us_date": u,
               "nvda_ret": None if nr is None else round(nr, 6),
               "qqq_ret": None if qr is None else round(qr, 6),
               "g1_flag": flag}
        if cn in backfill_notes:
            row["backfilled"] = True
            row["backfill_note"] = backfill_notes[cn]
        out.append(row)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    ap.add_argument("--emit-signal", action="store_true",
                    help="额外出 overnight_signal.json（近 30 个自然日）")
    args = ap.parse_args()
    import os
    os.makedirs(args.out_dir, exist_ok=True)

    symbols = [s.strip().lower() for s in args.symbols.split(",") if s.strip()]
    ok, fail = [], []
    for sym in symbols:
        try:
            rows = fetch_one(sym)
            n = merge_incremental(sym, rows, args.out_dir)
            first, last = rows[0]["date"], rows[-1]["date"]
            log(f"OK {sym}: {n} rows ({first} ~ {last})")
            ok.append(sym)
        except Exception as e:  # noqa: BLE001
            log(f"FAIL {sym}: {e}")
            fail.append(sym)

    if args.emit_signal:
        today = datetime.now().strftime("%Y-%m-%d")
        # staleness evidence: if the calendar-expected session is not yet in the
        # cache, say so loudly (the signal row will be marked stale, not rolled).
        exp_today = expected_us_session(today)
        try:
            last_nv = sorted(load_series(args.out_dir, "nvda"))[-1]
        except Exception:  # noqa: BLE001
            last_nv = None
        if exp_today is not None and last_nv != exp_today:
            log(f"WARN expected us session for cn {today} = {exp_today}, but "
                f"nvda cache last = {last_nv} -> row marked stale "
                f"(no forward-roll)")
        cn_dates = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                    for i in range(30)]
        cn_dates = [d for d in sorted(cn_dates) if d <= today]
        notes = {}
        np_path = os.path.join(args.out_dir, "backfill_notes.json")
        if os.path.exists(np_path):
            try:
                with open(np_path, "r", encoding="utf-8") as f:
                    notes = json.load(f)
            except Exception as e:  # noqa: BLE001
                log(f"WARN backfill_notes unreadable: {e}")
        try:
            sig = signal_for_cn_dates(cn_dates, args.out_dir, notes)
            sp = os.path.join(args.out_dir, "overnight_signal.json")
            with open(sp, "w", encoding="utf-8") as f:
                json.dump({"generated_at": today, "signal": sig}, f,
                          ensure_ascii=False, indent=1)
            n_stale = sum(1 for r in sig if r.get("g1_flag") == "stale")
            log(f"signal emitted: {sp} ({len(sig)} days, stale={n_stale})")
        except FileNotFoundError as e:
            log(f"signal skipped (need nvda+qqq caches): {e}")

    if fail:
        log(f"partial failure: ok={ok} fail={fail}")
        sys.exit(2)  # 部分失败退出码，便于上游告警区分
    log(f"all ok: {ok}")


if __name__ == "__main__":
    main()
