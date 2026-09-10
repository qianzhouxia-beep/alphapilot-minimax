#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""paper: 交易成本 + 轻量纸盘引擎（自建，仿 crypto paper_trader 结构）。

时序（每日事件循环）:
  T 收盘算信号 -> 挂单 -> T+1 开盘成交 -> 持有 HOLD_DAYS -> 到期日收盘卖出
  （与南向 IC 口径一致：D+1 open 买 → D+1+H close 卖）

不含 A 股竞价门/P2 确认；纯日频。费用按 config.COST 真实费率扣。
"""
import config as C
import dataio as io


# ---------------- 费用 ----------------
def trade_cost(market: str, notional: float, side: str, shares: float = 0.0) -> float:
    """单边费用（印花税/佣金/平台/SEC），不含滑点。"""
    c = C.COST.get(market, C.COST["HK"])
    fee = 0.0
    if side == "sell" and market == "US":
        fee += notional * c.get("sec_fee_rate", 0.0)
    fee += notional * c.get("stamp_rate", 0.0)          # HK 双边印花税
    fee += max(notional * c.get("comm_rate", 0.0), c.get("comm_min", 0.0))
    fee += c.get("platform", 0.0)
    return fee


# ---------------- 引擎 ----------------
class PaperEngine:
    def __init__(self, market: str = C.MARKET, cash: float = None,
                 max_pos: int = None, per_trade_frac: float = None,
                 hold_days: int = None):
        self.market = market
        self.cash = cash if cash is not None else C.INIT_CASH
        self.init_cash = self.cash
        self.max_pos = max_pos or C.MAX_POSITIONS
        self.per_trade_frac = per_trade_frac or C.PER_TRADE_FRAC
        self.hold_days = hold_days or C.HOLD_DAYS
        self.positions: dict[str, dict] = {}
        self.ledger: list[dict] = []
        self.equity_curve: list[dict] = []
        self.pending: list[str] = []      # 待 T+1 开盘买入
        self.trade_days: list[str] = []

    # ---- 调度 ----
    def schedule(self, codes: list[str]):
        self.pending = list(codes)

    # ---- 开盘执行 ----
    def execute_open(self, date: str, ctx):
        still = []
        for code in self.pending:
            if len(self.positions) >= self.max_pos:
                still.append(code)
                continue
            bars, i = ctx.bar(code, date)
            if not bars:
                continue   # 停牌/无K线，弃单
            slip = C.COST[self.market]["slippage"]
            px = bars[i]["o"] * (1 + slip)
            notional = self.init_cash * self.per_trade_frac
            shares = int(notional / px)
            if shares <= 0:
                continue
            gross = shares * px
            fee = trade_cost(self.market, gross, "buy", shares)
            if gross + fee > self.cash:
                continue
            self.cash -= gross + fee
            # 到期日 = date + hold_days 个交易日
            di = self.trade_days.index(date)
            exit_date = self.trade_days[min(di + self.hold_days, len(self.trade_days) - 1)]
            self.positions[code] = {"shares": shares, "entry_px": px, "entry_date": date,
                                    "exit_date": exit_date, "entry_fee": fee,
                                    "entry_notional": gross}
        self.pending = still

    # ---- 收盘执行 ----
    def execute_close(self, date: str, ctx):
        for code in list(self.positions.keys()):
            pos = self.positions[code]
            if pos["exit_date"] != date:
                continue
            bars, i = ctx.bar(code, date)
            if not bars:
                continue   # 停牌顺延
            slip = C.COST[self.market]["slippage"]
            px = bars[i]["c"] * (1 - slip)
            gross = pos["shares"] * px
            fee = trade_cost(self.market, gross, "sell", pos["shares"])
            self.cash += gross - fee
            pnl = gross - fee - pos["entry_notional"] - pos["entry_fee"]
            self.ledger.append({
                "code": code, "entry_date": pos["entry_date"], "exit_date": date,
                "entry_px": round(pos["entry_px"], 4), "exit_px": round(px, 4),
                "shares": pos["shares"], "pnl": round(pnl, 2),
                "ret": round(pnl / (pos["entry_notional"] + pos["entry_fee"]), 5),
                "entry_fee": round(pos["entry_fee"], 2), "exit_fee": round(fee, 2),
            })
            del self.positions[code]

    # ---- 收盘估值 ----
    def mark(self, date: str, ctx):
        mv = 0.0
        for code, pos in self.positions.items():
            px = ctx.price(code, date, "c")
            mv += (px if px else pos["entry_px"]) * pos["shares"]
        self.equity_curve.append({"date": date, "equity": round(self.cash + mv, 2),
                                  "cash": round(self.cash, 2),
                                  "n_pos": len(self.positions)})

    # ---- 主循环 ----
    def run(self, ctx, trade_days: list[str], scorer, start_idx: int = 1):
        self.trade_days = trade_days
        for di in range(start_idx, len(trade_days)):
            d = trade_days[di]
            self.execute_open(d, ctx)                       # 开盘：昨日信号
            self.execute_close(d, ctx)                      # 收盘：到期卖出
            self.mark(d, ctx)                               # 估值
            if di + 1 < len(trade_days):                    # 收盘后算信号挂到次日
                res = scorer(ctx, d)
                self.schedule([p["code"] for p in res["picks"]])
        return self.summary()

    def summary(self) -> dict:
        import statistics as st
        rets = [l["ret"] for l in self.ledger]
        eq = self.equity_curve
        s = {
            "init_cash": self.init_cash,
            "final_equity": eq[-1]["equity"] if eq else self.init_cash,
            "total_return": round((eq[-1]["equity"] / self.init_cash - 1) if eq else 0.0, 4),
            "n_trades": len(rets),
            "win_rate": round(sum(1 for r in rets if r > 0) / len(rets), 4) if rets else 0.0,
            "avg_ret": round(st.mean(rets), 5) if rets else 0.0,
            "median_ret": round(st.median(rets), 5) if rets else 0.0,
            "best": round(max(rets), 4) if rets else 0.0,
            "worst": round(min(rets), 4) if rets else 0.0,
        }
        return s

    def persist(self, summary: dict):
        io.save_atomic({"summary": summary, "positions": self.positions,
                        "cash": self.cash}, C.F_STATE)
        for row in self.ledger:
            io.append_jsonl(row, C.F_LEDGER)
        for row in self.equity_curve:
            io.append_jsonl(row, C.F_EQUITY)
