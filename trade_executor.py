"""模拟盘执行器 — 动态回撤减半止盈 + 分批买入 + GapSoft C 入场

买入（GapSoft C 臂）:
  - gap≤1.5%: 开盘/现价，权重 1.0
  - 1.5%<gap<3%: 限价=昨收×1.01，权重 0.7；未触及则挂单至收盘
  - 3%≤gap<5%: 限价=昨收×1.02，权重线性 0.5→0；未触及挂单
  - gap≥5% 或近涨停: 跳过
  - 日频建仓：默认一次买满计划仓（ENABLE_SCALE_IN=0）。若开启则首日 SCALE_IN_FRAC、
    次日确认补剩余（未涨停、相对昨收涨幅 <5%）。
  - 跌幅补仓：默认关闭（ENABLE_DIP_SCALE_IN=1 才开）。开启后仅补「计划剩余」
    （DIP_SCALE_MODE=planned_only，默认）；不再在已买满后等量加倍。
  - K 开仓时机（默认开）：禁开时段跳过；追高市价改限价等待

卖出（动态 peel）:
  - 浮盈 ≥3% → 仅激活跟踪（不卖）
  - 相对峰值回撤 ≥1.5% → 剩余仓位减半；须再创新高后，才允许下一次减半
  - 第三次回撤触发 / 移动止损 / 日频T+2 / 尾盘不按日强平(可关) / 超期 → 清仓
  - K 时间止损/划痕（默认关）：ENABLE_K_TIME_STOP=1 时，可卖后峰值浮盈<1% 且现价≤成本 → 主动离场
  - 仅连续竞价且 ≥09:31；集合竞价不更新峰值

选股：维持 A0（VM2.5+v3.1）；K 硬闸门默认关闭，不参与选股。
"""
import json
import os
import sys
from datetime import datetime

# Kelly 在线学习器（平仓记录，无状态时无害）
try:
    from kelly_learner import record_trade as _kelly_record_trade
except Exception:
    _kelly_record_trade = None

os.chdir("/home/ubuntu/alphapilot")
PT_PATH = "data/paper_trading.json"
REC_PATH = "output/daily_recommend.json"

STRATEGY_POOL = {"v19_daily": 0.50, "s2_eod": 0.50, "eod_sniper": 0.0}
# SHARED_CAPITAL=1（默认）：日频/尾盘共用账户现金，不再各锁约 50%
# SHARED_CAPITAL=0：恢复旧的策略资金池比例划分
MAX_PER_POSITION = 150000  # 日频单票上限（原 8 万，加仓后放大买卖比例）
# 尾盘策略单票可用上限（全仓一只）
MAX_PER_POSITION_EOD = 800000
EOD_STRATS = frozenset({"s2_eod", "eod_sniper"})
DEFAULT_INITIAL_CAPITAL = 1000000
LIMIT_FRAC = 0.97


def _shared_capital() -> bool:
    v = os.environ.get("SHARED_CAPITAL")
    if v is None:
        return True
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _pool_ratio(strat_id: str) -> float:
    """买入可用资金比例。共用模式下恒为 1.0。"""
    if _shared_capital():
        return 1.0
    return float(STRATEGY_POOL.get(strat_id, 0.50))

# 动态回撤减半
TRAIL_ARM = 0.03          # ≥3% 激活跟踪（不卖）
PEEL_PULLBACK = 0.015     # 回撤 1.5% 减半
PEEL_MAX_STEPS = 2        # 前两次减半，第三次清仓（共 3 刀）

# 分批买入（仅日频；尾盘全仓一次买完）
# ENABLE_SCALE_IN=0（默认）：日频一次买满，不再次日确认补仓
# ENABLE_SCALE_IN=1：首日 SCALE_IN_FRAC，次日确认补剩余
ENABLE_SCALE_IN = str(
    os.environ.get("ENABLE_SCALE_IN", "0")
).strip().lower() in ("1", "true", "yes", "on")
SCALE_IN_FRAC = float(os.environ.get("SCALE_IN_FRAC", "0.5") or 0.5)
SCALE_IN_MAX_GAP = 0.05       # 次日确认：涨幅≥5% 放弃补仓
SCALE_IN_DIP_PCT = float(os.environ.get("SCALE_IN_DIP_PCT", "0.05") or 0.05)
# 跌幅补仓：默认关。ENABLE_DIP_SCALE_IN=1 开启；DIP_SCALE_MODE=planned_only|equal_double
ENABLE_DIP_SCALE_IN = str(
    os.environ.get("ENABLE_DIP_SCALE_IN", "0")
).strip().lower() in ("1", "true", "yes", "on")
DIP_SCALE_MODE = str(os.environ.get("DIP_SCALE_MODE", "planned_only") or "planned_only").strip().lower()

# 日频入场：纯 GapSoft C（回测优选，不用 ML 择时）
ENTRY_MODE = "gap_soft"
GAP_OPEN_OK = 0.015
GAP_SOFT_LO = 0.03
GAP_HARD_SKIP = 0.05
LIMIT_PREMIUM = 0.01
LIMIT_PREMIUM_SOFT = 0.02
MID_WEIGHT = 0.70

T2_TRADING_DAYS = 1
T2_FORCE_AFTER_HHMM = (14, 45)

# 尾盘狙击（S2）：取消按交易日到期强平（原 T+3）；仍走硬止损 / peel
# EOD_FORCE_TRADING_DAYS<=0 或 DISABLE_EOD_TIME_FORCE=1 → 不按持有天数强平
EOD_FORCE_TRADING_DAYS = int(os.environ.get("EOD_FORCE_TRADING_DAYS", "0") or 0)
DISABLE_EOD_TIME_FORCE = str(
    os.environ.get("DISABLE_EOD_TIME_FORCE", "1")
).strip().lower() in ("1", "true", "yes", "on")

# E2：成本硬止损 -10%，仅收盘确认窗口触发（防开盘炸盘毛刺）
HARD_STOP_PCT = -0.10
# T+2 强平：资金净流入且未深亏时可延期 1 个交易日（仅一次）
T2_EXTEND_MIN_PRICE_RATIO = 0.95  # 现价 >= 成本 * 0.95
T2_EXTEND_FUND_LOOKBACK = 3       # 近 N 日主力净流入之和 > 0

STOP_LADDERS = [
    (0.00, -0.06),
    (0.03, 0.00),
    (0.06, 0.02),
    (0.10, 0.05),
    (0.15, 0.10),
]


def dynamic_stop(gain_pct):
    """旧动态阶梯（兼容展示）；可交易协议硬止损改用 HARD_STOP_PCT + 收盘确认。"""
    level = STOP_LADDERS[0][1]
    for threshold, stop in STOP_LADDERS:
        if gain_pct >= threshold:
            level = stop
        else:
            break
    return level


_FUND_HIST = None


def _load_fund_hist():
    global _FUND_HIST
    if _FUND_HIST is not None:
        return _FUND_HIST
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)) or ".", "data", "fund_flow_history.json")
    if not os.path.exists(path):
        path = "data/fund_flow_history.json"
    try:
        with open(path, encoding="utf-8") as f:
            _FUND_HIST = json.load(f)
    except Exception:
        _FUND_HIST = {}
    return _FUND_HIST


