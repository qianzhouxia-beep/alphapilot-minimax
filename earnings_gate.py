# -*- coding: utf-8 -*-
"""
业绩门控（Earnings Gate）

数据源：akshare stock_yjbb_em（免费，东方财富业绩报表）
         ak.stock_yjyg_em（免费，业绩预告）

剔除规则：
  1. 业绩预告中标记为"预减"、"首亏"、"续亏"
  2. 季报显示 净利润-同比增长 < -50%（业绩大幅下降）
  3. 季报显示 净利润为负且同比也在下降（亏损恶化）

运行时机：管线 Step 3（宇宙门）之后，Step 4（资金门）之前
"""
from __future__ import annotations

import json
import os
import sys
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

warnings.filterwarnings("ignore")

ROOT = Path("/home/ubuntu/alphapilot")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

# 业绩下降剔除阈值
PROFIT_DECLINE_THRESHOLD = -50  # 净利润同比降幅 > 50% 剔除
LOSS_THRESHOLD = 0  # 净利润为负（即亏损）

# 业绩预告剔除类型
BAD_FORECAST_TYPES = {"预减", "首亏", "续亏", "略减"}


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _bare(sym: str) -> str:
    s = str(sym or "").lower().replace("sh", "").replace("sz", "").replace("bj", "")
    return s[-6:] if len(s) >= 6 else s


# ── 数据加载 ──

def load_yjyg_forecast() -> dict[str, dict]:
    """加载业绩预告数据。
    
    返回: { bare_symbol: { 'forecast_type': str, 'change_pct': float } }
    """
    import akshare as ak

    today = datetime.now().strftime("%Y-%m-%d")
    for date in [today, "2026-07-23", "2026-07-22", "2026-07-21"]:
        try:
            df = ak.stock_yjyg_em(date=date)
            if df is None or df.empty:
                continue
            break
        except Exception:
            continue
    else:
        # Fallback: try quarterly approach instead
        return {}

    result = {}
    for _, row in df.iterrows():
        try:
            code = str(row.get("股票代码", "")).zfill(6)
            forecast_type = str(row.get("预告类型", "")).strip()
            change_str = str(row.get("最大变动", "0") or "0").replace("%", "").strip()
            try:
                change_pct = float(change_str)
            except (ValueError, TypeError):
                change_pct = 0.0
            result[code] = {
                "forecast_type": forecast_type,
                "change_pct": change_pct,
            }
        except Exception:
            continue

    log(f"  业绩预告: {len(result)} 条")
    return result


def load_quarterly_reports() -> dict[str, dict]:
    """加载最新季报数据（优先最新且覆盖度足够的报告期）。
    
    返回: { bare_symbol: { 'profit_yoy': float, 'net_profit': float } }
    """
    import akshare as ak

    # 按时间倒序尝试（最新 > 覆盖度 > 3000 只的）
    for date in ["20260630", "20260331", "20251231", "20250930"]:
        try:
            df = ak.stock_yjbb_em(date=date)
            if df is not None and not df.empty and len(df) > 3000:
                break
        except Exception:
            continue
    else:
        log("  ⚠️ 无有效季报数据")
        return {}

    n_rows = len(df)
    log(f"  季报数据: {n_rows} 条（{date}）")

    result = {}
    for _, row in df.iterrows():
        try:
            code = str(row.get("股票代码", "")).zfill(6)
            pct_raw = str(row.get("净利润-同比增长", "0") or "0").replace("%", "").strip()
            try:
                profit_yoy = float(pct_raw) if pct_raw and pct_raw != "nan" else 0.0
            except (ValueError, TypeError):
                profit_yoy = 0.0

            np_raw = str(row.get("净利润-净利润", "0") or "0").strip()
            try:
                net_profit = float(np_raw) if np_raw and np_raw != "nan" else 0.0
            except (ValueError, TypeError):
                net_profit = 0.0

            result[code] = {"profit_yoy": profit_yoy, "net_profit": net_profit, "quarter": date}
        except Exception:
            continue

    log(f"  季报解析完成: {len(result)} 只")
    return result


# ── 过滤逻辑 ──

