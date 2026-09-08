# -*- coding: utf-8 -*-
"""vwap_weak_early 信号回测分析 (一次性)

对每个 vwap_broken 信号(信号日/股票):
  sell_ref   = 信号日 14:45 记录的 px (模拟"若无信号继续持有的成本锚", 其实是信号发生时的价格)
  实际成本锚 = 用买入成本更合理, 但信号日 ret 已给出相对成本收益.
  A. 现状: 次日早盘(09:35-09:50)卖, 近似用次日 09:40 bar close; 08-31 用实际日志价
  B. 次日收盘卖 (信号次日收盘)
  C. 持有: 持有到 08-28 收盘 (最后完整交易日), 08-31 信号持有到今天盘中

输出相对"次日早盘卖"的增量收益, 以及每只股票的后续最高价(衡量卖飞程度)
"""
import json, os, re

sig = json.load(open(r"C:\Users\elvisq\Projects\alphapilot\scripts\_vwap_signals_dedup.json"))
m5 = json.load(open(r"C:\Users\elvisq\Projects\alphapilot\scripts\_m5_data.json"))

# 交易日顺序
TD = ["2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28", "2026-08-31"]

def m5_close(sym6, day, hhmm="09:40"):
    """从 5m 数据取某日 09:40 bar 收盘价"""
    bars = m5.get(sym6, [])
    for b in bars:
        t = b[0]
        if day in t and hhmm in t:
            return b[4]
    return None

def day_open_close(sym6, day):
    """5m 数据聚合日开盘/最高/收盘"""
    bars = m5.get(sym6, [])
    ds = [b for b in bars if day in b[0]]
    if not ds:
        return None, None, None
    o = ds[0][1]
    h = max(b[2] for b in ds)
    c = ds[-1][4]
    return o, h, c

# 08-31 实际日志卖出价 (B轨模拟 09:35-09:50)
actual_0831 = {"000700.SZ": 11.20, "002292.SZ": 8.16, "003032.SZ": 10.22}
# 08-31 盘中(11:30)快照价
actual_0831_close = {"000700.SZ": 11.41, "002292.SZ": 8.38, "003032.SZ": 10.70}
# 08-31 当日最高(11:30前) 用 5m 聚合近似——实际从 mootdx 实时数据获取
actual_0831_high = {"000700.SZ": 11.43, "002292.SZ": 8.40, "003032.SZ": 10.71}

results = []
for s in sig:
    date = s["date"]
    # 信号日志格式 YYYYMMDD -> 标准 YYYY-MM-DD
    date_std = "%s-%s-%s" % (date[:4], date[4:6], date[6:8])
    sym = s["symbol"]
    sym6 = sym.split(".")[0]
    # 信号日 index
    di = TD.index(date_std) if date_std in TD else None
    if di is None:
        continue
    nxt = TD[di + 1] if di + 1 < len(TD) else None
    if not nxt:
        continue

    # A: 次日早盘卖价
    if nxt == "2026-08-31":
        price_a = actual_0831.get(sym)
    else:
        price_a = m5_close(sym6, nxt, "09:40")
        if price_a is None:
            price_a = m5_close(sym6, nxt, "09:45")
    # B: 次日收盘
    _, _, close_b = day_open_close(sym6, nxt)
    # C: 持有到 08-28 收盘 (信号在 08-28 之前的持有到今天)
    if date_std < "2026-08-28":
        _, _, close_c = day_open_close(sym6, "2026-08-28")
    else:
        close_c = actual_0831_close.get(sym)  # 08-31 信号 -> 今天盘中
    # 后续最高价 (从信号次日到 08-28 或今天)
    if nxt == "2026-08-31":
        high_nxt = actual_0831_high.get(sym)
    else:
        _, high_nxt, _ = day_open_close(sym6, nxt)

    results.append({
        "date": date, "nxt": nxt, "symbol": sym,
        "sig_ret": s["ret"], "sig_px": s["px"],
        "price_a": price_a, "price_b": close_b, "price_c": close_c,
        "high_nxt": high_nxt,
    })

print("n =", len(results))
print("="*110)
print("%-12s %-10s %-6s %8s %8s %8s %8s | %8s" % ("信号日", "股票", "次日", "sig_ret%", "A早盘卖", "B次日收", "C持有", "次日最高"))
print("-"*110)
for r in sorted(results, key=lambda x: (x["date"], x["symbol"])):
    pa, pb, pc, ph = r["price_a"], r["price_b"], r["price_c"], r["high_nxt"]
    if pa:
        da = (pb / pa - 1) * 100 if pb else None
        dc = (pc / pa - 1) * 100 if pc else None
        dh = (ph / pa - 1) * 100 if ph else None
        print("%-12s %-10s %-6s %8.1f %8.2f %8.2f %8.2f | %8.2f  B vs A=%+.1f%%  C vs A=%+.1f%%  H vs A=%+.1f%%" % (
            r["date"], r["symbol"], r["nxt"][5:], r["sig_ret"], pa, pb or 0, pc or 0, ph or 0,
            da if da is not None else -99, dc if dc is not None else -99, dh if dh is not None else -99))
    else:
        print("%-12s %-10s %-6s %8.1f  (A price missing)" % (r["date"], r["symbol"], r["nxt"][5:], r["sig_ret"]))

# 汇总统计
print()
diffs_b = [ (r["price_b"]/r["price_a"]-1)*100 for r in results if r["price_a"] and r["price_b"] ]
diffs_c = [ (r["price_c"]/r["price_a"]-1)*100 for r in results if r["price_a"] and r["price_c"] ]
diffs_h = [ (r["high_nxt"]/r["price_a"]-1)*100 for r in results if r["price_a"] and r["high_nxt"] ]
print("B(次日收) vs A(早盘卖): mean=%+.2f%%  win=%d/%d" % (sum(diffs_b)/len(diffs_b), sum(1 for d in diffs_b if d>0), len(diffs_b)) if diffs_b else "no data")
print("C(持有) vs A(早盘卖):   mean=%+.2f%%  win=%d/%d" % (sum(diffs_c)/len(diffs_c), sum(1 for d in diffs_c if d>0), len(diffs_c)) if diffs_c else "no data")
print("H(次日最高) vs A(早盘):  mean=%+.2f%%  (卖飞空间)" % (sum(diffs_h)/len(diffs_h)) if diffs_h else "no data")
