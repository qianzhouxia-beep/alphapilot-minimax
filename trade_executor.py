#!/usr/bin/env python3
"""AlphaPilot V19 自动成交器 v4 — Plan C: 分级止损止盈 + T+1 强平"""
import json, os, sys
from datetime import datetime, timedelta

os.chdir("/home/ubuntu/alphapilot")
PT_PATH = "data/paper_trading.json"

# ═══ 低吸择时 ═══
# 买入不再直接以信号价(模型评分=昨收)成交, 而是盘中回踩 VWAP 后以实时价成交.
# 回放验证(60 标的日): 95% 能在盘中触发, 触发价平均低于收盘 3.16%.
LOW_ENTRY_ENABLED = os.environ.get("LOW_ENTRY_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")
# P2 动态确认 + 先到先得: 每日最多买入 MAX_DAILY_BUY 只（候选池 Top10 中先达标先买）
MAX_DAILY_BUY = int(os.environ.get("MAX_DAILY_BUY", "2"))
try:
    sys.path.insert(0, os.getcwd())
    import intraday_low as _low
    except Exception:
    _low = None

# ═══ Plan C 参数 ═══
LADDER_STOP = [[-0.03, 0.5]]    # -3% → 卖一半
STOP_HARD = -0.05                # -5% → 全卖
OPEN_PROTECT = -0.07             # 09:35-09:45 放宽到 -7%
LIMIT_DOWN = -0.095              # 跌停立即卖
LADDER_TP = [[0.05, 0.5], [0.10, 1.0]]  # (已废除, 改用趋势跟踪峰值回撤6%)
CONSECUTIVE_MIN = 3              # -3% 需连续 3 分钟
T1_FORCE_HHMM = (14, 50)         # (不再强平, 保留常量兼容)
T1_FORCE_LIMIT_UP_RATIO = 3.0    # 买一单 / 成交量 > 3 → 可延期
TRAIL_EXIT_PCT = 0.06            # 从峰值回撤 6% → 止盈全卖(趋势跟踪)
MAX_HOLD_DAYS = 15               # 超期清理(防呆, 不再 T+1 硬卖)

# ═══ 策略级离场参数 (v2 系统 = 用户蚂蚁搬家思路 + 数据验证) ═══
# 用户思路: 短期目标3-5%达标 → 移动跟踪, 回撤1-1.5%离场; 蚂蚁搬家复利
# 数据验证(315样本): 目标5%+回撤1.5%+止损6%+10日 → 胜率48%/平均+5.2% (vs 无止盈24%胜率)
V2_EXIT = {
    "stop_hard": -0.06,       # 硬止损 -6%
    "target_pct": 0.05,       # 目标 +5% (达标激活移动跟踪)
    "trail_pct": 0.015,       # 激活后回撤 1.5% → 离场
    "max_hold_days": 10,      # 10日持有上限 (用户认为20日太长)
}
V2_STRAT_IDS = ("v19_daily_v2",)


def log(msg):
    t = datetime.now().strftime("%H:%M:%S")
    print(f"[{t}] {msg}")


def in_trading_session():
    """A股连续竞价时段: 09:25-11:30, 13:00-15:00.
    09:25前(集合竞价)腾讯行情是快照, 不撮合, 防止开盘前假成交."""
    now = datetime.now()
    hm = now.hour * 60 + now.minute
    return (9 * 60 + 25 <= hm <= 11 * 60 + 30) or (13 * 60 <= hm <= 15 * 60)


def trading_session_open():
    """是否已过 09:25 (允许买入/卖出)"""
    now = datetime.now()
    return now.hour * 60 + now.minute >= 9 * 60 + 25


def fetch_price(sym):
    """腾讯实时价格。09:25 前返回 None(无效快照, 防止开盘前假价)。"""
    if not trading_session_open():
        return None
    import urllib.request
    prefix = "sh" if sym.startswith("6") else "sz"
    try:
        r = urllib.request.urlopen(f"https://qt.gtimg.cn/q={prefix}{sym}", timeout=5)
        vals = r.read().decode("gbk").split('"')[1].split("~")
        if len(vals) > 3:
            return float(vals[3]) or float(vals[4]) or None
    except Exception:
        pass
    return None


