#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""弱市超跌反包 × 低开 — 尾盘影子 scanner（路径 C 影子先行）

在服务器 14:50 运行（cron 建议: 工作日 14:50），全市场扫描「超跌×低开」组合，
只记录候选、不下单、不改 P2 任何链路。T+1 由 reversal_shadow_report.py 结算并推送企业微信。

信号口径（与 bt_research/bt_reversal_lowopen_combo.py 完全一致）：
  - 连跌≥3 天 (down_streak >= 3)
  - 长上影: 当日 upper_shadow 在「历史 tradable 样本」60% 分位以上（滚动历史分位，无前视）
  - 120 日低位: pos120 在 40% 分位以下（滚动历史分位，无前视）
  - 近 5 日无跌停 (has_lu_down5 = False)
  - 大盘 3 日累计跌 (mkt3 <= 0, 等权全市场代理；可选上证 as-of)
  - 低开 (open_gap < 0)

数据源: mootdx 通达信直连（服务器已具备，参考 fix_kline_server.py）。
  - 拉最近 ~150 日全市场日线（pos120 需要 120 日窗口 + 缓冲）
  - 分位边界用「截止昨日」的历史样本计算（无未来函数）

产出:
  - output/reversal_shadow/{date}.json          当日候选明细
  - output/reversal_shadow_history.jsonl        逐日追加（报告用）
  - output/reversal_shadow/last_run.json        最近一次运行元信息

用法:
  python scripts/reversal_shadow_scanner.py            # 正常跑
  python scripts/reversal_shadow_scanner.py --date 2026-08-28   # 指定日期(补跑/回测)
  python scripts/reversal_shadow_scanner.py --pool-file xxx.json # 用预拉数据(测试)

Env:
  REVERSAL_SHADOW_DISABLE=1   关闭（等权开关不满足时仍记录, 用 --no-skip 强制）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
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

SHADOW_DIR = ROOT / "output" / "reversal_shadow"
HISTORY_PATH = ROOT / "output" / "reversal_shadow_history.jsonl"
LAST_RUN = SHADOW_DIR / "last_run.json"
KLINE_PATH = ROOT / "data" / "kline_cache" / "kline_all.parquet"
INDEX_HIST = ROOT / "data" / "index_klines_hist.json"
QMT_SCORE_DIR = ROOT / "output" / "qmt_scores"

# P2 候选甜蜜区标签（2026-08-29 新增）：gap ∈ [-1.5%, 0] 为甜蜜区
SWEET_LO = -1.5
SWEET_HI = 0.0

# 分位阈值（与回测一致）
UP_SHADOW_Q = 0.60   # 上影 > 历史 60% 分位
POS120_Q = 0.40      # pos120 < 历史 40% 分位
DOWN_STREAK_MIN = 3
HIST_MIN_N = 10000   # 历史分位需要的最少样本
TOP_K = 20           # 记录最多前 20 只（每日候选通常 1~62，够用）


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def lu_threshold(sym: str) -> float:
    if sym.startswith(("300", "301", "688")):
        return 0.194
    if sym.startswith(("8", "4")):
        return 0.294
    return 0.094


def _bare(sym: str) -> str:
    return str(sym or "").lower().replace("sh", "").replace("sz", "").replace("bj", "").zfill(6)[-6:]


def load_kline_hist(days: int = 150) -> pd.DataFrame:
    """加载历史 K 线（最近 days 天全市场）。"""
    if not KLINE_PATH.exists():
        return pd.DataFrame()
    df = pd.read_parquet(KLINE_PATH)
    df["symbol"] = df["symbol"].map(_bare)
    df["date"] = df["date"].astype(str).str[:10]
    df = df.sort_values(["symbol", "date"]).reset_index(drop=True)
    # 取最近 days 天
    dates = sorted(df["date"].unique())
    if len(dates) > days:
        cutoff = dates[-days]
        df = df[df["date"] >= cutoff]
    return df