def stock_fund_inflow(sym, today=None, lookback=None):
    """近 lookback 日主力净流入合计 > 0 视为净流入。无数据返回 False。"""
    today = today or datetime.now().strftime("%Y-%m-%d")
    lookback = lookback if lookback is not None else T2_EXTEND_FUND_LOOKBACK
    hist = _load_fund_hist()
    bare = "".join(ch for ch in str(sym or "") if ch.isdigit())[-6:]
    series = hist.get(bare) or hist.get("sh" + bare) or hist.get("sz" + bare) or {}
    if not isinstance(series, dict) or not series:
        return False, 0.0
    if "data" in series and isinstance(series["data"], dict):
        series = series["data"]
    days = sorted([d for d in series.keys() if str(d)[:10] <= today], reverse=True)[:lookback]
    if not days:
        return False, 0.0
    total = 0.0
    for d in days:
        try:
            v = series[d]
            if isinstance(v, dict):
                total += float(v.get("main_net") or 0)
            else:
                total += float(v or 0)
        except Exception:
            pass
    return total > 0, total


def log(msg):
    t = datetime.now().strftime("%H:%M:%S")
    print("[{}] {}".format(t, msg))


def limit_pct(symbol):
    s = (symbol or "")[-6:]
    if s.startswith(("300", "301", "688")):
        return 0.20
    if s.startswith(("8", "4")):
        return 0.30
    return 0.10


def fetch_quote(sym):
    """返回 (last, prev_close, open_, high)；失败则全 None。"""
    import requests as _req

    prefix = "sh" if str(sym).startswith("6") else "sz"
    try:
        r = _req.get(
            "https://qt.gtimg.cn/q=" + prefix + sym,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=5,
        )
        vals = r.content.decode("gbk").split('"')[1].split("~")
        last = float(vals[3]) if len(vals) > 3 and vals[3] else 0.0
        prev = float(vals[4]) if len(vals) > 4 and vals[4] else 0.0
        open_ = float(vals[5]) if len(vals) > 5 and vals[5] else 0.0
        # 腾讯行情 ~33 为最高价
        high = float(vals[33]) if len(vals) > 33 and vals[33] else 0.0
        return last or None, prev or None, open_ or None, high or None
    except Exception:
        return None, None, None, None


def choose_fill(last, open_, signal_price=0.0, prefer_open=False):
    """成交价选择：盘中用现价；仅开盘窗口(09:25-09:34)或显式 prefer_open 用开盘价。

    旧逻辑 `open_ or last` 会在全天都用开盘价，尾盘买入会被记成开盘/甚至信号脏价。
    """
    now = datetime.now()
    hm = (now.hour, now.minute)
    use_open = prefer_open or ((9, 25) <= hm < (9, 35))
    if use_open:
        fill = open_ or last or (signal_price or None)
    else:
        fill = last or open_ or (signal_price or None)
    return float(fill) if fill else None


def soft_weight_3_to_5(gap):
    """gap∈[3%,5%) → 权重线性 0.50→0。"""
    if gap < GAP_SOFT_LO:
        return 1.0
    if gap >= GAP_HARD_SKIP:
        return 0.0
    return 0.5 * (GAP_HARD_SKIP - gap) / (GAP_HARD_SKIP - GAP_SOFT_LO)


def decide_gap_soft(prev, open_, last):
    """C 臂入场决策。

    返回:
      action: buy | pending | skip
      weight, limit, gap, reason
    """
    if not prev or prev <= 0:
        return {"action": "buy", "weight": 1.0, "limit": None, "gap": None, "reason": "no_prev"}
    ref_open = open_ if open_ and open_ > 0 else last
    if not ref_open or ref_open <= 0:
        return {"action": "skip", "weight": 0.0, "limit": None, "gap": None, "reason": "no_open"}
    gap = ref_open / prev - 1.0
    if gap >= GAP_HARD_SKIP:
        return {
            "action": "skip",
            "weight": 0.0,
            "limit": None,
            "gap": gap,
            "reason": "gap_ge_5pct",
        }
    if gap <= GAP_OPEN_OK:
        return {
            "action": "buy",
            "weight": 1.0,
            "limit": None,
            "gap": gap,
            "reason": "open_ok",
        }
    if gap < GAP_SOFT_LO:
        limit = round(prev * (1.0 + LIMIT_PREMIUM), 2)
        px = last if last and last > 0 else ref_open
        if px <= limit + 1e-9:
            return {
                "action": "buy",
                "weight": MID_WEIGHT,
                "limit": limit,
                "gap": gap,
                "reason": "mid_hit",
                "fill_cap": limit,
            }
        return {
            "action": "pending",
            "weight": MID_WEIGHT,
            "limit": limit,
            "gap": gap,
            "reason": "mid_wait",
        }
    # 3%–5%
    w = soft_weight_3_to_5(gap)
    if w <= 1e-12:
        return {
            "action": "skip",
            "weight": 0.0,
            "limit": None,
            "gap": gap,
            "reason": "soft_weight_zero",
        }
    limit = round(prev * (1.0 + LIMIT_PREMIUM_SOFT), 2)
    px = last if last and last > 0 else ref_open
    if px <= limit + 1e-9:
        return {
            "action": "buy",
            "weight": w,
            "limit": limit,
            "gap": gap,
            "reason": "soft_hit",
            "fill_cap": limit,
        }
    return {
        "action": "pending",
        "weight": w,
        "limit": limit,
        "gap": gap,
        "reason": "soft_wait",
    }


def is_open_limit(sym, last, prev_close, open_):
    if not prev_close or prev_close <= 0:
        return False
    lim = limit_pct(sym)
    ref = open_ if open_ and open_ > 0 else last
    if not ref or ref <= 0:
        return False
    gap = ref / prev_close - 1.0
    return gap >= lim * LIMIT_FRAC


def bump_trading_days(pos, today):
    last = pos.get("last_day_check") or ""
    if last == today:
        return int(pos.get("trading_days_held") or 0)
    held = int(pos.get("trading_days_held") or 0)
    buy_date = pos.get("buy_date") or ""
    if buy_date and buy_date < today:
        held += 1
    pos["trading_days_held"] = held
    pos["days_held"] = held
    pos["last_day_check"] = today
    return held


def load_exposure(pt):
    expo = pt.get("position_exposure")
    if expo is None and os.path.exists(REC_PATH):
        try:
            expo = json.load(open(REC_PATH, encoding="utf-8")).get("position_exposure", 1.0)
        except Exception:
            expo = 1.0
    try:
        return float(expo if expo is not None else 1.0)
    except Exception:
        return 1.0


def near_close(now=None):
    now = now or datetime.now()
    return (now.hour, now.minute) >= T2_FORCE_AFTER_HHMM


def in_continuous_session(now=None):
    now = now or datetime.now()
    hm = (now.hour, now.minute)
    if (9, 30) <= hm <= (11, 30):
        return True
    if (13, 0) <= hm <= (15, 0):
        return True
    return False


def calendar_stale_days(buy_date, today):
    if not buy_date:
        return 0
    try:
        return (
            datetime.strptime(today, "%Y-%m-%d")
            - datetime.strptime(buy_date[:10], "%Y-%m-%d")
        ).days
    except Exception:
        return 0