def fetch_prev_close(sym):
    """腾讯昨收价。用于单日跳变检测(区分真实涨跌 vs 除权/脏数据)。"""
    import urllib.request
    prefix = "sh" if sym.startswith("6") else "sz"
    try:
        r = urllib.request.urlopen(f"https://qt.gtimg.cn/q={prefix}{sym}", timeout=5)
        vals = r.read().decode("gbk").split('"')[1].split("~")
        if len(vals) > 4 and vals[4]:
            return float(vals[4])
        except Exception:
        pass
    return None


def fetch_bid1_volume(sym):
    """获取买一挂单量（判断涨停封板）"""
    prefix = "sh" if sym.startswith("6") else "sz"
    try:
        import urllib.request
        r = urllib.request.urlopen(f"https://qt.gtimg.cn/q={prefix}{sym}", timeout=5)
        vals = r.read().decode("gbk").split('"')[1].split("~")
        if len(vals) > 20:
            bid1_vol = int(float(vals[20]) * 100) if vals[20] else 0  # 买一量(手→股)
            volume = int(vals[6]) if len(vals) > 6 else 0
            return bid1_vol, volume
    except Exception:
        pass
    return 0, 0


def half_qty(qty):
    """减半（向下取整到整百）"""
    return max(100, (qty // 2 // 100) * 100)


def in_open_protection():
    """09:35-09:45 开盘保护期"""
    now = datetime.now()
    return (now.hour == 9 and 35 <= now.minute <= 45)


def main():
    # 交易时段硬门槛: 仅连续竞价时段撮合(09:25-11:30, 13:00-15:00)
    # 排除盘前(09:25前)/午休(11:30-13:00)/盘后(15:00后)假成交
    if not in_trading_session():
        now = datetime.now()
        print(f"[{now.strftime('%H:%M:%S')}] 非交易时段(需 09:25-11:30/13:00-15:00), 跳过本次执行")
        return

    pt = json.load(open(PT_PATH))
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    now_min = now.hour * 60 + now.minute
    t1_force_min = T1_FORCE_HHMM[0] * 60 + T1_FORCE_HHMM[1]
    is_t1_window = now_min >= t1_force_min
    is_protect = in_open_protection()

    # ===== 1. 卖出（方案 C：分级止损止盈 + T+1 强平）=====
    log("=" * 60)
    log(f"Plan C 卖出检查 (保护期={is_protect} T+1窗口={is_t1_window})")

    import urllib.request as _req
    sold = 0
    for s in pt.get("strategies", []):
        remaining = []
        # 策略级离场参数: v2 用最优方案, 其他保留现状
        is_v2 = s.get("id") in V2_STRAT_IDS
        stop_hard = V2_EXIT["stop_hard"] if is_v2 else STOP_HARD
        max_hold = V2_EXIT["max_hold_days"] if is_v2 else MAX_HOLD_DAYS
        use_tp = not is_v2  # v2 无止盈
        for p in s.get("positions", []):
            sym = p.get("symbol", "")
            name = p.get("name", "")
            qty = p.get("quantity", 0)
            cost = float(p.get("buy_price", 0))
            if qty <= 0 or cost <= 0:
                continue

            # 计算持仓天数
            buy_date = p.get("buy_date", today)
            try:
                held_days = (datetime.strptime(today, "%Y-%m-%d") -
                             datetime.strptime(buy_date, "%Y-%m-%d")).days
            except Exception:
                held_days = 0

            # 拉实时价
            price = fetch_price(sym) or cost

            if price is None or price <= 0:
                price = cost

            pnl_pct = (price / cost - 1) * 100

            # ── 防呆: 当日价格跳变异常(>±11%) = 除权/数据错, 不卖(等数据修复) ──
            # 旧逻辑用「持仓盈亏>±25%」判断, 会误伤真实大涨的持仓(如 300058 蓝色光标 +24.8% 被拦下)。
            # 改用「当日涨跌幅」判断: A股单日涨跌停上限 10%(创业/科创 20%),
            # 若现价相对昨收跳变超过 11%(主板 10%+容差) 且超出 20%(双创), 才是真正的除权/脏数据。
            _prev_close = fetch_prev_close(sym)
            _day_chg = (price / _prev_close - 1) * 100 if _prev_close and _prev_close > 0 else 0.0
            # 单日跳变上限: 主板 10%, 双创 20%; 用 11% 容差覆盖
            _limit = 21.0 if (sym.startswith("30") or sym.startswith("68")) else 11.0
            if _prev_close and _prev_close > 0 and abs(_day_chg) > _limit:
                log(f"[PRICE-GUARD] {sym} {name} 单日跳变{_day_chg:.1f}% 异常(除权/数据错), 跳过卖出")
                p["current_price"] = round(price, 2)
                remaining.append(p)
                        continue

            # ═══ v2 专属离场: 目标5%+回撤1.5% (蚂蚁搬家) ═══
            if is_v2:
                # 状态: 是否已达标激活 + 激活后峰值
                if "v2_target_hit" not in p:
                    p["v2_target_hit"] = False
                    p["v2_peak_after"] = 0.0
                if price > float(p.get("v2_peak_after", 0) or 0):
                    p["v2_peak_after"] = round(price, 3)
                # 硬止损 -6%
                if pnl_pct <= V2_EXIT["stop_hard"] * 100:
                    log(f"[v2] 止损 {sym} {name}: {pnl_pct:.2f}%")
                    pt["trade_log"].append(_sell_row(s["id"], sym, name, price,
                                                      p.get("quantity", qty), cost,
                                                      "卖出(v2止损)"))
                    sold += 1
                continue
                # 达标激活: 现价 >= 成本*(1+5%)
                target_price = cost * (1 + V2_EXIT["target_pct"])
                if not p["v2_target_hit"] and price >= target_price:
                    p["v2_target_hit"] = True
                    p["v2_peak_after"] = round(price, 3)
                    log(f"[v2] 达标 {sym} {name}: {pnl_pct:.2f}% ≥ 目标, 激活移动跟踪")
                # 激活后回撤 1.5% → 离场 (蚂蚁搬家落袋)
                if p["v2_target_hit"]:
                    pull = (price / float(p["v2_peak_after"]) - 1) * 100
                    if pull <= -V2_EXIT["trail_pct"] * 100:
                        log(f"[v2] 回撤离场 {sym} {name}: 峰值{p['v2_peak_after']} 回撤{pull:.1f}%")
                        pt["trade_log"].append(_sell_row(s["id"], sym, name, price,
                                                          p.get("quantity", qty), cost,
                                                          "卖出(v2目标回撤)"))
                        sold += 1
                        continue
                # 超期强制离场 (v2: 10日上限)
                if held_days >= V2_EXIT["max_hold_days"]:
                    log(f"[v2] 超期离场 {sym} {name}: 持有{held_days}天")
                    pt["trade_log"].append(_sell_row(s["id"], sym, name, price,
                                                      p.get("quantity", qty), cost,
                                                      "卖出(v2超期)"))
                    sold += 1
                    continue
                # 更新状态
            p["current_price"] = round(price, 2)
            p["pnl_pct"] = round(pnl_pct, 2)
            remaining.append(p)
            continue

            # ── 初始化 Plan C 状态（持久化在 position dict 里）──
            if "plan_c_half_stopped" not in p:
                p["plan_c_half_stopped"] = False   # -3% 减半已做
            if "plan_c_tp_halfed" not in p:
                p["plan_c_tp_halfed"] = False      # +5% 止盈减半已做
            if "plan_c_consec_low" not in p:
                p["plan_c_consec_low"] = 0         # 连续低于 -3% 的分钟数
            if "plan_c_limit_ext" not in p:
                p["plan_c_limit_ext"] = False      # 已涨停延期
            if "plan_c_ext_traded" not in p:
                p["plan_c_ext_traded"] = False     # 延期后已处理
            half_done = p["plan_c_half_stopped"]
            tp_halfed = p["plan_c_tp_halfed"]
            consec_low = p["plan_c_consec_low"]
            limit_ext = p["plan_c_limit_ext"]

            # ── 跌停: 立即全卖 ──
            if pnl_pct <= LIMIT_DOWN * 100:
                log(f"跌停止损 {sym} {name}: {pnl_pct:.2f}%")
                pt["trade_log"].append(_sell_row(s["id"], sym, name, price, qty, cost,
                                                  f"卖出(跌停·全清)"))
                sold += 1
                continue

            # ── 开盘保护期: -7% 全卖 ──
            if is_protect and pnl_pct <= OPEN_PROTECT * 100:
                log(f"开盘止损 {sym} {name}: {pnl_pct:.2f}% (保护期)")
                pt["trade_log"].append(_sell_row(s["id"], sym, name, price, qty, cost,
                                                  f"卖出(开盘止损·全清)"))
                sold += 1
                continue

            # ── 硬止损 (v2: -6%, 其他: -5%) ──
            if pnl_pct <= stop_hard * 100:
                log(f"硬止损 {sym} {name}: {pnl_pct:.2f}%")
                pt["trade_log"].append(_sell_row(s["id"], sym, name, price, qty, cost,
                                                  f"卖出(硬止损·全清)"))
                sold += 1
                continue

            # ── 分级止损 -3%: 连续 N 分钟低于 -3% → 卖一半 ──
            if pnl_pct <= LADDER_STOP[0][0] * 100:
                if not half_done:
                    consec_low += 1
                    p["plan_c_consec_low"] = consec_low
                    if consec_low >= CONSECUTIVE_MIN:
                        half = half_qty(qty)
                        if half >= 100 and half < qty:
                            log(f"分级止损 {sym} {name}: {pnl_pct:.2f}% {consec_low}分钟 → 减半卖{half}股")
                            pt["trade_log"].append(_sell_row(s["id"], sym, name, price, half, cost,
                                                              f"卖出(分级止损·减半)"))
                            p["quantity"] = qty - half
                            p["plan_c_half_stopped"] = True
                            sold += 1
                            # 减半后如果还有剩余，继续持有
                            remaining.append(p)
                            continue
                        # 减半后不足 100 股 → 全卖
            else:
                            log(f"分级止损 {sym} {name}: {pnl_pct:.2f}% 减半不足 → 全清")
                            pt["trade_log"].append(_sell_row(s["id"], sym, name, price, qty, cost,
                                                              f"卖出(分级止损·清仓)"))
                            p["quantity"] = 0
                            sold += 1
                continue
                # 还没到 3 分钟，继续持有
                p["plan_c_consec_low"] = consec_low
                remaining.append(p)
                continue
            else:
                # 价格回升 → 重置计数器
                p["plan_c_consec_low"] = 0

            # ── 固定止盈 +5%/+10% 已废除 (2026-07-31): 让利润奔跑 ──
            # 历史教训: 300058 蓝色光标 +19.88% 被 +5% 减半, 次日涨停+20%
            # 卖出仅由趋势跟踪(峰值回撤6%)/止损/跌停/超期触发
            pass

            # ── 趋势跟踪退出（替代硬 T+1/T+2 强平）──
            # v2: 无止盈 (回测证明止盈砍收益), 仅保留止损/超期
            # 其他: 创新高持有, 峰值回撤 ≥ TRAIL_EXIT_PCT → 止盈全卖
            peak = float(p.get("trail_peak", 0) or 0)
            if price > peak:
                p["trail_peak"] = round(price, 3)
                peak = price
            # 涨停封板检查(现价≥涨停幅度且封单强) → 持有
            bid1_vol, volume = fetch_bid1_volume(sym)
            is_limit_up = pnl_pct >= 9.5 and bid1_vol > 0 and volume > 0 and \
                          (bid1_vol / volume) >= T1_FORCE_LIMIT_UP_RATIO
            if is_limit_up:
                p["plan_c_limit_ext"] = True
                remaining.append(p)
            continue
            # 从峰值回撤超过阈值 → 止盈全卖(锁定利润) [v2 跳过: 让利润奔跑]
            if not is_v2 and peak > 0 and peak > cost:
                pullback = (price / peak - 1) * 100
                if pullback <= -TRAIL_EXIT_PCT * 100:
                    log(f"趋势止盈 {sym} {name}: 峰值{peak} 回撤{pullback:.1f}% → 全卖")
                    pt["trade_log"].append(_sell_row(s["id"], sym, name, price,
                                                      p.get("quantity", qty), cost,
                                                      f"卖出(趋势止盈·峰值回撤)"))
                    sold += 1
                continue

            # ── 涨停延期后的次日强平（09:35-09:40 处理）──
            if limit_ext and not p.get("plan_c_ext_traded", False) and \
               now.hour == 9 and 35 <= now.minute <= 40:
                log(f"涨停延期强平 {sym} {name}")
                pt["trade_log"].append(_sell_row(s["id"], sym, name, price,
                                                  p.get("quantity", qty), cost,
                                                  f"卖出(涨停延期·强平)"))
                p["plan_c_ext_traded"] = True
                sold += 1
                continue

            # ── 超期清理（防呆, 长持标的可手动处理）──
            if held_days >= max_hold:
                log(f"超期清理 {sym} {name}: 持有{held_days}天")
                pt["trade_log"].append(_sell_row(s["id"], sym, name, price,
                                                  p.get("quantity", qty), cost,
                                                  f"卖出(超期清理)"))
                sold += 1
                    continue

            # ── 更新持仓 ──
            p["current_price"] = round(price, 2)
            p["pnl_pct"] = round(pnl_pct, 2)
            p["pnl_amount"] = round((price - cost) * p.get("quantity", qty), 2)
            p["days_held"] = p.get("days_held", 0) + 1
            remaining.append(p)

        s["positions"] = remaining

    if sold > 0:
        log(f"共卖出 {sold} 笔")

    # ===== 2. 买入（P2 动态确认 + 先到先得: 候选池中先达标先买, 每日最多 MAX_DAILY_BUY 只）=====
    log("\n检查买入信号...")
    all_signals = []
        for s in pt.get("strategies", []):
        for sig in s.get("signals", []):
            if sig.get("action") == "buy":
                all_signals.append(sig)

    if all_signals:
        log(f"待成交信号: {len(all_signals)} 条 (候选池, 先到先得最多买 {MAX_DAILY_BUY} 只)")
        held_symbols = set()
        for s in pt.get("strategies", []):
            for p in s.get("positions", []):
                held_symbols.add(p.get("symbol", ""))
        traded_symbols = set()
        for t in pt.get("trade_log", []):
            traded_symbols.add(t.get("symbol", ""))

        # 当日已买入数（用于先到先得上限）
        today_bought = 0
        for t in pt.get("trade_log", []):
            if t.get("time", "").startswith(datetime.now().strftime("%Y-%m-%d")) and t.get("action") == "买入":
                today_bought += 1

        executed = 0
        for sig in all_signals:
                sym = sig.get("symbol", "")
                name = sig.get("name", "")
            ref_price = float(sig.get("price", 0))
            strat_id = sig.get("strategy_id", "v19_daily")
            if not sym or ref_price <= 0:
                    continue
                if sym in held_symbols:
                log(f" 跳过 {sym} {name}: 已有持仓")
                    continue
            if sym in traded_symbols:
                log(f" 跳过 {sym} {name}: 已有成交记录")
                    continue
            # 先到先得: 已买满上限 → 不再买入（信号保留, 次日作废/由下一次信号覆盖）
            if today_bought >= MAX_DAILY_BUY:
                log(f" 已达今日买入上限 {MAX_DAILY_BUY} 只, 跳过剩余候选 {sym} {name}")
                break

            # ── P2 动态确认: 求实际成交价 ──
            # 触发(dyn_confirm) → 用实时价成交;
            # 未触发(wait_confirm) → 保留信号等待下一次 cron;
            # 观察期结束(no_confirm_eod) → 放弃.
            entry_mode = "direct"
            price = ref_price
            if LOW_ENTRY_ENABLED and _low is not None:
                price, reason = _low.low_entry_price(sym, ref_price)
                if price is None:
                    if reason in ("abandon_no_dip", "force_abandon_high_gap", "hybrid_abandon",
                                  "no_quote_end", "no_confirm_eod", "skip_high_turnover"):
                        log(f" 放弃 {sym} {name}: {reason} (观察窗口关闭/换手超限)")
                        for s in pt["strategies"]:
                            s["signals"] = [x for x in s.get("signals", []) if not (x.get("symbol") == sym and x.get("action") == "buy")]
                    continue
                    log(f" 等待 {sym} {name}: 动态确认未触发 ({reason})")
                        continue
                entry_mode = reason

            total_cash = pt["account"].get("cash", 0)
            per_trade = min(50000, total_cash / max(1, len(all_signals)))
            qty = int(per_trade / price / 100) * 100
            if qty < 100: qty = 100
            actual_cost = qty * price
            if actual_cost > total_cash: continue

            log(f" 成交 {sym} {name} x{qty}股 = {actual_cost:.0f} @{price} [{strat_id}] entry={entry_mode}")
            pt["trade_log"].append({
                "time": now.strftime("%Y-%m-%d %H:%M"),
                "symbol": sym, "name": name, "action": "买入",
                "price": price, "quantity": qty,
                "amount": round(actual_cost, 2), "strategy_id": strat_id,
                "entry_mode": entry_mode,
            })
            pos = {
                "symbol": sym, "name": name,
                "entry_price": price, "buy_price": price, "current_price": price,
                "quantity": qty, "pnl_pct": 0, "pnl_amount": 0,
                "stop_loss": sig.get("stop_price", round(price * 0.95, 2)),  # Plan C: -5%
                "take_profit": sig.get("target_price", round(price * 1.10, 2)),  # Plan C: +10%
                "days_held": 0, "strategy_id": strat_id,
                "buy_date": today,
                "entry_mode": entry_mode,
                # Plan C state
                "plan_c_half_stopped": False,
                "plan_c_tp_halfed": False,
                "plan_c_consec_low": 0,
                "plan_c_limit_ext": False,
                "plan_c_ext_traded": False,
            }
            found = False
            for st in pt["strategies"]:
                if st["id"] == strat_id:
                    if "positions" not in st: st["positions"] = []
                    st["positions"].append(pos)
                    st["used"] = float(st.get("used", 0)) + actual_cost
                    found = True; break
            if not found:
                pt["strategies"].append({
                    "id": strat_id, "name": strat_id, "status": "active",
                    "allocated": 500000, "used": actual_cost,
                    "signals": [], "positions": [pos],
                })
            for st in pt["strategies"]:
                st["signals"] = [x for x in st.get("signals", []) if x.get("symbol") != sym]
            held_symbols.add(sym); traded_symbols.add(sym)
            executed += 1
            today_bought += 1
        log(f"成交完成: {executed} 笔 (今日累计买入 {today_bought})")
    else:
        log("无待成交信号")

    # ===== 3. 更新账户 =====
    pos_list = []
    for s in pt["strategies"]:
        pos_list.extend(s.get("positions", []))
    total_cost = sum(p.get("quantity", 0) * p.get("buy_price", 0) for p in pos_list)
    total_mv = sum(p.get("quantity", 0) * (p.get("current_price", 0) or p.get("buy_price", 0)) for p in pos_list)
    pnl = total_mv - total_cost

    # 现金直接用账户字段(不依赖 trade_log 重算——人工删单会失真)
    INITIAL = float(pt.get("initial_capital", 2000000) or 2000000)
    _cash_ok = round(float(pt["account"].get("cash", 0) or 0), 2)
    pt["account"]["market_value"] = round(total_mv, 2)
    pt["account"]["cash"] = _cash_ok
    pt["account"]["total_assets"] = round(_cash_ok + total_mv, 2)
    pt["account"]["total_pnl_amount"] = round(_cash_ok + total_mv - INITIAL, 2)
    pt["account"]["total_pnl_pct"] = round((_cash_ok + total_mv - INITIAL) / INITIAL * 100, 2) if INITIAL > 0 else 0

    # ── 写入 exit_policy 方案 C ──
    pt["exit_policy"] = {
        "mode": "plan_C",
        "ladder_stop": "[[-0.03, 0.5]] consecutive 3min → half",
        "stop_hard": "-0.05 → full clear",
        "open_protection": "-0.07 during 09:35-09:45",
        "limit_down": "-0.095 → immediate full clear",
        "ladder_tp": "[[0.05, 0.5], [0.10, 1.0]] using original buy price",
        "t1_force": "held>=1 day at 14:50; limit-up (bid1/vol>3x) extends to next 09:35",
        "c_atr_adaptive": False,
        "check_intraday": True,
    }
    pt["updated_at"] = now.strftime("%Y-%m-%d %H:%M")

    json.dump(pt, open(PT_PATH, "w"), ensure_ascii=False, indent=2)

    pos_count = sum(len(s.get("positions", [])) for s in pt["strategies"])
    total_cash = pt["account"].get("cash", 0)
    log(f"\n账户: 持仓{pos_count}只 | 市值{total_mv:.0f} | 现金{total_cash:.0f} | PnL {pnl:+.2f}%")


def _sell_row(strat_id, sym, name, price, qty, cost, action):
    return {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "symbol": sym, "name": name,
        "action": action,
        "price": round(price, 2),
        "quantity": qty,
        "amount": round(price * qty, 2),
        "strategy_id": strat_id,
        "pnl": round((price - cost) * qty, 2),
    }


if __name__ == "__main__":
    main()
