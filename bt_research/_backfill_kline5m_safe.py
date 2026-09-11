#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""5m K 线历史回补（安全重开版，baostock 源，不复权）

背景（2026-09-11 事故后重设计）
  - 旧版 backfill_kline5m_baostock.py 用 4 shard 并发 → baostock 拉黑服务器 IP
    （login 返回 10001011 黑名单用户），全市场只成功 2.1%。
  - 本版纪律：**单线程 + 逐只限速 + 每日配额 + login 带超时 + 失败即退**，
    绝不并发刷 IP。服务恢复后由 cron 每日自动跑一点，分日补齐 ≥6 个月。

安全约束（与旧版一致）
  - 只新增 datetime < 现有最早 bar 的行，绝不改写/删除现有行；原子写；可断点续跑。
  - 避开 16:18-16:28 的 build_kline5m.py 写入窗口。

当前实测（2026-09-11）：baostock 从上海/新加坡/Mac 三处均不可用
  （服务器=黑名单；SG/Mac=login 超时）。本脚本 `--probe` 可探活；cron 先探活再决定是否回补。

用法
  python3 backfill_kline5m_safe.py --probe                 # 只探活（≤15s），不抓数
  python3 backfill_kline5m_safe.py --quota 250             # 单次最多回补 250 只
  python3 backfill_kline5m_safe.py --start 2026-03-01      # 指定目标起点
  python3 backfill_kline5m_safe.py --dry-run               # 只报还需回补多少只
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path("/home/ubuntu/alphapilot")
DATA5M = ROOT / "data" / "kline5m"
LOG = ROOT / "output" / "logs" / "backfill_kline5m_safe.log"
STATE = ROOT / "output" / "logs" / "backfill_kline5m_safe_state.json"
COLS = ["open", "close", "high", "low", "vol", "amount",
        "year", "month", "day", "hour", "minute", "datetime", "volume", "symbol"]

LOGIN_TIMEOUT = 15      # login 最长等待秒数（避免像 SG/Mac 那样无限 hang）
RATE_SLEEP = 1.2        # 每只之间休眠
DAILY_QUOTA = 250       # 单次（单日）最多处理的股票数
DEFAULT_START = "2026-03-01"


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


class _Timeout(Exception):
    pass


def _alarm(_s, _f):
    raise _Timeout()


def login_ok():
    """带超时的 login。返回 (ok, msg)。"""
    try:
        import baostock as bs
    except Exception as e:  # noqa: BLE001
        return False, f"import_err:{e}"
    signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(LOGIN_TIMEOUT)
    try:
        lg = bs.login()
        ok = getattr(lg, "error_code", "?") == "0"
        return ok, f"{lg.error_code}:{lg.error_msg}"
    except _Timeout:
        return False, f"login_timeout>{LOGIN_TIMEOUT}s"
    except Exception as e:  # noqa: BLE001
        return False, f"login_err:{e}"
    finally:
        signal.alarm(0)


def bcode(sym: str):
    s = str(sym).strip().zfill(6)
    if s.startswith("6"):
        return "sh." + s
    if s.startswith(("0", "3")):
        return "sz." + s
    return None


def _rows_to_df(rows, fields, symbol):
    df = pd.DataFrame(rows, columns=fields)
    dt = pd.to_datetime(df["time"].astype(str).str[:14], format="%Y%m%d%H%M%S", errors="coerce")
    out = pd.DataFrame({
        "open": pd.to_numeric(df["open"], errors="coerce"),
        "close": pd.to_numeric(df["close"], errors="coerce"),
        "high": pd.to_numeric(df["high"], errors="coerce"),
        "low": pd.to_numeric(df["low"], errors="coerce"),
        "vol": pd.to_numeric(df["volume"], errors="coerce"),
        "amount": pd.to_numeric(df["amount"], errors="coerce"),
        "datetime": dt,
    }).dropna(subset=["datetime"])
    out["year"] = out["datetime"].dt.year
    out["month"] = out["datetime"].dt.month
    out["day"] = out["datetime"].dt.day
    out["hour"] = out["datetime"].dt.hour
    out["minute"] = out["datetime"].dt.minute
    out["volume"] = out["vol"]
    out["symbol"] = str(symbol).zfill(6)
    return out[COLS]