def fetch_live_kline(worker: int = 16) -> pd.DataFrame:
    """用 mootdx 拉全市场最近 ~150 日日线（服务器直连通达信）。

    返回 DataFrame: symbol/date/open/high/low/close/volume/amount
    """
    try:
        from mootdx.quotes import Quotes
    except Exception as e:
        log(f"❌ mootdx 不可用: {e}")
        return pd.DataFrame()

    from concurrent.futures import ThreadPoolExecutor, as_completed

    codes = sorted(
        {p.stem for p in (ROOT / "data" / "kline5m").glob("*.parquet")}
        | {p.stem for p in (ROOT / "data" / "kline_cache").glob("*.parquet")}
        | set(load_a_share_codes())
    )
    if not codes:
        return pd.DataFrame()

    _client = Quotes.factory(market="std")

    def fetch_one(sym: str):
        try:
            df = _client.bars(symbol=sym, frequency=9, offset=150)
            if df is None or len(df) == 0:
                return None
            df = df.reset_index(drop=True)
            if "datetime" in df.columns:
                df["date"] = df["datetime"].astype(str).str[:10]
            elif "date" in df.columns:
                df["date"] = df["date"].astype(str).str[:10]
            else:
                return None
            cols = {}
            for c in ("open", "high", "low", "close", "volume", "amount"):
                if c in df.columns:
                    cols[c] = c
            if "vol" in df.columns and "volume" not in df.columns:
                cols["volume"] = "vol"
            df = df[["date"] + list(cols.keys())].rename(columns=cols)
            df["symbol"] = _bare(sym)
            return df
        except Exception:
            return None

    frames = []
    ok = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=worker) as ex:
        futs = {ex.submit(fetch_one, c): c for c in codes}
        for fut in as_completed(futs):
            r = fut.result()
            if r is not None and len(r):
                frames.append(r)
                ok += 1
            if ok % 500 == 0 and ok:
                log(f"  ... 已拉 {ok}/{len(codes)} ({time.time()-t0:.0f}s)")
    log(f"mootdx 拉取完成: {ok}/{len(codes)} 只, 耗时 {time.time()-t0:.0f}s")
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    return df[["symbol", "date", "open", "high", "low", "close", "volume", "amount"]]


def load_a_share_codes() -> list[str]:
    """从行业映射读全市场代码。"""
    p = ROOT / "data" / "stock_industry_map.json"
    if p.exists():
        try:
            return [str(k) for k in json.loads(p.read_text(encoding="utf-8"))]
        except Exception:
            pass
    return []


def compute_factor(df: pd.DataFrame) -> pd.DataFrame:
    """计算因子（as-of, 无未来函数）。df 需含 symbol/date/open/high/low/close。"""
    df = df.sort_values(["symbol", "date"]).reset_index(drop=True)
    g = df.groupby("symbol", sort=False)
    df["prev_close"] = g["close"].shift(1).to_numpy()
    df["chg"] = (df["close"] / df["prev_close"] - 1).to_numpy()
    df["open_gap"] = (df["open"] / df["prev_close"] - 1).to_numpy()

    # 连跌天数 (不含今日, 今日还没收盘; 用历史连跌 + 今日是否低开)
    df["is_down"] = (df["chg"] < 0).astype(int)
    # down_streak: 连续下跌天数 (含当日)
    streak = np.zeros(len(df), dtype=int)
    prev_sym = None
    cnt = 0
    syms = df["symbol"].to_numpy()
    downs = df["is_down"].to_numpy()
    for i in range(len(df)):
        if syms[i] != prev_sym:
            cnt = 0
            prev_sym = syms[i]
        if downs[i]:
            cnt += 1
        else:
            cnt = 0
        streak[i] = cnt
    df["down_streak"] = streak

    # 上影: (high - max(open, close)) / (high - low)
    hi = df["high"].to_numpy()
    lo = df["low"].to_numpy()
    op = df["open"].to_numpy()
    cl = df["close"].to_numpy()
    rng = np.where(hi - lo > 0, hi - lo, np.nan)
    df["upper_shadow"] = np.where(rng > 0, (hi - np.maximum(op, cl)) / rng, 0.0)

    # pos120: close 在近 120 日 (high-low) 区间的位置
    pos = []
    for sym, sd in df.groupby("symbol", sort=False):
        h = sd["high"].rolling(120, min_periods=60).max().to_numpy()
        l = sd["low"].rolling(120, min_periods=60).min().to_numpy()
        c = sd["close"].to_numpy()
        pos.append(np.where(h - l > 0, (c - l) / (h - l), np.nan))
    df["pos120"] = np.concatenate(pos) if pos else np.full(len(df), np.nan)

    # 跌停标记 (近5日无跌停)
    df["lu_thr"] = df["symbol"].map(lu_threshold).to_numpy()
    df["is_lu_down"] = (df["chg"] <= -(df["lu_thr"] - 0.004)).astype(float)
    down5 = df.groupby("symbol", sort=False)["is_lu_down"].rolling(5, min_periods=1).max().to_numpy()
    df["has_lu_down5"] = np.concatenate([[False], down5[:-1]]).astype(bool)  # T 日用 T-5..T-1

    # 市场代理: 等权全市场日收益
    day = df[df["chg"].notna()].groupby("date").agg(mkt_ret=("chg", "mean")).reset_index()
    day["mkt3"] = day["mkt_ret"].rolling(3, min_periods=3).sum()
    df = df.merge(day[["date", "mkt3"]], on="date", how="left")
    return df


