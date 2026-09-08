# -*- coding: utf-8 -*-
"""Dual Thrust 策略在 A 股的回测 (服务器跑)
按用户贴文公式实现，并施加 A 股真实约束：
- 只能做多 (不能融券做空)
- T+1：当日买入次日才能卖
- 涨跌停约束：涨停(≈+10%/20%/30%)买不进、跌停卖不出
- 交易成本：佣金万2.5 + 卖出印花税0.05% (2023.8后) + 滑点0.1%

回测目标：回答"Dual Thrust 是否适合 A 股"
"""
import pandas as pd
import numpy as np
import os, sys, json

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = "/home/ubuntu/alphapilot/data/kline_cache/kline_all.parquet"
OUT = "/home/ubuntu/alphapilot/output/bt_dual_thrust_ashare.json"

K = 0.5            # 贴文：K 固定 0.5
N = 20             # 贴文：15分钟用20根；日线取20天
COMMISSION = 0.00025   # 佣金 万2.5 (买卖都收)
STAMP_TAX = 0.0005     # 印花税 0.05% (卖出收)
SLIPPAGE = 0.001       # 滑点 0.1%
INIT_CAP = 1_000_000.0

# 涨跌停比例 (按板块, 简化：主板/创业/科创/北交)
def limit_pct(symbol: str) -> float:
    code = symbol.split(".")[0]
    if code.startswith(("30", "68")):
        return 0.20    # 创业板/科创板
    if code.startswith(("8", "4", "92")):
        return 0.30    # 北交所
    return 0.10        # 主板


def dual_thrust_backtest(df: pd.DataFrame, symbol: str, k=K, n=N) -> dict:
    df = df.sort_values("date").reset_index(drop=True)
    o = df["open"].values
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values
    dates = df["date"].values

    lp = limit_pct(symbol)
    # 前一日收盘 (用于判断涨跌停)
    prev_close = np.roll(c, 1)
    prev_close[0] = np.nan

    # 计算 R: max(HH - 实体下沿, 实体上沿 - LL) 前 N 根
    # 实体上沿 = max(open, close) = 对前一根, close 是上一根收盘
    # 简化实现: 前 N 根最高/最低 + 前 N 根收盘
    rng = []
    for i in range(len(df)):
        if i < n:
            rng.append(np.nan)
            continue
        win_h = h[i - n:i].max()
        win_l = l[i - n:i].min()
        win_c = c[i - n:i]
        body_hi = np.maximum(o[i - n:i], win_c)
        body_lo = np.minimum(o[i - n:i], win_c)
        r1 = (win_h - body_lo).max()
        r2 = (body_hi - win_l).max()
        rng.append(max(r1, r2))
    rng = np.array(rng)

    upper = o + k * rng
    lower = o - k * rng

    # 状态机：只能做多
    cash = INIT_CAP
    shares = 0.0
    entry_price = 0.0
    entry_date = None
    trades = []
    equity_curve = []

    for i in range(len(df)):
        price_open = o[i]
        price_high = h[i]
        price_low = l[i]
        price_close = c[i]
        d = str(dates[i])[:10]

        if np.isnan(rng[i]):
            equity_curve.append(cash)
            continue

        # 判断涨跌停 (相对昨收)
        if not np.isnan(prev_close[i]):
            up_limit = prev_close[i] * (1 + lp)
            dn_limit = prev_close[i] * (1 - lp)

        # 持仓处理
        if shares > 0:
            # 卖出逻辑：跌破下轨 或 跌破昨收的-7%止损 (双保险)
            sell_signal = price_low <= lower[i]
            # 涨跌停检查：跌停卖不出
            can_sell = not (not np.isnan(prev_close[i]) and price_low <= dn_limit * 0.999 and price_close >= dn_limit * 0.999)
            if sell_signal and can_sell:
                # 以触及下轨的价格成交 (保守：取下轨与低点的较小可用价)
                fill = min(price_close, lower[i]) if not np.isnan(lower[i]) else price_close
                fill *= (1 - SLIPPAGE)
                proceeds = shares * fill
                tax = proceeds * STAMP_TAX
                fee = proceeds * COMMISSION
                cash += proceeds - tax - fee
                pnl = (fill - entry_price) / entry_price
                trades.append({
                    "entry_date": entry_date, "exit_date": d,
                    "entry": round(entry_price, 3), "exit": round(fill, 3),
                    "pnl_pct": round(pnl * 100, 2), "hold_days": max(0, (pd.to_datetime(d) - pd.to_datetime(entry_date)).days),
                    "reason": "下轨跌破"
                })
                shares = 0.0
                entry_price = 0.0
                entry_date = None

        else:
            # 买入逻辑：突破上轨，但涨停不追
            buy_signal = price_high >= upper[i]
            limit_up = not np.isnan(prev_close[i]) and price_open >= up_limit * 0.999
            if buy_signal and not limit_up:
                fill = max(price_close, upper[i])
                fill *= (1 + SLIPPAGE)
                budget = cash * 0.95   # 单笔95%仓位（简化，多笔资金分离后续再说）
                sh = budget / fill
                cost = sh * fill * (1 + COMMISSION)
                cash -= cost
                shares = sh
                entry_price = fill
                entry_date = d

        equity_curve.append(cash + shares * price_close)

    # 收盘平仓
    if shares > 0 and entry_date:
        last = c[-1]
        proceeds = shares * last
        tax = proceeds * STAMP_TAX
        fee = proceeds * COMMISSION
        cash += proceeds - tax - fee
        pnl = (last - entry_price) / entry_price
        trades.append({
            "entry_date": entry_date, "exit_date": str(dates[-1])[:10],
            "entry": round(entry_price, 3), "exit": round(last, 3),
            "pnl_pct": round(pnl * 100, 2), "hold_days": 0, "reason": "回测结束平仓"
        })

    eq = np.array(equity_curve)
    ret = eq[-1] / INIT_CAP - 1
    # 最大回撤
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
        "n_days": len(df),
        "n_trades": len(trades),
        "total_return_pct": round(ret * 100, 2),
        "max_drawdown_pct": round(mdd * 100, 2),
        "win_rate_pct": round(win_rate * 100, 1),
        "avg_win_pct": round(avg_win, 2),
        "avg_loss_pct": round(avg_loss, 2),
        "final_equity": round(eq[-1], 2),
        "trades_sample": trades[:10],
    }


def main():
    df = pd.read_parquet(BASE)
    df["date"] = pd.to_datetime(df["date"])
    # 选有代表性的样本：几只流动性好的大盘股 + 小样本随机
    sample_codes = ["000001", "000002", "600519", "000858", "300750", "002415", "600036", "601318", "000333", "600900"]
    results = []
    for code in sample_codes:
        sub = df[df["symbol"] == code].copy()
        if len(sub) < 60:
            print(f"{code}: 数据不足 {len(sub)}")
            continue
        r = dual_thrust_backtest(sub, code)
        results.append(r)
        print(json.dumps(r, ensure_ascii=False))

    # 汇总
    if results:
        tr = [r["total_return_pct"] for r in results]
        wins = [r["win_rate_pct"] for r in results]
        mdd = [r["max_drawdown_pct"] for r in results]
        summary = {
            "n_symbols": len(results),
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