def fetch(symbol, start, end):
    import baostock as bs
    code = bcode(symbol)
    if code is None:
        return None, "bse_unsupported"
    rs = bs.query_history_k_data_plus(
        code, "date,time,open,high,low,close,volume,amount",
        start_date=start, end_date=end, frequency="5", adjustflag="3")
    if rs.error_code != "0":
        return None, f"bs_err_{rs.error_code}:{rs.error_msg}"
    rows = []
    while rs.next():
        rows.append(rs.get_row_data())
    if not rows:
        return pd.DataFrame(columns=COLS), None
    return _rows_to_df(rows, rs.fields, symbol), None


def existing_min(path: Path):
    try:
        d = pd.read_parquet(path, columns=["datetime"])
        return pd.to_datetime(d["datetime"]).min()
    except Exception:
        return None


def _guard_build_window():
    hm = time.localtime().tm_hour * 60 + time.localtime().tm_min
    if (16 * 60 + 18) <= hm <= (16 * 60 + 28):
        wait = (16 * 60 + 29 - hm) * 60 + 5
        log(f"  [guard] 避开 build_kline5m 窗口(16:20)，休眠 {wait}s")
        time.sleep(wait)


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(st: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, STATE)


def pending_symbols(start_ts: pd.Timestamp):
    """还需回补的票：现有最早 bar > start+7d（已覆盖的跳过）。"""
    deadline = start_ts + pd.Timedelta(days=7)
    todo = []
    for p in sorted(DATA5M.glob("*.parquet")):
        if not p.stem.isdigit():
            continue
        emin = existing_min(p)
        if emin is None:
            todo.append((p.stem, None))
        elif emin > deadline:
            todo.append((p.stem, emin))
    return todo


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=DEFAULT_START)
    ap.add_argument("--quota", type=int, default=DAILY_QUOTA)
    ap.add_argument("--rate", type=float, default=RATE_SLEEP)
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    ok, msg = login_ok()
    if args.probe:
        log(f"[probe] baostock login_ok={ok} msg={msg}")
        return 0 if ok else 2
    if not ok:
        log(f"[skip] baostock 不可用（{msg}）；不刷 IP，退出。")
        return 2

    start_ts = pd.Timestamp(args.start)
    todo = pending_symbols(start_ts)
    log(f"baostock login ok; 待回补 {len(todo)} 只 (> {args.start}+7d)")
    if args.dry_run:
        return 0

    import baostock as bs
    st = load_state()
    st["last_run"] = datetime.now().isoformat(timespec="seconds")
    st["pending"] = len(todo)
    selected = todo[: max(0, args.quota)]
    done = skipped = empty = failed = 0
    added = 0
    t0 = time.time()
    try:
        for i, (sym, emin) in enumerate(selected, 1):
            if i % 20 == 0:
                _guard_build_window()
            end = str(emin.date()) if emin is not None else "2026-07-22"
            df, err = fetch(sym, args.start, end)
            if err:
                failed += 1
            elif df is None or not len(df):
                empty += 1
            else:
                new = df[df["datetime"] < emin] if emin is not None else df
                if not len(new):
                    skipped += 1
                else:
                    p = DATA5M / f"{sym}.parquet"
                    out = pd.concat([new, pd.read_parquet(p)], ignore_index=True)
                    out = out.drop_duplicates(subset=["datetime"], keep="first")
                    out = out.sort_values("datetime").reset_index(drop=True)
                    tmp = p.with_suffix(".parquet.tmp")
                    out.to_parquet(tmp, index=False)
                    os.replace(tmp, p)
                    done += 1
                    added += len(new)
            if i % 25 == 0:
                log(f"  进度 {i}/{len(selected)} ok={done} skip={skipped} "
                    f"empty={empty} fail={failed} +{added:,}行")
            time.sleep(args.rate)   # 关键：逐只限速，避免拉黑
    finally:
        bs.logout()
    st.update({"last_done": done, "last_added_rows": added,
               "quota": args.quota, "elapsed_s": round(time.time() - t0)})
    save_state(st)
    log(f"=== 本轮完成 处理 {len(selected)} 只 ok={done} skip={skipped} "
        f"empty={empty} fail={failed} +{added:,}行 ({time.time()-t0:.0f}s) ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