def pick_candidates(df: pd.DataFrame, asof: str) -> pd.DataFrame:
    """按超跌×低开规则选候选。asof=当日日期。"""
    today = df[df["date"] == asof]
    hist = df[df["date"] < asof]  # 历史分位基准（无前视）
    if today.empty or hist.empty:
        return pd.DataFrame()

    # 历史分位边界（tradable 近似：非涨停、有成交）
    h = hist[hist["chg"].notna() & hist["close"].notna()]
    if len(h) < HIST_MIN_N:
        log(f"⚠️ 历史样本不足 {len(h)} < {HIST_MIN_N}，跳过分位判定")
        return pd.DataFrame()
    up_thr = h["upper_shadow"].quantile(UP_SHADOW_Q)
    pos_thr = h["pos120"].quantile(POS120_Q)
    log(f"分位边界: 上影>{up_thr:.3f} (60%), pos120<{pos_thr:.3f} (40%), 历史样本 n={len(h)}")

    # 当日数据为实时快照（14:50），当日 chg/open_gap 按盘中算；down_streak 含当日要谨慎
    # —— 尾盘 14:50 当日基本定型，用当日 down 状态估算连跌
    cand = today.copy()
    cand = cand[cand["down_streak"] >= DOWN_STREAK_MIN]
    cand = cand[cand["upper_shadow"] > up_thr]
    cand = cand[cand["pos120"] < pos_thr]
    cand = cand[~cand["has_lu_down5"]]
    cand = cand[cand["mkt3"] <= 0]
    cand = cand[cand["open_gap"] < 0]

    cand = cand.sort_values("open_gap").head(TOP_K)
    return cand[["symbol", "date", "open", "high", "low", "close", "open_gap",
                 "down_streak", "upper_shadow", "pos120", "chg", "mkt3"]]


def _fetch_gap_bars(syms: list[str]) -> dict:
    """补拉指定代码的当日 K 线（open/prev_close），返回 {code: open_gap}。
    全市场拉取限流时 P2 候选可能漏掉，单独补拉 10 只开销极小。"""
    if not syms:
        return {}
    try:
        from mootdx.quotes import Quotes
        _client = Quotes.factory(market="std")
    except Exception:
        return {}
    out = {}
    for sym in syms:
        try:
            df = _client.bars(symbol=sym, frequency=9, offset=3)
            if df is None or len(df) < 2:
                continue
            df = df.reset_index(drop=True)
            if "datetime" in df.columns:
                ds = df["datetime"].astype(str).str[:10].tolist()
            else:
                ds = df["date"].astype(str).str[:10].tolist()
            op = [float(x) for x in df["open"].tolist()]
            cl = [float(x) for x in df["close"].tolist()]
            # 最后两行 = 当日 + 昨日
            today_open = op[-1]
            prev_close = cl[-2]
            if today_open and prev_close and prev_close > 0:
                out[sym] = today_open / prev_close - 1.0
        except Exception:
            continue
    return out