def check_symbol(
    symbol: str,
    forecast_map: dict[str, dict],
    quarterly_map: dict[str, dict],
) -> tuple[bool, str]:
    """检查一只股票是否应被剔除。

    返回: (should_eliminate: bool, reason: str)
    """
    code = _bare(symbol)

    # 1. 业绩预告检查
    fc = forecast_map.get(code)
    if fc:
        ftype = fc.get("forecast_type", "")
        if ftype in BAD_FORECAST_TYPES:
            return True, f"业绩预告:{ftype}(变动{fc.get('change_pct', 0):+.1f}%)"
        # 即使不在这几个类型里，变动幅度 < -50% 也剔除
        if fc.get("change_pct", 0) < -50:
            return True, f"业绩预告:预计降幅{fc['change_pct']:.1f}%"

    # 2. 季报检查
    qr = quarterly_map.get(code)
    if qr:
        profit_yoy = qr.get("profit_yoy", 0)
        net_profit = qr.get("net_profit", 0)

        # 净利润同比大幅下降
        if profit_yoy < PROFIT_DECLINE_THRESHOLD:
            return True, f"季报:净利同比{profit_yoy:+.1f}%(降幅>{abs(PROFIT_DECLINE_THRESHOLD)}%)"

        # 亏损且同比也在下降
        if net_profit < LOSS_THRESHOLD and profit_yoy < 0:
            return True, f"季报:亏损({net_profit:.0f})且同比{profit_yoy:+.1f}%"

        # 每股收益为 0 或负值也可以考虑
        # (这一步比较严格，先不做)

    return False, ""


def apply_earnings_gate(items: list[dict]) -> list[dict]:
    """对候选股列表应用业绩门控。

    Args:
        items: 候选股列表，每个包含 'symbol', 'name' 等字段

    Returns:
        过滤后的候选股列表
    """
    if not items:
        return items

    # 1. 加载数据
    log("应用业绩门控 (Earnings Gate)...")
    forecast_map = load_yjyg_forecast()
    quarterly_map = load_quarterly_reports()

    if not forecast_map and not quarterly_map:
        log("  ⚠️ 无业绩/季报数据可用，跳过")
        return items

    # 2. 逐股检查
    eliminated = []
    kept = []
    for it in items:
        sym = it.get("symbol", "")
        name = it.get("name", "")
        elim, reason = check_symbol(sym, forecast_map, quarterly_map)
        if elim:
            eliminated.append({"symbol": sym, "name": name, "reason": reason})
        else:
            kept.append(it)

    # 3. 输出统计
    n_total = len(items)
    n_elim = len(eliminated)
    if n_elim > 0:
        log(f"  业绩门: {n_elim}/{n_total} 只被剔除")
        for e in eliminated:
            log(f"    ❌ {e['name']}({e['symbol']}) — {e['reason']}")
    else:
        log(f"  业绩门: 0/{n_total} 只被剔除（全部通过）")

    return kept


# ── 独立入口（可直接python运行）──
def main():
    """独立运行：读取 daily_recommend.json 做业绩过滤"""
    rec_path = ROOT / "output" / "daily_recommend.json"
    if not rec_path.exists():
        log(f"❌ {rec_path} 不存在")
        return 1

    recs = json.loads(rec_path.read_text(encoding="utf-8"))
    items = recs.get("recommendations", [])
    if not items:
        log("  ⚠️ daily_recommend.json 为空")
        return 1

    log(f"读取 {len(items)} 只候选股")
    filtered = apply_earnings_gate(items)

    # 写回
    recs["recommendations"] = filtered
    recs["earnings_gate"] = {
        "n_before": len(items),
        "n_after": len(filtered),
        "n_eliminated": len(items) - len(filtered),
        "run_at": datetime.now().isoformat(),
    }
    rec_path.write_text(json.dumps(recs, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"✅ 写回 {rec_path} ({len(filtered)} 只)")

    # 输出被剔除明细
    if len(items) - len(filtered) > 0:
        eliminated_symbols = {it["symbol"] for it in items} - {it["symbol"] for it in filtered}
        log(f"\n被剔除 {len(eliminated_symbols)} 只:")
        for it in items:
            if it["symbol"] in eliminated_symbols:
                log(f"  {it['name']}({it['symbol']})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
