#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HK/US paper-trading framework — config (Cursor 2026-09-10).

单一配置入口。所有路径可由 HK_BASE / HK_DATA / HK_OUT 覆盖，
便于本地测试 → 新加坡部署同一份代码。
"""
import os

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("HK_DATA", os.path.join(BASE, "data"))
OUT = os.environ.get("HK_OUT", os.path.join(BASE, "output"))
os.makedirs(DATA, exist_ok=True)
os.makedirs(OUT, exist_ok=True)

# ---- files ----
F_POOL = os.path.join(DATA, "pool.json")
F_KLINE = os.path.join(DATA, "kline.json")
F_SOUTH = os.path.join(DATA, "southbound_hist.json")
F_READY = os.path.join(OUT, "readiness.json")
F_PICKS = os.path.join(OUT, "picks_{date}.json")
F_STATE = os.path.join(OUT, "paper_state.json")
F_LEDGER = os.path.join(OUT, "paper_ledger.jsonl")
F_EQUITY = os.path.join(OUT, "paper_equity.jsonl")
F_WEIGHTS = os.path.join(DATA, "factor_weights.json")
F_SHORTABLE = os.path.join(DATA, "shortable.json")   # 港交所可卖空指定证券名单

# ---- http ----
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")
REFERER = "https://gu.qq.com/"

# ---- universe / trading ----
KLINE_N = 200                 # 日K根数（含预热）
POOL_MIN_MED_AMOUNT = 20e6    # 港股通池流动性阈：成交额中位 ≥ 2000万 HKD
POOL_MIN_BARS = 60            # 至少 60 根可用日K
SCORE_TOP_N = 20              # 每日打分取前 N
HOLD_DAYS = 5                 # 持仓天数（D+1 开盘买 → D+1+H 收盘卖）
INIT_CASH = 1_000_000.0       # 纸盘初始资金
MAX_POSITIONS = 10            # 最大同时持仓数
PER_TRADE_FRAC = 0.1          # 单笔占用资金比例

# ---- 做空约束（港股，2026-09-10 加；把回测做严）----
SHORT_MIN_PRICE = 1.0          # 仙股（<1 HKD）禁止做空（无券可借）
SHORT_MAX_ABS_1D = 0.25        # 前一日 |涨跌| > 25% 视为妖股，无券/费率极高，禁止做空
SHORT_BORROW_ANNUAL = 0.08     # 个股借券费 8%/年（保守；冷门票可达 50%+）
HEDGE_BORROW_ANNUAL = 0.01     # 指数 ETF(02800) 借券费 1%/年
SHORT_SLIPPAGE = 0.003         # 空头小盘滑点 0.3%（远高于大盘）

# ---- 交易成本（纸盘按真实费率扣；数值为初值，开户后按实际费率校正）----
COST = {
    "HK": {
        "stamp_rate": 0.001,      # 印花税 0.1%（2023-11 起）双边
        "comm_rate": 0.0005,      # 佣金 0.05%（券商各异）
        "comm_min": 3.0,          # 最低佣金 HKD
        "platform": 15.0,         # 平台费/笔 HKD（如富途）
        "slippage": 0.0005,       # 纸盘滑点
    },
    "US": {
        "stamp_rate": 0.0,
        "sec_fee_rate": 0.0000278,  # SEC 费（仅卖出，极少）
        "comm_rate": 0.0005,
        "comm_min": 1.0,
        "platform": 0.0,
        "slippage": 0.0005,
    },
}

# ---- 因子默认权重（透明加权基线，Phase-1 用；方向 +1/-1）----
DEFAULT_WEIGHTS = {
    "mom_20":      {"w": 0.15, "dir": +1},
    "mom_60":      {"w": 0.20, "dir": +1},
    "mom_120":     {"w": 0.10, "dir": +1},
    "trend_ma20":  {"w": 0.15, "dir": +1},
    "vol_20":      {"w": 0.10, "dir": -1},   # 低波优先
    "dd_60":       {"w": 0.10, "dir": +1},   # 回撤小优先（dd 为负，dir +1 即越接近0越好）
    "sb_ratio_chg5": {"w": 0.10, "dir": -1}, # 南向增持=反向/风险（已实证）
    "sb_shares_g5":  {"w": 0.10, "dir": -1},
    "sb_ratio_lvl":  {"w": 0.00, "dir": +1}, # 水平无预测力，暂 0
}

MARKET = "HK"   # 本框架当前市场；US 预留同接口