def round_lot(n):
    n = int(n or 0)
    return (n // 100) * 100


def ensure_pos_meta(p):
    """兼容旧仓：补齐动态 peel / 分批买入字段。"""
    qty = int(p.get("quantity") or 0)
    if not p.get("initial_quantity"):
        p["initial_quantity"] = qty
    if not p.get("planned_quantity"):
        p["planned_quantity"] = int(p.get("initial_quantity") or qty)
    if p.get("scale_in_pending") is None:
        p["scale_in_pending"] = False
    if p.get("scale_in_done") is None:
        p["scale_in_done"] = not p.get("scale_in_pending")
    if p.get("dip_scale_done") is None:
        p["dip_scale_done"] = False
    # 动态 peel 状态
    if p.get("trail_armed") is None:
        # 旧定额分批若已卖过，视为已激活
        p["trail_armed"] = bool(p.get("scale_out_lock") or p.get("scale_out_trail"))
    if p.get("peel_count") is None:
        n = 0
        if p.get("scale_out_lock"):
            n += 1
        if p.get("scale_out_trail"):
            n += 1
        p["peel_count"] = n
    if p.get("awaiting_new_high") is None:
        p["awaiting_new_high"] = bool(p.get("peel_count", 0) > 0)
    if p.get("peel_peak_snapshot") is None:
        p["peel_peak_snapshot"] = float(p.get("trailing_high") or p.get("buy_price") or 0)
    if p.get("t2_extended") is None:
        p["t2_extended"] = False
    return p


def half_sell_qty(rem):
    """剩余仓位减半（向下取整到手数）；不足 2 手则全清。"""
    rem = int(rem or 0)
    if rem <= 0:
        return 0
    if rem < 200:
        return rem
    half = round_lot(rem // 2)
    if half < 100:
        return rem
    if rem - half < 100:
        return rem
    return half


def append_sell(pt, pos, strat_id, action, price, qty, held_days, extra=None):
    cost = float(pos.get("buy_price") or 0)
    row = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "symbol": pos.get("symbol"),
        "name": pos.get("name"),
        "action": action,
        "price": round(price, 2),
        "quantity": qty,
        "amount": round(price * qty, 2),
        "strategy_id": strat_id,
        "pnl": round((price - cost) * qty, 2),
        "trading_days_held": held_days,
        "protocol": pos.get("protocol") or "tradable_top2",
        "scale_out": True,
        "qty_remaining": int(pos.get("quantity") or 0) - qty,
    }
    if extra:
        row.update(extra)
    pt["trade_log"].append(row)
    # 全仓清空 → 记录到 Kelly 在线学习器
    if _kelly_record_trade is not None and row["qty_remaining"] <= 0:
        try:
            _kelly_record_trade(pt, pos, row)
        except Exception:
            pass
    return row


def main():
    SELL_ONLY = "--sell-only" in sys.argv
    pt = json.load(open(PT_PATH, encoding="utf-8"))
    today = datetime.now().strftime("%Y-%m-%d")
    expo = load_exposure(pt)
    pt["position_exposure"] = expo
    can_t2_force = near_close()
    continuous = in_continuous_session()
    allow_intra = continuous and (datetime.now().hour, datetime.now().minute) >= (9, 31)

    # ===== 1. 卖出（动态 peel）=====
    log("=" * 60)
    log(
        "检查出场(E2硬止损{:.0f}%收盘确认 / peel激活{:.0f}% / T+2可资金延期)... (force_close={} continuous={} intra={})".format(
            abs(HARD_STOP_PCT) * 100,
            TRAIL_ARM * 100,
            can_t2_force,
            continuous,
            allow_intra,
        )
    )

    sold_lots = 0
    for s in pt.get("strategies", []):
        remaining = []
        for p in s.get("positions", []):
            p = ensure_pos_meta(p)
            sym = p.get("symbol", "")
            name = p.get("name", "")
            qty = int(p.get("quantity") or 0)
            cost = float(p.get("buy_price") or 0)
            if qty <= 0 or cost <= 0:
                continue

            last, prev, open_, _high = fetch_quote(sym)
            price = last if last else cost
            gain_pct = (price - cost) / cost if cost else 0.0
            pnl_pct = gain_pct * 100
            held_days = bump_trading_days(p, today)
            buy_date = (p.get("buy_date") or "")[:10]
            # A股 T+1：当日买入不可卖（止损/peel/T+2 一律禁止）
            can_sell = bool(buy_date and buy_date < today)
            if not can_sell:
                p["current_price"] = round(price, 2)
                p["pnl_pct"] = round(pnl_pct, 2)
                p["pnl_amount"] = round((price - cost) * qty, 2)
                if continuous and price > float(p.get("trailing_high") or cost):
                    p["trailing_high"] = price
                remaining.append(p)
                log(
                    "  {} {} T+0 冻结不可卖 (buy={} held={}d) 现价{:.2f} {:+.2f}%".format(
                        sym, name, buy_date or "?", held_days, price, pnl_pct
                    )
                )
                continue

            trailing_high = float(p.get("trailing_high") or cost)
            if continuous and price > trailing_high:
                trailing_high = price
                p["trailing_high"] = trailing_high
            pullback = (trailing_high - price) / trailing_high if trailing_high else 0.0

            # ≥3% 仅激活跟踪
            if gain_pct >= TRAIL_ARM or (trailing_high - cost) / cost >= TRAIL_ARM:
                p["trail_armed"] = True
            # 浮盈消失：退出 peel 模式，回到硬止损框架
            if gain_pct < 0:
                p["trail_armed"] = False
                p["awaiting_new_high"] = False

            # 减半后须再创新高，才允许下一刀
            if p.get("awaiting_new_high") and p.get("trail_armed"):
                snap = float(p.get("peel_peak_snapshot") or 0)
                if trailing_high > snap + 1e-9:
                    p["awaiting_new_high"] = False
                    log(
                        "  {} {} 创新高 {:.2f} > 上次峰值 {:.2f}，允许下一刀减半".format(
                            sym, name, trailing_high, snap
                        )
                    )

            use_t2 = (
                p.get("protocol") in ("tradable_top2", "eod_full")
                or s.get("id") in ("v19_daily", "s2_eod", "eod_sniper")
                or p.get("strategy_id") in ("v19_daily", "s2_eod", "eod_sniper")
            )
            is_eod_pos = (
                p.get("protocol") == "eod_full"
                or s.get("id") in EOD_STRATS
                or p.get("strategy_id") in EOD_STRATS
            )
            force_held_days = EOD_FORCE_TRADING_DAYS if is_eod_pos else T2_TRADING_DAYS
            force_label = "T+3" if is_eod_pos else "T+2"
            eod_skip_time_force = is_eod_pos and (
                DISABLE_EOD_TIME_FORCE or force_held_days <= 0
            )
            stale = calendar_stale_days(p.get("buy_date"), today)

            # 止损线：可交易协议用成本硬止损 -10%（E2 收盘确认）
            hard_stop_price = cost * (1.0 + HARD_STOP_PCT)
            p["stop_loss"] = round(hard_stop_price, 2)
            p["stop_pct"] = round(HARD_STOP_PCT * 100, 1)

            clear_action = None

            # 优先级 0a：板块资金反转紧急卖出（盘中板块巡检检出）
            if clear_action is None and allow_intra:
                try:
                    ALERT_PATH = "output/sector_watch_alerts.json"
                    if os.path.exists(ALERT_PATH):
                        alerts_data = json.load(open(ALERT_PATH, encoding="utf-8"))
                        for alert in (alerts_data.get("alerts") or []):
                            if (
                                alert.get("symbol") == sym
                                and alert.get("action") == "force_sell"
                            ):
                                severity_pct = {
                                    "high": 0,    # 立即市价卖
                                    "medium": -0.01,  # 可容忍 -1%
                                }.get(alert.get("severity", "medium"), -0.01)
                                # 高严重度或已达容忍亏损 → 强卖
                                if severity_pct == 0 or price <= cost * (1 + severity_pct):
                                    clear_action = "卖出(板块资金反转:" + alert.get("sector", "?") + ")"
                                    log(f"  🚨 板块反转紧急卖出: {sym} {name} "
                                        f"板块={alert.get('sector')} "
                                        f"原因={alert.get('reason')[:80]}")
                                break
                except Exception as e:
                    log(f"  sector_watch alerts skip: {e}")

            # 优先级 1：硬止损 · 仅收盘确认窗口（14:45 后）且现价仍≤止损
            if (
                use_t2
                and can_t2_force
                and allow_intra
                and price <= hard_stop_price + 1e-9
            ):
                clear_action = "卖出(硬止损·收盘确认)"
            # 优先级 1b：K 时间止损/划痕（默认关；ENABLE_K_TIME_STOP=1 才启用）
            elif allow_intra:
                try:
                    from k_execution import time_stop_triggered

                    hit, act = time_stop_triggered(
                        p,
                        price=price,
                        cost=cost,
                        held_days=held_days,
                        can_sell=can_sell,
                    )
                    if hit:
                        clear_action = act
                except Exception as e:
                    log("  k time_stop skip: {}".format(e))
            # 优先级 2：到期强平（日频 T+2；尾盘默认关闭按日强平）
            if (
                clear_action is None
                and use_t2
                and can_t2_force
                and (not eod_skip_time_force)
                and (
                    held_days >= force_held_days or stale >= (force_held_days + 1)
                )
            ):
                already_ext = bool(p.get("t2_extended"))
                need_held = force_held_days + (1 if already_ext else 0)
                force_label = "T+3" if is_eod_pos else "T+2"
                if already_ext:
                    if held_days >= need_held or stale >= (force_held_days + 2):
                        clear_action = "卖出(延期后强平)"
                else:
                    # 首次到期：资金净流入且未深亏 → 延期
                    fund_ok, fund_sum = stock_fund_inflow(sym, today)
                    price_ok = price >= cost * T2_EXTEND_MIN_PRICE_RATIO
                    if fund_ok and price_ok and held_days >= force_held_days:
                        p["t2_extended"] = True
                        p["t2_extend_date"] = today
                        p["t2_extend_fund"] = round(fund_sum, 2)
                        log(
                            "  {} {} {}延期1日 (资金近{}日净流入{:.0f} 现价{:.2f} 成本{:.2f})".format(
                                sym,
                                name,
                                force_label,
                                T2_EXTEND_FUND_LOOKBACK,
                                fund_sum,
                                price,
                                cost,
                            )
                        )
                    else:
                        clear_action = "卖出({}收盘)".format(force_label)
                        if not fund_ok:
                            p["t2_no_extend_reason"] = "no_fund_inflow"
                        elif not price_ok:
                            p["t2_no_extend_reason"] = "deep_loss"
            # 尾盘取消按日强平后，仍保留很长日历超期兜底（防僵尸仓）；日频不变
            stale_cap = 30 if is_eod_pos else 5
            if clear_action is None and can_t2_force and stale >= stale_cap:
                clear_action = "卖出(超期清理)"

            if clear_action:
                log(
                    "{} {} {}: 成本{:.2f} 现价{:.2f} {:.2f}% qty={} held={}d".format(
                        clear_action, sym, name, cost, price, pnl_pct, qty, held_days
                    )
                )
                extra = {"peak": round(trailing_high, 2), "pullback": round(pullback * 100, 2)}
                if "止损" in clear_action:
                    extra["stop_pct"] = round(HARD_STOP_PCT * 100, 1)
                    extra["stop_mode"] = "e2_close_confirm"
                if "延期" in clear_action or p.get("t2_extended"):
                    extra["t2_extended"] = bool(p.get("t2_extended"))
                append_sell(pt, p, s.get("id"), clear_action, price, qty, held_days, extra)
                sold_lots += 1
                continue

            # —— 动态减半（仅盘中、仅浮盈）——
            did_partial = False
            if (
                allow_intra
                and gain_pct > 0
                and p.get("trail_armed")
                and (not p.get("awaiting_new_high"))
                and pullback >= PEEL_PULLBACK
            ):
                peel_n = int(p.get("peel_count") or 0)
                # 第 3 刀（peel_count 已达 2）或剩余不足 2 手 → 清仓
                if peel_n >= PEEL_MAX_STEPS:
                    sq = qty
                    action = "卖出(动态止盈·清仓)"
                else:
                    sq = half_sell_qty(qty)
                    action = "卖出(动态止盈·减半{})".format(peel_n + 1)

                if sq > 0:
                    log(
                        "{} {} {}: 峰值{:.2f} 回撤{:.2f}% 卖{}股 剩{}".format(
                            action,
                            sym,
                            name,
                            trailing_high,
                            pullback * 100,
                            sq,
                            qty - sq,
                        )
                    )
                    append_sell(
                        pt,
                        p,
                        s.get("id"),
                        action,
                        price,
                        sq,
                        held_days,
                        {
                            "peak": round(trailing_high, 2),
                            "pullback": round(pullback * 100, 2),
                            "peel_step": peel_n + 1,
                        },
                    )
                    p["quantity"] = qty - sq
                    qty = p["quantity"]
                    p["peel_count"] = peel_n + 1
                    sold_lots += 1
                    did_partial = True
                    if qty > 0:
                        p["awaiting_new_high"] = True
                        p["peel_peak_snapshot"] = trailing_high
                    else:
                        continue

            if qty <= 0:
                continue

            p["current_price"] = round(price, 2)
            p["pnl_pct"] = round(pnl_pct, 2)
            p["pnl_amount"] = round((price - cost) * qty, 2)
            remaining.append(p)
            if did_partial:
                log("  {} {} 减半后仍持仓 {} 股".format(sym, name, qty))

        s["positions"] = remaining

    if sold_lots > 0:
        log("共卖出 {} 笔（含动态减半）".format(sold_lots))

    # ===== 2. 买入 / 补仓 / 限价挂单 =====
    # --sell-only 仍处理：限价成交、跌幅补仓、次日补仓；只跳过「新开仓信号」
    log("\n检查买入/补仓... expo={:.2f} sell_only={}".format(expo, SELL_ONLY))
    total_cash = pt["account"].get("cash", 0)
    held_symbols = {
        p.get("symbol", "")
        for st in pt["strategies"]
        for p in st.get("positions", [])
    }
    traded_today = {
        t.get("symbol", "")
        for t in pt.get("trade_log", [])
        if t.get("action")
        in ("买入", "买入(首批50%)", "买入(补仓50%)", "买入(补仓跌幅)")
        and str(t.get("time", "")).startswith(today)
    }
    # 当日已做过跌幅补仓的标的（避免重复加仓）
    dip_scaled_today = {
        t.get("symbol", "")
        for t in pt.get("trade_log", [])
        if t.get("action") == "买入(补仓跌幅)" and str(t.get("time", "")).startswith(today)
    }
    executed = 0
    pending = list(pt.get("pending_limits") or [])
    still_pending = []

    if expo <= 0:
        log("  position_exposure=0, 跳过新开仓（补仓/挂单仍可能处理）")
        for s in pt.get("strategies", []):
            if s.get("id") == "v19_daily":
                s["signals"] = []

    def _place_buy(strat_id, sym, name, fill, weight, gap, entry_reason, alloc_budget, full_position=False, *, entry_score_pct=None, entry_vol=None):
        """按权重建仓；alloc_budget 已是该票可用预算。尾盘 full_position=True 一次买满。"""
        nonlocal executed
        w = float(max(0.0, min(1.0, weight or 1.0)))
        if w <= 0 or not fill or fill <= 0:
            return False, 0.0
        is_eod = strat_id in EOD_STRATS or full_position
        max_cap = MAX_PER_POSITION_EOD if is_eod else MAX_PER_POSITION
        alloc_full = min(float(alloc_budget), max_cap) * w
        planned_qty = round_lot(alloc_full / fill)
        if is_eod or not ENABLE_SCALE_IN:
            # 尾盘，或日频关闭分批：一次买满
            first_qty = planned_qty
            scale_pending = False
        else:
            first_qty = round_lot(planned_qty * SCALE_IN_FRAC)
            if planned_qty < 200:
                first_qty = planned_qty
                scale_pending = False
            else:
                if first_qty < 100:
                    first_qty = 100
                scale_pending = first_qty < planned_qty
        if first_qty < 100:
            log("  跳过 {} {}: 金额不足1手 (w={:.2f})".format(sym, name, w))
            return False, 0.0
        cash_now = float(pt["account"].get("cash", 0))
        actual_cost = first_qty * fill
        if actual_cost > cash_now + 1:
            # 现金不够则缩量到可买手数
            afford = round_lot(cash_now / fill)
            if afford < 100:
                log("  跳过 {} {}: 现金不足".format(sym, name))
                return False, 0.0
            first_qty = afford
            planned_qty = afford
            scale_pending = False
            actual_cost = first_qty * fill
        log(
            "  成交 {} {} x{}股/计划{} = {:.0f} @ {:.2f} [w={:.0%} {} gap={} {}]".format(
                sym,
                name,
                first_qty,
                planned_qty,
                actual_cost,
                fill,
                w,
                entry_reason,
                "{:.2%}".format(gap) if gap is not None else "?",
                "EOD全仓" if is_eod else "日频分批",
            )
        )
        pt["trade_log"].append(
            {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "symbol": sym,
                "name": name,
                "action": (
                    "买入(尾盘全仓)"
                    if is_eod
                    else ("买入(首批50%)" if scale_pending else "买入")
                ),
                "price": round(fill, 2),
                "quantity": first_qty,
                "amount": round(actual_cost, 2),
                "strategy_id": strat_id,
                "position_exposure": expo,
                "protocol": "eod_full" if is_eod else "gap_soft",
                "planned_quantity": planned_qty,
                "entry_weight": round(w, 4),
                "entry_gap": round(gap, 4) if gap is not None else None,
                "entry_reason": entry_reason,
            }
        )
        init_stop = STOP_LADDERS[0][1]
        pos = {
            "symbol": sym,
            "name": name,
            "entry_price": round(fill, 2),
            "buy_price": round(fill, 2),
            "current_price": round(fill, 2),
            "quantity": first_qty,
            "planned_quantity": planned_qty,
            "initial_quantity": first_qty,
            "pnl_pct": 0,
            "pnl_amount": 0,
            "stop_loss": round(fill * (1 + init_stop), 2),
            "stop_pct": round(init_stop * 100, 1),
            "trailing_high": round(fill, 2),
            "days_held": 0,
            "trading_days_held": 0,
            "last_day_check": today,
            "strategy_id": strat_id,
            "buy_date": today,
            "protocol": "eod_full" if is_eod else "tradable_top2",
            "entry_mode": "eod_full" if is_eod else ENTRY_MODE,
            "entry_weight": round(w, 4),
            "position_exposure": expo,
            "entry_score_pct": entry_score_pct,
            "entry_vol": entry_vol,
            "scale_in_pending": scale_pending,
            "scale_in_done": not scale_pending,
            "trail_armed": False,
            "peel_count": 0,
            "awaiting_new_high": False,
            "peel_peak_snapshot": round(fill, 2),
        }
        for st in pt["strategies"]:
            if st["id"] == strat_id:
                st.setdefault("positions", []).append(pos)
                st["used"] = float(st.get("used", 0)) + actual_cost
                break
        held_symbols.add(sym)
        traded_today.add(sym)
        # 即时扣现金，避免同轮超买
        pt["account"]["cash"] = cash_now - actual_cost
        executed += 1
        return True, actual_cost

    def _mark_ticket_filled(ticket_id, fill, qty):
        if not ticket_id:
            return
        try:
            from order_tickets import mark_ticket_status

            mark_ticket_status(
                ticket_id,
                "filled",
                user_id="owner",
                extra={"fill_price": fill, "fill_qty": qty, "exec_channel": "paper"},
            )
        except Exception as e:
            log("  ticket fill mark skip: {}".format(e))

    # —— 2a0. 处理挂单限价（当日有效）——
    for od in pending:
        expire = (od.get("expire_date") or "")[:10]
        if expire and expire < today:
            log(
                "  限价过期撤单 {} {} @{}".format(
                    od.get("symbol"), od.get("name"), od.get("limit")
                )
            )
            pt["trade_log"].append(
                {
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "symbol": od.get("symbol"),
                    "name": od.get("name"),
                    "action": "撤单(限价过期)",
                    "price": od.get("limit"),
                    "quantity": 0,
                    "amount": 0,
                    "strategy_id": od.get("strategy_id"),
                    "skip": "limit_expire",
                }
            )
            continue
        if expire and expire > today:
            still_pending.append(od)
            continue
        sym = od.get("symbol", "")
        name = od.get("name", "")
        limit = float(od.get("limit") or 0)
        if sym in held_symbols or sym in traded_today:
            continue
        last, prev, open_, _h = fetch_quote(sym)
        px = last or open_
        if not px or limit <= 0:
            still_pending.append(od)
            continue
        if px > limit + 1e-9:
            if near_close():
                log("  限价未触及撤单 {} {} last={} limit={}".format(sym, name, px, limit))
                pt["trade_log"].append(
                    {
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "symbol": sym,
                        "name": name,
                        "action": "撤单(限价未触及)",
                        "price": px,
                        "quantity": 0,
                        "amount": 0,
                        "strategy_id": od.get("strategy_id"),
                        "skip": "limit_miss",
                        "limit": limit,
                    }
                )
                continue
            still_pending.append(od)
            continue
        fill = min(float(px), limit)
        strat_id = od.get("strategy_id") or "v19_daily"
        pool_ratio = _pool_ratio(strat_id)
        budget = min(
            float(pt["account"].get("cash", total_cash)) * pool_ratio * expo,
            MAX_PER_POSITION,
        )
        _place_buy(
            strat_id,
            sym,
            name,
            fill,
            float(od.get("weight") or MID_WEIGHT),
            od.get("gap"),
            od.get("reason") or "pending_fill",
            budget,
            entry_score_pct=od.get("entry_score_pct"),
            entry_vol=od.get("entry_vol"),
        )

    pt["pending_limits"] = still_pending

    def _apply_scale_in(s, p, fill, need, action, extra=None):
        """执行补仓成交并记账。返回 True 表示成交。"""
        nonlocal executed
        sym = p.get("symbol", "")
        name = p.get("name", "")
        cur = int(p.get("quantity") or 0)
        actual_cost = need * fill
        if actual_cost > float(pt["account"].get("cash", 0)) + 1:
            log("  补仓跳过 {} {}: 现金不足".format(sym, name))
            return False
        old_cost = float(p.get("buy_price") or 0)
        new_cost = (old_cost * cur + fill * need) / (cur + need) if (cur + need) else fill
        p["quantity"] = cur + need
        p["buy_price"] = round(new_cost, 4)
        p["entry_price"] = p["buy_price"]
        p["initial_quantity"] = cur + need
        p["planned_quantity"] = max(int(p.get("planned_quantity") or 0), cur + need)
        if not p.get("scale_out_lock") and not p.get("scale_out_trail"):
            p["scale_out_base"] = cur + need
        p["current_price"] = round(fill, 2)
        p["scale_in_pending"] = False
        p["scale_in_done"] = True
        if action == "买入(补仓跌幅)":
            p["dip_scale_done"] = True
        p["trailing_high"] = max(float(p.get("trailing_high") or 0), fill)
        # 即时扣减现金，避免同轮多次补仓超支
        pt["account"]["cash"] = float(pt["account"].get("cash", 0)) - actual_cost
        log(
            "  补仓 {} {} x{}股 = {:.0f} @ {:.2f} 均价{:.2f} [{}]".format(
                sym, name, need, actual_cost, fill, p["buy_price"], action
            )
        )
        row = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "symbol": sym,
            "name": name,
            "action": action,
            "price": round(fill, 2),
            "quantity": need,
            "amount": round(actual_cost, 2),
            "strategy_id": s.get("id"),
            "position_exposure": expo,
            "protocol": p.get("protocol") or "tradable_top2",
            "avg_cost": p["buy_price"],
        }
        if extra:
            row.update(extra)
        pt["trade_log"].append(row)
        for st in pt["strategies"]:
            if st["id"] == s.get("id"):
                st["used"] = float(st.get("used", 0)) + actual_cost
                break
        traded_today.add(sym)
        executed += 1
        return True

    # —— 2a0.5 当日跌幅补仓（默认关；--sell-only 也会跑，故必须默认关）——
    if not ENABLE_DIP_SCALE_IN:
        log("  跌幅补仓关闭 (ENABLE_DIP_SCALE_IN=0)")
    else:
        log(
            "  跌幅补仓开启 mode={} thr={:.0%}".format(
                DIP_SCALE_MODE, SCALE_IN_DIP_PCT
            )
        )
    for s in pt.get("strategies", []):
        if not ENABLE_DIP_SCALE_IN:
            break
        if s.get("id") in EOD_STRATS:
            continue  # 尾盘全仓，无分批补仓
        for p in s.get("positions", []):
            p = ensure_pos_meta(p)
            if p.get("protocol") == "eod_full" or p.get("entry_mode") == "eod_full":
                continue
            sym = p.get("symbol", "")
            name = p.get("name", "")
            if sym in dip_scaled_today or p.get("dip_scale_done"):
                continue

            last, prev, open_, _high = fetch_quote(sym)
            fill = choose_fill(last, open_, prefer_open=False)
            if not fill or fill <= 0:
                continue
            if is_open_limit(sym, last, prev, open_):
                continue

            day_chg = (fill / prev - 1.0) if prev and prev > 0 else None
            cost = float(p.get("buy_price") or 0)
            cost_chg = (fill / cost - 1.0) if cost > 0 else None
            day_dip = day_chg is not None and day_chg <= -SCALE_IN_DIP_PCT
            cost_dip = cost_chg is not None and cost_chg <= -SCALE_IN_DIP_PCT
            if not day_dip and not cost_dip:
                continue

            planned = int(p.get("planned_quantity") or p.get("initial_quantity") or 0)
            cur = int(p.get("quantity") or 0)
            # planned_only（默认）：只补计划剩余；已买满则不加。
            # equal_double（旧行为）：已买满再补与当前持仓等量。
            if p.get("scale_in_pending") and not p.get("scale_in_done"):
                need = round_lot(planned - cur)
            elif DIP_SCALE_MODE in ("equal_double", "double", "legacy"):
                need = round_lot(cur)
            else:
                continue  # planned_only 且无计划剩余 → 跳过
            if need < 100:
                continue
            # 单票总名义不超过 2×MAX，避免无限加仓
            room_qty = round_lot(
                max(0, (2 * MAX_PER_POSITION - cur * fill) / fill)
            )
            if room_qty < 100:
                log(
                    "  补仓跳过 {} {}: 已近仓位上限 (mv≈{:.0f})".format(
                        sym, name, cur * fill
                    )
                )
                continue
            need = min(need, room_qty)

            ok = _apply_scale_in(
                s,
                p,
                fill,
                need,
                "买入(补仓跌幅)",
                extra={
                    "day_chg": round(day_chg, 4) if day_chg is not None else None,
                    "cost_chg": round(cost_chg, 4) if cost_chg is not None else None,
                    "dip_trigger": "vs_prev" if day_dip else "vs_cost",
                    "dip_mode": DIP_SCALE_MODE,
                },
            )
            if ok:
                dip_scaled_today.add(sym)

    # —— 2a. 次日确认补仓 ——
    if not ENABLE_SCALE_IN:
        log("  次日确认补仓关闭 (ENABLE_SCALE_IN=0，日频一次买满)")
        # 清理历史半仓挂起标记，避免状态残留
        for s in pt.get("strategies", []):
            for p in s.get("positions", []):
                if p.get("scale_in_pending"):
                    p["scale_in_pending"] = False
                    p["scale_in_done"] = True
                    log(
                        "  取消待补仓标记 {} {}（保留当前持仓，不再加仓）".format(
                            p.get("symbol"), p.get("name")
                        )
                    )
    for s in pt.get("strategies", []):
        if not ENABLE_SCALE_IN:
            break
        if s.get("id") in EOD_STRATS:
            continue
        for p in s.get("positions", []):
            p = ensure_pos_meta(p)
            if p.get("protocol") == "eod_full" or p.get("entry_mode") == "eod_full":
                continue
            if not p.get("scale_in_pending") or p.get("scale_in_done"):
                continue
            buy_date = (p.get("buy_date") or "")[:10]
            if not buy_date or buy_date >= today:
                continue  # 当日不走次日确认（跌幅补仓已在上面处理）

            sym = p.get("symbol", "")
            name = p.get("name", "")
            planned = int(p.get("planned_quantity") or p.get("initial_quantity") or 0)
            cur = int(p.get("quantity") or 0)
            need = round_lot(planned - cur)
            if need < 100:
                p["scale_in_pending"] = False
                p["scale_in_done"] = True
                continue

            last, prev, open_, _high = fetch_quote(sym)
            fill = choose_fill(last, open_, prefer_open=True)  # 次日开盘补仓
            if not fill or fill <= 0:
                log("  补仓跳过 {} {}: 无报价".format(sym, name))
                continue
            if is_open_limit(sym, last, prev, open_):
                log("  补仓跳过 {} {}: 涨停/近涨停 → 放弃补仓".format(sym, name))
                p["scale_in_pending"] = False
                p["scale_in_done"] = True  # 不再补
                pt["trade_log"].append(
                    {
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "symbol": sym,
                        "name": name,
                        "action": "跳过(补仓涨停)",
                        "price": fill,
                        "quantity": 0,
                        "amount": 0,
                        "strategy_id": s.get("id"),
                        "skip": "scale_in_limit",
                    }
                )
                continue
            if prev and prev > 0:
                gap = fill / prev - 1.0
                if gap >= SCALE_IN_MAX_GAP:
                    log(
                        "  补仓跳过 {} {}: 涨幅{:.1f}%≥{:.0f}% → 放弃补仓".format(
                            sym, name, gap * 100, SCALE_IN_MAX_GAP * 100
                        )
                    )
                    p["scale_in_pending"] = False
                    p["scale_in_done"] = True
                    continue

            _apply_scale_in(s, p, fill, need, "买入(补仓50%)")

    # —— 2b. 新信号买入（--sell-only 跳过）——
    if not SELL_ONLY:
        # 同步策略资金额度展示
        _equity = float(pt["account"].get("cash", 0)) + float(pt["account"].get("market_value", 0))
        if _equity <= 0:
            _equity = float(pt.get("initial_capital") or DEFAULT_INITIAL_CAPITAL)
        _shared = _shared_capital()
        for _st in pt.get("strategies", []):
            _rid = _st.get("id")
            if _shared:
                # 通用资金池：各策略展示总额，实际买入看账户现金
                _st["allocated"] = round(_equity, 2)
                _st["capital_mode"] = "shared"
            elif _rid in STRATEGY_POOL:
                _st["allocated"] = round(_equity * float(STRATEGY_POOL[_rid]), 2)
                _st["capital_mode"] = "split"

        for s in pt.get("strategies", []):
            buy_sigs = [sig for sig in s.get("signals", []) if sig.get("action") == "buy"]
            if not buy_sigs:
                continue

            strat_id = s.get("id", "default")
            pool_ratio = _pool_ratio(strat_id)
            is_eod = strat_id in EOD_STRATS
            cash_now = float(pt["account"].get("cash", total_cash))
            if is_eod:
                # 尾盘：用账户可用现金全仓买 Top1（单票仍受 MAX_PER_POSITION_EOD 限制）
                pool_cash = cash_now * pool_ratio
                entry_label = "eod_full"
                first_pct = 100.0
            else:
                pool_cash = cash_now * pool_ratio * expo
                entry_label = ENTRY_MODE
                first_pct = SCALE_IN_FRAC * 100
            n = len(buy_sigs)
            log(
                "  [{}] {}可用¥{:.0f}{} | {} 只 | 入场={} 仓位{:.0f}%".format(
                    strat_id,
                    "共用资金" if _shared else "资金池{:.0f}%".format(pool_ratio * 100),
                    pool_cash,
                    "" if is_eod else "×expo{:.0f}%".format(expo * 100),
                    n,
                    entry_label,
                    first_pct,
                )
            )

            for sig in buy_sigs:
                sym = sig.get("symbol", "")
                name = sig.get("name", "")
                signal_price = float(sig.get("price", 0) or 0)
                if not sym or signal_price <= 0:
                    continue
                if sym in held_symbols:
                    log("  跳过 {} {}: 已有持仓".format(sym, name))
                    continue
                if sym in traded_today:
                    log("  跳过 {} {}: 今日已买入".format(sym, name))
                    continue
                # 已有同日挂单则不再重复挂（日频）
                if not is_eod and any(
                    p.get("symbol") == sym and (p.get("expire_date") or "")[:10] == today
                    for p in (pt.get("pending_limits") or [])
                ):
                    log("  跳过 {} {}: 已有限价挂单".format(sym, name))
                    s["signals"] = [x for x in s.get("signals", []) if x.get("symbol") != sym]
                    continue

                last, prev, open_, high = fetch_quote(sym)
                if is_open_limit(sym, last, prev, open_):
                    log("  跳过 {} {}: 开盘涨停/近涨停".format(sym, name))
                    pt["trade_log"].append(
                        {
                            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "symbol": sym,
                            "name": name,
                            "action": "跳过(开盘涨停)",
                            "price": open_ or last or signal_price,
                            "quantity": 0,
                            "amount": 0,
                            "strategy_id": strat_id,
                            "skip": "open_limit",
                            "prev_close": prev,
                            "open": open_,
                            "last": last,
                            "high": high,
                        }
                    )
                    s["signals"] = [x for x in s.get("signals", []) if x.get("symbol") != sym]
                    continue

                # 分时资金确认：执行前再验盘中资金面（仓位缩放 / 过弱跳过）
                fund_w = 1.0
                try:
                    from trade_precheck import intraday_fund_confirm

                    chg_pct = None
                    if last and prev and prev > 0:
                        chg_pct = (float(last) / float(prev) - 1.0) * 100.0
                    confirm = intraday_fund_confirm(
                        sym,
                        quote={
                            "last": last,
                            "prev_close": prev,
                            "open": open_,
                            "change_pct": chg_pct,
                        },
                    )
                    fund_w = float(confirm.get("weight") or 1.0)
                    if not confirm.get("pass"):
                        log(
                            "  跳过 {} {}: 分时资金确认失败 w={:.2f} {}".format(
                                sym,
                                name,
                                fund_w,
                                ";".join(confirm.get("reasons") or [])[:80],
                            )
                        )
                        pt["trade_log"].append(
                            {
                                "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                "symbol": sym,
                                "name": name,
                                "action": "跳过(分时资金确认)",
                                "price": open_ or last or signal_price,
                                "quantity": 0,
                                "amount": 0,
                                "strategy_id": strat_id,
                                "skip": "intraday_fund_confirm",
                                "fund_confirm": confirm,
                            }
                        )
                        s["signals"] = [
                            x for x in s.get("signals", []) if x.get("symbol") != sym
                        ]
                        continue
                    if fund_w < 0.99:
                        log(
                            "  分时降权 {} {} w={:.2f} {}".format(
                                sym,
                                name,
                                fund_w,
                                ";".join(confirm.get("reasons") or [])[:60],
                            )
                        )
                except Exception as e:
                    log("  分时资金确认跳过(异常放行): {}".format(e))
                    fund_w = 1.0

                # 尾盘：现价全仓，不做早盘 GapSoft
                if is_eod:
                    fill = choose_fill(last, open_, signal_price, prefer_open=False)
                    if not fill or fill <= 0:
                        log("  跳过 {} {}: 无有效成交价".format(sym, name))
                        continue
                    budget = min(pool_cash / max(n, 1), MAX_PER_POSITION_EOD)
                    ok, cost = _place_buy(
                    strat_id,
                    sym,
                    name,
                    fill,
                    fund_w,
                    None,
                    "eod_full_cash",
                    budget,
                    full_position=True,
                    entry_score_pct=sig.get("entry_score_pct"),
                    entry_vol=sig.get("entry_vol"),
                )
                if ok:
                    _mark_ticket_filled(sig.get("ticket_id"), fill, None)
                    s["signals"] = [x for x in s.get("signals", []) if x.get("symbol") != sym]
                    pool_cash -= cost
                    continue

                decision = decide_gap_soft(prev, open_, last)
                try:
                    from k_execution import apply_entry_timing

                    decision = apply_entry_timing(decision, gap=decision.get("gap"))
                    # 追高改挂单但缺 limit 时，补昨收×1.01
                    if (
                        decision.get("action") == "pending"
                        and not decision.get("limit")
                        and prev
                        and prev > 0
                    ):
                        decision["limit"] = round(float(prev) * (1.0 + LIMIT_PREMIUM), 2)
                        decision["weight"] = decision.get("weight") or MID_WEIGHT
                except Exception as e:
                    log("  k entry_timing skip: {}".format(e))
                gap = decision.get("gap")
                if decision["action"] == "skip":
                    log(
                        "  跳过 {} {}: {} gap={}".format(
                            sym,
                            name,
                            decision.get("reason"),
                            "{:.2%}".format(gap) if gap is not None else "?",
                        )
                    )
                    pt["trade_log"].append(
                        {
                            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "symbol": sym,
                            "name": name,
                            "action": "跳过(开盘追高)",
                            "price": open_ or last or signal_price,
                            "quantity": 0,
                            "amount": 0,
                            "strategy_id": strat_id,
                            "skip": decision.get("reason"),
                            "open_gap": gap,
                        }
                    )
                    s["signals"] = [x for x in s.get("signals", []) if x.get("symbol") != sym]
                    continue

                if decision["action"] == "pending":
                    # 初始 weight = decision weight × fund_confirm
                    base_w = float(decision["weight"] or 1.0) * fund_w
                    # 若 signal 带有 Kelly entry_weight，用它覆盖 base_w
                    sig_entry_w = sig.get("entry_weight")
                    if sig_entry_w is not None:
                        try:
                            base_w = float(sig_entry_w) * fund_w
                        except (TypeError, ValueError):
                            pass
                    pend_w = base_w
                    od = {
                        "symbol": sym,
                        "name": name,
                        "limit": decision["limit"],
                        "weight": pend_w,
                        "gap": gap,
                        "reason": decision.get("reason"),
                        "strategy_id": strat_id,
                        "expire_date": today,
                        "signal_price": signal_price,
                        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "fund_confirm_weight": fund_w,
                        "entry_weight": round(base_w, 4),
                        "entry_score_pct": sig.get("entry_score_pct"),
                        "entry_vol": sig.get("entry_vol"),
                    }
                    pt.setdefault("pending_limits", []).append(od)
                    log(
                        "  挂限价 {} {} @{} w={:.0%} gap={} ({})".format(
                            sym,
                            name,
                            decision["limit"],
                            pend_w,
                            "{:.2%}".format(gap) if gap is not None else "?",
                            decision.get("reason"),
                        )
                    )
                    pt["trade_log"].append(
                        {
                            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "symbol": sym,
                            "name": name,
                            "action": "挂单(限价回踩)",
                            "price": decision["limit"],
                            "quantity": 0,
                            "amount": 0,
                            "strategy_id": strat_id,
                            "entry_weight": pend_w,
                            "open_gap": gap,
                            "limit": decision["limit"],
                        }
                    )
                    s["signals"] = [x for x in s.get("signals", []) if x.get("symbol") != sym]
                    continue

                # action == buy（日频）
                fill = choose_fill(last, open_, signal_price)
                if decision.get("fill_cap") and fill:
                    fill = min(fill, float(decision["fill_cap"]))
                if not fill or fill <= 0:
                    log("  跳过 {} {}: 无有效成交价".format(sym, name))
                    continue
                budget = min(pool_cash / max(n, 1), MAX_PER_POSITION)
                entry_w = float(decision.get("weight", 1.0) or 1.0) * fund_w
                # 人工确认单可带 entry_weight
                if sig.get("entry_weight") is not None:
                    try:
                        entry_w = float(sig.get("entry_weight") or 1.0) * fund_w
                    except (TypeError, ValueError):
                        pass
                ok, cost = _place_buy(
                    strat_id,
                    sym,
                    name,
                    fill,
                    entry_w,
                    gap,
                    decision.get("reason") or "buy",
                    budget,
                    full_position=False,
                    entry_score_pct=sig.get("entry_score_pct"),
                    entry_vol=sig.get("entry_vol"),
                )
                if ok:
                    _mark_ticket_filled(sig.get("ticket_id"), fill, None)
                    s["signals"] = [x for x in s.get("signals", []) if x.get("symbol") != sym]
                    pool_cash -= cost
    else:
        log("  --sell-only: 跳过新开仓，已处理挂单/跌幅补仓/次日补仓")

    log("成交完成: {} 笔（含补仓） | 挂单中 {}".format(executed, len(pt.get("pending_limits") or [])))

    # ===== 3. 更新账户 =====
    pos_list = [p for st in pt["strategies"] for p in st.get("positions", [])]
    INITIAL = float(pt.get("initial_capital") or DEFAULT_INITIAL_CAPITAL)
    total_bought = total_sold = settled_pnl = 0
    for t in pt.get("trade_log", []):
        a = t.get("action", "")
        amt = float(t.get("amount", 0) or 0)
        pn = float(t.get("pnl", 0) or 0)
        if a.startswith("买入") or a == "买入":
            total_bought += amt
        elif "卖出" in a:
            total_sold += amt
            settled_pnl += pn

    total_cost = sum(
        p.get("quantity", 0) * p.get("buy_price", 0) for p in pos_list
    )
    total_mv = sum(
        p.get("quantity", 0) * (p.get("current_price", 0) or p.get("buy_price", 0))
        for p in pos_list
    )
    float_pnl = total_mv - total_cost
    cash = INITIAL - total_bought + total_sold
    # 累计盈亏优先用权益−本金，与 API / 前端「累计收益」口径一致
    equity = cash + total_mv
    pnl = equity - INITIAL
    used = total_cost
    ret = pnl / INITIAL * 100 if INITIAL > 0 else 0

    now = datetime.now()
    m = now.strftime("%Y-%m")
    mb = ms = mst = 0
    for t in pt.get("trade_log", []):
        if t.get("time", "")[:7] == m:
            amt = float(t.get("amount", 0) or 0)
            pn = float(t.get("pnl", 0) or 0)
            a = t.get("action", "")
            if a.startswith("买入") or a == "买入":
                mb += amt
            elif "卖出" in a:
                ms += amt
                mst += pn
    mpnl = mst + float_pnl
    mr = mpnl / INITIAL * 100 if INITIAL > 0 else 0

    pt["initial_capital"] = INITIAL
    pt["account"] = {
        "market_value": round(total_mv, 2),
        "cash": round(cash, 2),
        "total_assets": round(equity, 2),
        "total_pnl_amount": round(pnl, 2),
        "total_pnl_pct": round(ret, 2),
        "asset_pnl_pct": round(ret, 2),
        "settled_pnl": round(settled_pnl, 2),
        "float_pnl": round(float_pnl, 2),
        "total_bought": round(total_bought, 2),
        "total_sold": round(total_sold, 2),
        "used_capital": round(used, 2),
        "month_pnl": round(mpnl, 2),
        "month_pnl_pct": round(mr, 2),
        "month_settled": round(mst, 2),
        "position_exposure": expo,
        "initial_capital": INITIAL,
    }
    pt["exit_policy"] = {
        "mode": "e2_hard_stop_close_confirm + dynamic_peel + daily_t2_fund_extend; eod_no_time_force",
        "hard_stop": "cost {:.0%}；仅≥14:45 收盘确认窗口且现价仍≤止损才全清".format(
            HARD_STOP_PCT
        ),
        "arm": "gain>=3% activate peel only (no sell); disarm when float<0",
        "peel": "pullback>=1.5% from peak → sell half remaining; need new high before next peel; 3rd clears",
        "priority": "1 hard_stop_e2 > 2 t2_force/extend(daily only) > 3 peel(float>0 only)",
        "t2_force": "daily: held_days>=1 at >=14:45; fund inflow + price>=95% cost → extend once; next day force",
        "eod_force": "disabled (no T+3 time force); hard-stop + peel only; calendar stale>=30d cleanup",
        "trail_arm": TRAIL_ARM,
        "peel_pullback": PEEL_PULLBACK,
        "hard_stop_pct": HARD_STOP_PCT,
        "eod_force_trading_days": EOD_FORCE_TRADING_DAYS,
        "disable_eod_time_force": DISABLE_EOD_TIME_FORCE,
        "scale_in": (
            "daily: full position day1 by default (ENABLE_SCALE_IN=0); "
            "optional 50%+50% next-day confirm if ENABLE_SCALE_IN=1; "
            "dip_scale OFF (ENABLE_DIP_SCALE_IN=0); eod: full-cash one ticker"
        ),
        "enable_scale_in": ENABLE_SCALE_IN,
        "enable_dip_scale_in": ENABLE_DIP_SCALE_IN,
        "dip_scale_mode": DIP_SCALE_MODE,
        "scale_in_dip_pct": SCALE_IN_DIP_PCT,
        "entry_mode": ENTRY_MODE,
        "entry": (
            "gap_soft: <=1.5% open w=1; 1.5-3% limit prev*1.01 w=0.7; "
            "3-5% limit prev*1.02 w=linear0.5→0; >=5% skip"
        ),
    }
    if "protocol" in pt and isinstance(pt["protocol"], dict):
        pt["protocol"]["entry"] = pt["exit_policy"]["entry"]
        pt["protocol"]["entry_mode"] = ENTRY_MODE
    pt["updated_at"] = now.strftime("%Y-%m-%d %H:%M")
    json.dump(pt, open(PT_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    pos_count = sum(len(s.get("positions", [])) for s in pt["strategies"])
    log(
        "\n账户: 持仓{}只 | 市值{:.0f} | 现金{:.0f} | expo={:.0%} | 累计{:+.0f}({:+.2f}%)".format(
            pos_count, total_mv, cash, expo, pnl, ret
        )
    )


if __name__ == "__main__":
    main()