def record_p2_candidates(df: pd.DataFrame, asof: str) -> list[dict]:
    """P2 候选甜蜜区标签（2026-08-29 新增）。

    读当日 output/qmt_scores/{date}.candidates.json（09:36 生成，Top10 P2 候选），
    用 kline 的 open_gap 打甜蜜区标签，返回候选记录列表（供历史 jsonl 落盘）。
    该记录与超跌×低开影子分开（p2_candidates 键），结算时单独对比甜蜜区 vs 非甜蜜区。
    """
    fname = asof.replace("-", "") + ".candidates.json"
    fpath = QMT_SCORE_DIR / fname
    if not fpath.exists():
        # 兼容 asof 无连字符
        fpath = QMT_SCORE_DIR / (asof + ".candidates.json")
    if not fpath.exists():
        log(f"⚠️ P2 候选文件不存在: {fpath} → 跳过 P2 甜蜜区记录")
        return []
    try:
        d = json.loads(fpath.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"⚠️ P2 候选解析失败 {fpath}: {e}")
        return []
    items = d.get("candidates") or []
    if not items:
        log("⚠️ P2 候选为空 → 跳过")
        return []

    # 当日 kline 快照（open_gap 已由 compute_factor 算好）
    today = df[df["date"] == asof]
    gap_map = {}
    if not today.empty:
        for _, r in today.iterrows():
            gap_map[str(r["symbol"]).zfill(6)] = r["open_gap"]

    # 全市场拉取漏掉的候选 → mootdx 单独补拉（仅限当日缺失的）
    missing = [str(it.get("symbol", "")).split(".")[0].zfill(6)
               for it in items
               if gap_map.get(str(it.get("symbol", "")).split(".")[0].zfill(6)) is None]
    if missing:
        extra = _fetch_gap_bars(missing)
        for sym, g in extra.items():
            gap_map[sym] = g

    recs = []
    for it in items:
        sym = str(it.get("symbol", "")).split(".")[0].zfill(6)
        gap = gap_map.get(sym)
        if gap is None or not np.isfinite(gap):
            gap = None
        sweet = bool(gap is not None and SWEET_LO <= gap * 100 <= SWEET_HI)
        recs.append({
            "symbol": sym,
            "name": it.get("name", ""),
            "rank": it.get("rank"),
            "score": round(float(it.get("score") or 0), 4),
            "open_gap": round(float(gap), 4) if gap is not None else None,
            "sweet": sweet,
        })
    n_sweet = sum(1 for r in recs if r["sweet"])
    n_gap = sum(1 for r in recs if r["open_gap"] is not None)
    log(f"P2 候选 {len(recs)} 只, gap 可得 {n_gap}, 甜蜜区 {n_sweet} 只 (gap∈[{SWEET_LO},{SWEET_HI}%])")
    return recs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--no-skip", action="store_true", help="大盘开关不满足也记录（默认跳过）")
    ap.add_argument("--pool-file", default="", help="预拉数据 parquet，跳过 mootdx（测试用）")
    args = ap.parse_args()

    asof = args.date
    if os.environ.get("REVERSAL_SHADOW_DISABLE") == "1" and not args.no_skip:
        log("REVERSAL_SHADOW_DISABLE=1，跳过")
        return 0

    SHADOW_DIR.mkdir(parents=True, exist_ok=True)
    log(f"=== 尾盘超跌×低开影子扫描 {asof} ===")

    # 1. 数据
    if args.pool_file:
        df = pd.read_parquet(args.pool_file)
        df["date"] = df["date"].astype(str).str[:10]
        df["symbol"] = df["symbol"].map(_bare)
    else:
        df = fetch_live_kline()
        if df.empty:
            log("❌ 实时数据为空，退出")
            return 1
    log(f"数据: {len(df)} 行, {df['symbol'].nunique()} 只, 日期 {df['date'].min()}~{df['date'].max()}")

    # 2. 因子
    df = compute_factor(df)

    # 3. 大盘开关
    mkt3_today = df[df["date"] == asof]["mkt3"].iloc[0] if (df["date"] == asof).any() else np.nan
    weak = bool(np.isfinite(mkt3_today) and mkt3_today <= 0)
    log(f"大盘 3 日累计: {mkt3_today*100:+.2f}% → {'弱市开关 ON' if weak else '弱市开关 OFF'}")

    # 4. 候选
    cand = pick_candidates(df, asof)
    if cand.empty:
        log("今日无超跌×低开候选")
        if not args.no_skip:
            # 记录空候选也写 jsonl（报告侧知道今天没信号）；P2 候选仍记录
            rec = {"date": asof, "n_candidates": 0, "weak_market": weak, "mkt3": float(mkt3_today) if np.isfinite(mkt3_today) else None, "candidates": []}
            p2_recs = record_p2_candidates(df, asof)
            if p2_recs:
                rec["p2_candidates"] = p2_recs
                rec["p2_n"] = len(p2_recs)
                rec["p2_n_sweet"] = sum(1 for r in p2_recs if r["sweet"])
            with open(HISTORY_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            (SHADOW_DIR / f"{asof}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
            (LAST_RUN).write_text(json.dumps({"date": asof, "ts": datetime.now().isoformat(), "n": 0}), encoding="utf-8")
            return 0

    # 5. 落盘
    recs = []
    for _, r in cand.iterrows():
        recs.append({
            "symbol": r["symbol"],
            "open_gap": round(float(r["open_gap"]), 4),
            "down_streak": int(r["down_streak"]),
            "upper_shadow": round(float(r["upper_shadow"]), 4),
            "pos120": round(float(r["pos120"]), 4),
            "chg": round(float(r["chg"]), 4) if np.isfinite(r["chg"]) else None,
            "close": float(r["close"]),
            "open": float(r["open"]),
        })
    rec = {
        "date": asof,
        "ts": datetime.now().isoformat(),
        "n_candidates": len(recs),
        "weak_market": weak,
        "mkt3": float(mkt3_today) if np.isfinite(mkt3_today) else None,
        "up_shadow_q": UP_SHADOW_Q,
        "pos120_q": POS120_Q,
        "candidates": recs,
    }
    # P2 候选甜蜜区标签（2026-08-29）
    p2_recs = record_p2_candidates(df, asof)
    if p2_recs:
        rec["p2_candidates"] = p2_recs
        rec["p2_n"] = len(p2_recs)
        rec["p2_n_sweet"] = sum(1 for r in p2_recs if r["sweet"])
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    (SHADOW_DIR / f"{asof}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    (LAST_RUN).write_text(json.dumps({"date": asof, "ts": datetime.now().isoformat(), "n": len(recs)}), encoding="utf-8")
    log(f"✅ 候选 {len(recs)} 只 → {SHADOW_DIR / (asof+'.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
