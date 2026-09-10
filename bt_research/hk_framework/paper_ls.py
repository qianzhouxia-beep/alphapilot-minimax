#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""paper_ls: 带做空的多空纸盘引擎（HK/US 波段研究，Cursor 2026-09-10）。

支持三种模式:
  long_only   只做多 top-N（基线，与 paper.py 对齐）
  long_short  多 top-k / 空 bottom-k（美元中性，需个股借券）
  long_hedge  多 top-N + 空指数 ETF(02800 盈富基金)等名义（beta 对冲，现实可行）

口径:
  - T 收盘出信号 → T+1 开盘成交（滑点）→ 持有 HOLD_DAYS → 到期日收盘平仓
  - 费用: 买卖双边按 config.COST（HK 印花税 0.1% 双边）
  - 借券成本: 空头按 borrow_annual 年化、按自然日计提（个股默认 3%/年，ETF 1%/年）
  - ⚠️ 港股做空仅限港交所「指定可卖空名单」内证券（每季调整）+ 需借券；
       本引擎为研究/纸盘，未强制该名单——实盘前必须过名单与可借检查（见 README）。
"""
import config as C
import dataio as io
from paper import trade_cost


class LongShortEngine:
    def __init__(self, market=C.MARKET, cash=None, hold_days=None,
                 mode="long_short", top_n=10, bottom_n=10,
                 per_trade_frac=C.PER_TRADE_FRAC, max_pos=C.MAX_POSITIONS,
                 borrow_annual=C.SHORT_BORROW_ANNUAL, hedge_code="02800",
                 hedge_borrow=C.HEDGE_BORROW_ANNUAL, shortable=None):
        self.market = market
        self.cash = cash if cash is not None else C.INIT_CASH
        self.init_cash = self.cash
        self.hold_days = hold_days or C.HOLD_DAYS
        self.mode = mode
        self.top_n = top_n
        self.bottom_n = bottom_n
        self.per_trade_frac = per_trade_frac
        self.max_pos = max_pos
        self.borrow_annual = borrow_annual
        self.hedge_code = hedge_code
        self.hedge_borrow = hedge_borrow
        # 可卖空名单：显式传入 > config 文件 > None(=研究模式放开,仅警告)
        if shortable is None:
            sk = io.load(C.F_SHORTABLE, {}) or {}
            shortable = set(sk.get("codes") or [])
        self.shortable = set(shortable)
        self.skipped_short = 0
        self.positions = {}     # code -> {shares(signed), entry_px, entry_date, exit_date, side, fee, notional}
        self.ledger = []
        self.equity_curve = []
        self.long_pending = []
        self.short_pending = []
        self.trade_days = []

    # ---------- 做空资格 ----------
    def _short_ok(self, code, date, ctx):
        """港股做空现实约束：名单内 + 非仙股 + 非妖股(前日极端波动=无券/费率高)。"""
        if self.shortable and code not in self.shortable:
            return False
        bars, i = ctx.bar(code, date)
        if not bars or i < 2:
            return False
        px = bars[i]["o"]
        if px < C.SHORT_MIN_PRICE:
            return False
        prev = bars[i - 1]["c"]
        prev2 = bars[i - 2]["c"]
        if prev2 and abs(prev / prev2 - 1) > C.SHORT_MAX_ABS_1D:
            return False
        return True

    # ---------- 调度 ----------
    def schedule(self, longs, shorts):
        self.long_pending, self.short_pending = list(longs), list(shorts)

    # ---------- 开盘 ----------
    def _open_one(self, code, side, date, ctx):
        if code in self.positions:
            return
        bars, i = ctx.bar(code, date)
        if not bars:
            return
        slip = C.SHORT_SLIPPAGE if side == "short" else C.COST[self.market]["slippage"]
        px = bars[i]["o"] * (1 + slip) if side == "long" else bars[i]["o"] * (1 - slip)
        notional = self.init_cash * self.per_trade_frac
        shares = int(notional / px)
        if shares <= 0:
            return
        signed = shares if side == "long" else -shares
        gross = shares * px
        fee = trade_cost(self.market, gross, "buy" if side == "long" else "sell", shares)
        if side == "long" and gross + fee > self.cash:
            return
        self.cash += (-gross - fee) if side == "long" else (gross - fee)
        di = self.trade_days.index(date)
        exit_date = self.trade_days[min(di + self.hold_days, len(self.trade_days) - 1)]
        self.positions[code] = {"shares": signed, "entry_px": px, "entry_date": date,
                                "exit_date": exit_date, "side": side, "entry_fee": fee,
                                "entry_notional": gross}

    def execute_open(self, date, ctx):
        for code in self.long_pending:
            if sum(1 for p in self.positions.values() if p["side"] == "long") >= self.max_pos:
                break
            self._open_one(code, "long", date, ctx)
        if self.mode in ("long_short", "long_hedge"):
            for code in self.short_pending:
                if sum(1 for p in self.positions.values() if p["side"] == "short") >= self.max_pos:
                    break
                if code != self.hedge_code and not self._short_ok(code, date, ctx):
                    self.skipped_short += 1
                    continue
                self._open_one(code, "short", date, ctx)
        self.long_pending, self.short_pending = [], []

    # ---------- 收盘 ----------
    def execute_close(self, date, ctx):
        for code in list(self.positions.keys()):
            pos = self.positions[code]
            if pos["exit_date"] != date:
                continue
            bars, i = ctx.bar(code, date)
            if not bars:
                continue
            slip = C.SHORT_SLIPPAGE if pos["side"] == "short" else C.COST[self.market]["slippage"]
            px = bars[i]["c"] * (1 - slip) if pos["side"] == "long" else bars[i]["c"] * (1 + slip)
            shares = abs(pos["shares"])
            gross = shares * px
            fee = trade_cost(self.market, gross, "sell" if pos["side"] == "long" else "buy", shares)
            borrow_days = max(1, (self.trade_days.index(date) - self.trade_days.index(pos["entry_date"])))
            rate = self.hedge_borrow if code == self.hedge_code else self.borrow_annual
            borrow = pos["entry_notional"] * rate * borrow_days / 365.0 if pos["side"] == "short" else 0.0
            if pos["side"] == "long":
                self.cash += gross - fee
                pnl = gross - fee - pos["entry_notional"] - pos["entry_fee"]
            else:
                self.cash -= gross + fee + borrow   # 买回平空
                pnl = pos["entry_notional"] - gross - fee - pos["entry_fee"] - borrow
            self.ledger.append({
                "code": code, "side": pos["side"], "entry_date": pos["entry_date"],
                "exit_date": date, "entry_px": round(pos["entry_px"], 4), "exit_px": round(px, 4),
                "shares": shares, "pnl": round(pnl, 2),
                "ret": round(pnl / (pos["entry_notional"] + pos["entry_fee"]), 5),
                "borrow": round(borrow, 2)})
            del self.positions[code]

    # ---------- 估值 ----------
    def mark(self, date, ctx):
        mv = 0.0
        for code, pos in self.positions.items():
            px = ctx.price(code, date, "c") or pos["entry_px"]
            mv += px * pos["shares"]     # 空头为负
        self.equity_curve.append({"date": date, "equity": round(self.cash + mv, 2),
                                  "cash": round(self.cash, 2),
                                  "n_pos": len(self.positions)})

    # ---------- 主循环 ----------
    def run(self, ctx, trade_days, scorer, start_idx=1, gate=None):
        self.trade_days = trade_days
        for di in range(start_idx, len(trade_days)):
            d = trade_days[di]
            self.execute_open(d, ctx)
            self.execute_close(d, ctx)
            self.mark(d, ctx)
            if di + 1 < len(trade_days):
                res = scorer(ctx, d)
                allow = gate(ctx, d) if gate else {"long", "short"}
                longs = [p["code"] for p in res["picks"][:self.top_n]] if "long" in allow else []
                shorts = []
                if "short" in allow and self.mode == "long_short":
                    shorts = [p["code"] for p in res["picks"][-self.bottom_n:]]
                elif "short" in allow and self.mode == "long_hedge":
                    shorts = [self.hedge_code]
                self.schedule(longs, shorts)
        return self.summary()

    def summary(self):
        import math
        import statistics as st
        vals = [e["equity"] for e in self.equity_curve]
        rets = [vals[i] / vals[i - 1] - 1 for i in range(1, len(vals)) if vals[i - 1]]
        peak, mdd = vals[0], 0.0
        for v in vals:
            peak = max(peak, v)
            mdd = min(mdd, v / peak - 1)
        sd = st.pstdev(rets) if len(rets) > 1 else 0.0
        lr = [l["ret"] for l in self.ledger]
        longs = [l["ret"] for l in self.ledger if l["side"] == "long"]
        shorts = [l["ret"] for l in self.ledger if l["side"] == "short"]
        # 多头侧收益（做空收益为正表示做空赚钱）
        return {
            "mode": self.mode,
            "total_return": round((vals[-1] / self.init_cash - 1) if vals else 0.0, 4),
            "sharpe": round(st.mean(rets) / sd * math.sqrt(252), 2) if sd else 0.0,
            "max_dd": round(mdd, 4),
            "n_trades": len(lr),
            "win_rate": round(sum(1 for r in lr if r > 0) / len(lr), 4) if lr else 0.0,
            "avg_ret": round(st.mean(lr), 5) if lr else 0.0,
            "long_n": len(longs), "long_avg": round(st.mean(longs), 5) if longs else 0.0,
            "short_n": len(shorts), "short_avg": round(st.mean(shorts), 5) if shorts else 0.0,
            "skipped_short": self.skipped_short,
            "final_equity": round(vals[-1], 2) if vals else self.init_cash,
        }


def scorer_wrap(ctx, date):
    import signals as S
    return S.pick(ctx, date)
