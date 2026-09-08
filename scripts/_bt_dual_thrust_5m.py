# -*- coding: utf-8 -*-
"""Dual Thrust 5分钟线 A股回测 (服务器跑, 贴近贴文原始设定)
贴文: 15分钟周期 N=20根 K=0.5; 并声称 5分钟/1分钟也适用
A股约束: T+1 (当日买次日才能卖), 只能做多, 涨跌停约束, 成本
数据: 5分钟线 2026-07-23 ~ 08-28 (26个交易日, 每只1296根)
"""
import pandas as pd
import numpy as np
import os, sys, json, glob

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = "/home/ubuntu/alphapilot/data/kline5m"
OUT = "/home/ubuntu/alphapilot/output/bt_dual_thrust_5m.json"

K = 0.5
N = 20            # 20根 5分钟 ≈ 1个交易日
COMMISSION = 0.00025
STAMP_TAX = 0.0005
SLIPPAGE = 0.001
INIT_CAP = 1_000_000.0


def limit_pct(symbol: str) -> float:
    code = symbol.split(".")[0] if "." in symbol else symbol
    if code.startswith(("30", "68")):
        return 0.20
    if code.startswith(("8", "4", "92")):
        return 0.30
    return 0.10


def dual_thrust_5m(df: pd.DataFrame, symbol: str, k=K, n=N) -> dict:
    df = df.sort_values("datetime").reset_index(drop=True)
    o = df["open"].values
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values
    dt = df["datetime"].values

    # 每日收盘价 (判断 T+1 与每日涨跌停)
    day = pd.Series(dt).dt.date.values
    day_prev_close = {}
    # 每根K线对应的昨收 = 前一交易日收盘
    df["day"] = day
    dg = df.groupby("day")["close"].last()
    prev_map = {}
    days = sorted(dg.index)
    for j, dd in enumerate(days):
        prev_map[dd] = dg.iloc[j - 1] if j > 0 else np.nan
    prev_close = np.array([prev_map.get(d, np.nan) for d in day])

    # R: 前 n 根 实体
    rng = np.full(len(df), np.nan)
    for i in range(n, len(df)):
        win_o = o[i - n:i]
        win_c = c[i - n:i]
        win_h = h[i - n:i]
        win_l = l[i - n:i]
        body_hi = np.maximum(win_o, win_c)
        body_lo = np.minimum(win_o, win_c)
        r1 = (win_h - body_lo).max()
        r2 = (body_hi - win_l).max()
        rng[i] = max(r1, r2)

    upper = o + k * rng
    lower = o - k * rng

    cash = INIT_CAP
    shares = 0.0
    entry_price = 0.0
    entry_date = None
    buy_day = None
    trades = []
    equity = []

    lp = limit_pct(symbol)

    for i in range(len(df)):
        if np.isnan(rng[i]):
            equity.append(cash)
            continue
        d = str(dt[i])[:10]
        pc = prev_close[i]
        up_limit = pc * (1 + lp) if not np.isnan(pc) else np.nan
        dn_limit = pc * (1 - lp) if not np.isnan(pc) else np.nan

        if shares > 0:
            # T+1: 买入当天不能卖
            if buy_day != d:
                sell_signal = l[i] <= lower[i]
                # 跌停卖不出
                stuck_dn = (not np.isnan(dn_limit)) and (l[i] <= dn_limit * 0.999)
                if sell_signal and not stuck_dn:
                    fill = min(c[i], lower[i])
                    fill *= (1 - SLIPPAGE)
                    proceeds = shares * fill
                    cash += proceeds - proceeds * (STAMP_TAX + COMMISSION)
                    pnl = (fill - entry_price) / entry_price
                    trades.append({
                        "entry_date": entry_date, "exit_date": d,
                        "entry": round(entry_price, 3), "exit": round(fill, 3),
                        "pnl_pct": round(pnl * 100, 2),
                        "hold_bars": i,
                        "reason": "下轨跌破"
                    })
                    shares = 0.0
                    entry_price = 0.0
                    entry_date = None
                    buy_day = None
        else:
            buy_signal = h[i] >= upper[i]
            # 涨停买不进
            stuck_up = (not np.isnan(up_limit)) and (o[i] >= up_limit * 0.999)
            if buy_signal and not stuck_up:
                fill = max(c[i], upper[i])
                fill *= (1 + SLIPPAGE)
                budget = cash * 0.95
                sh = budget / fill
                cash -= sh * fill * (1 + COMMISSION)
                shares = sh
                entry_price = fill
                entry_date = d
                buy_day = d

        equity.append(cash + shares * c[i])

    if shares > 0 and entry_date:
        last = c[-1]
        proceeds = shares * last
        cash += proceeds - proceeds * (STAMP_TAX + COMMISSION)
        pnl = (last - entry_price) / entry_price
        trades.append({
            "entry_date": entry_date, "exit_date": str(dt[-1])[:10],
            "entry": round(entry_price, 3), "exit": round(last, 3),
            "pnl_pct": round(pnl * 100, 2), "hold_bars": len(df), "reason": "结束平仓"
        })

    eq = np.array(equity)
    ret = eq[-1] / INIT_CAP - 1
    peak = np.maximum.accumulate(eq)
    mdd = ((eq - peak) / peak).min()
    if trades:
        pnls = np.array([t["pnl_pct"] for t in trades])
        wins = pnls[pnls > 0]
        losses = pnls[pnls <= 0]
        win_rate = len(wins) / len(pnls)
        avg_win = wins.mean() if len(wins) else 0
        avg_loss = losses.mean() if len(losses) else 0
    else:
        win_rate = avg_win = avg_loss = 0

    return {
        "symbol": symbol, "k": k, "n": n,
        "n_bars": len(df), "n_days": len(set(day)),
        "n_trades": len(trades),
        "total_return_pct": round(ret * 100, 2),
        "max_drawdown_pct": round(mdd * 100, 2),
        "win_rate_pct": round(win_rate * 100, 1),
        "avg_win_pct": round(avg_win, 2),
        "avg_loss_pct": round(avg_loss, 2),
        "trades_sample": trades[:8],
    }


def main():
    # 用与日线回测相同的样本 + 有代表性的活跃股
    codes = ["000001", "000002", "600519", "000858", "300750", "002415",
             "600036", "601318", "000333", "600900", "002466", "000906"]
    results = []
    for code in codes:
        p = os.path.join(BASE, code + ".parquet")
        if not os.path.exists(p):
            print(code, "MISSING")
            continue
        df = pd.read_parquet(p)
        if len(df) < 100:
            print(code, "too short", len(df))
            continue
        r = dual_thrust_5m(df, code)
        results.append(r)
        print(json.dumps(r, ensure_ascii=False))

    if results:
        tr = [r["total_return_pct"] for r in results]
        wins = [r["win_rate_pct"] for r in results]
        mdd = [r["max_drawdown_pct"] for r in results]
        summary = {
            "n_symbols": len(results),
            "n_days": results[0]["n_days"],
            "avg_total_return_pct": round(np.mean(tr), 2),
            "avg_win_rate_pct": round(np.mean(wins), 1),
            "avg_max_drawdown_pct": round(np.mean(mdd), 2),
            "n_positive": sum(1 for x in tr if x > 0),
        }
        print("=== SUMMARY ===")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump({"per_symbol": results, "summary": summary}, f, ensure_ascii=False, indent=2)
        print("saved:", OUT)


if __name__ == "__main__":
    main()
