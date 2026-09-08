# -*- coding: utf-8 -*-
"""QMT 模拟盘自动账本查看器 (2026-08-10)

读取策略自动维护的账本:
  C:\\alphapilot\\sim_trades_fullchain.json   逐笔交易记录(自动去重)
  C:\\alphapilot\\ledger_daily.json           每日收盘快照(持仓+盈亏)

用法:
  python scripts/qmt_ledger_view.py            打印全部
  python scripts/qmt_ledger_view.py --day 20260810   只查某日
  python scripts/qmt_ledger_view.py --json     输出原始 JSON
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRADE_LOG = r"C:\alphapilot\sim_trades_fullchain.json"
LEDGER_DAILY = r"C:\alphapilot\ledger_daily.json"


def load_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("  [ERR] " + path + ": " + str(e))
        return None


def view(day=None, as_json=False):
    trades = load_json(TRADE_LOG)
    daily = load_json(LEDGER_DAILY)

    if as_json:
        out = {"trades": trades or [], "daily": daily or {}}
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return

    print("=" * 78)
    print("QMT 模拟盘自动账本 (策略自动记录)")
    print("  交易日志: " + TRADE_LOG)
    print("  每日快照: " + LEDGER_DAILY)
    print("=" * 78)

    # 逐笔交易
    if trades:
        if day:
            day_str = str(day)
            t2 = [t for t in trades if str(t.get("time", "")).startswith(
                day_str[:4] + "-" + day_str[4:6] + "-" + day_str[6:8])]
        else:
            t2 = trades
        if t2:
            print("\n## 逐笔交易 (" + str(len(t2)) + " 条)")
            print(f"{'时间':19s} {'动作':9s} {'代码':12s} {'股数':>8s} {'价格':>8s}  原因")
            for t in t2:
                print(f"{t.get('time',''):19s} {t.get('action',''):9s} "
                      f"{t.get('symbol',''):12s} {t.get('volume',0):8d} "
                      f"{t.get('price',0):8.3f}  {t.get('reason','')}")
        else:
            print("\n无该日交易记录")
    else:
        print("\n无交易日志 (文件不存在或为空)")

    # 每日快照
    if daily:
        days = list(daily.keys())
        if day:
            days = [d for d in days if d == str(day)]
        if days:
            print("\n## 每日收盘快照")
            for d in sorted(days):
                s = daily[d]
                print(f"\n  {d}  (快照时间 {s.get('time','')})")
                pos = s.get("positions", [])
                if pos:
                    print(f"    {'代码':12s} {'股数':>8s} {'成本':>8s} {'现价':>8s} "
                          f"{'浮盈':>10s} {'幅度':>7s}")
                    for p in pos:
                        print(f"    {p['code']:12s} {p['shares']:8d} {p['cost']:8.3f} "
                              f"{p['price']:8.3f} {p['pl']:10.2f} {p['pl_pct']:6.2f}%")
                else:
                    print("    (空仓)")
                print(f"    未实现盈亏: {s.get('unrealized_pl',0):+,.2f} 元 | "
                      f"当日卖出回款: {s.get('realized_proceeds',0):+,.2f} 元")
        else:
            print("\n无该日快照")
    else:
        print("\n无每日快照 (文件不存在或为空, 需策略运行到 15:05 后生成)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", type=str, default=None, help="查询日期 YYYYMMDD")
    ap.add_argument("--json", action="store_true", help="输出原始 JSON")
    args = ap.parse_args()
    view(day=args.day, as_json=args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
