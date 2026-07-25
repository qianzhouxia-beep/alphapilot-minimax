#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
09:35 全市场动量扫描 — 双轨评分（ICIR + 实时资金流）

方案：
  05:00 管线保存全量 ICIR 分数（output/icir_all_scores.json）
  09:35 本脚本拉全市场 akshare 资金流（免费，~13s）
  合并：final = ICIR_z × 0.5 + momentum_z × 0.5
  新票（无 ICIR）：final = momentum_z × 0.9
  → 门控链 → Top 37 → daily_recommend.json

数据源（全部免费）：
  - akshare stock_fund_flow_individual(~5197只)：主力净额、主动买入比、涨跌幅、换手率
  - Wind board flow（08:50 已缓存）：板块 prefer/avoid

运行时序：09:35 → 09:35:18（~18s）→ 09:36 下单
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import warnings

warnings.filterwarnings("ignore")

ROOT = Path("/home/ubuntu/alphapilot")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

# 路径
ICIR_PATH = ROOT / "output" / "icir_all_scores.json"
REC_PATH = ROOT / "output" / "daily_recommend.json"
INDUSTRY_MAP_PATH = ROOT / "data" / "stock_industry_map.json"
BOARD_FLOW_PATH = ROOT / "data" / "wind_board_flow.json"
GC_POOL_PATH = ROOT / "output" / "volume_gc_pool.json"
EXCLUDE_PATH = ROOT / "config" / "exclude_symbols.json"

# 参数
TOP_N = 50
HARD_DROP = -5.0          # 跌超 5% 硬剔除
SECTOR_MAX_TOP10 = 2      # Top10 同板块最多 2 只
SECTOR_MAX_POOL = 4       # 全池同板块最多 4 只

# 动量因子权重
W_MAIN_NET = 0.35
W_ACTIVE_BUY = 0.25
W_CHG_PCT = 0.25
W_TURNOVER = 0.15

# ICIR 与动量融合权重
W_ICIR = 0.50
W_MOMENTUM = 0.50
NEW_STOCK_PENALTY = 0.9   # 无 ICIR 的新票折价

# 季报业绩下降剔除阈值
PROFIT_DECLINE_THRESHOLD = -50


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _bare(sym: str) -> str:
    s = str(sym or "").lower().replace("sh", "").replace("sz", "").replace("bj", "")
    return s.zfill(6)[-6:]


# ── 1. 加载数据 ──

def load_icir_scores() -> dict[str, dict]:
    """加载 05:00 管线保存的全量 ICIR 分数"""
    if not ICIR_PATH.exists():
        log(f"  ⚠️ ICIR 分数文件不存在: {ICIR_PATH}")
        return {}
    try:
        data = json.loads(ICIR_PATH.read_text(encoding="utf-8"))
        raw = data.get("stocks", [])
        result = {}
        for s in raw:
            result[_bare(s["symbol"])] = s
        log(f"  ICIR 分数: {len(result)} 只（来自 {ICIR_PATH.name}）")
        return result
    except Exception as e:
        log(f"  ❌ ICIR 加载失败: {e}")
        return {}


def load_industry_map() -> dict[str, dict]:
    if not INDUSTRY_MAP_PATH.exists():
        return {}
    try:
        return json.loads(INDUSTRY_MAP_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_sector(sym: str, imap: dict) -> str:
    meta = imap.get(_bare(sym), {})
    if isinstance(meta, dict):
        return meta.get("industry_l1", "其他")
    return "其他"


def load_board_flow() -> dict[str, str]:
    """从 wind_board_flow.json 读取板块基线 {sector: prefer/avoid/neutral}"""
    if not BOARD_FLOW_PATH.exists():
        return {}
    try:
        data = json.loads(BOARD_FLOW_PATH.read_text(encoding="utf-8"))
        consult = data.get("consult") or {}
        prefer = set(consult.get("prefer", []))
        avoid = set(consult.get("avoid", []))
        result = {}
        for s in prefer:
            result[s] = "prefer"
        for s in avoid:
            result[s] = "avoid"
        log(f"  板块基线: prefer={len(prefer)} avoid={len(avoid)}")
        return result
    except Exception:
        return {}


def load_excluded_symbols() -> set[str]:
    """加载排除股票列表"""
    if not EXCLUDE_PATH.exists():
        return set()
    try:
        data = json.loads(EXCLUDE_PATH.read_text(encoding="utf-8"))
        return set(_bare(s) for s in (data.get("symbols", []) + data.get("exclude", [])))
    except Exception:
        return set()


def load_gc_pool() -> set[str]:
    """加载 05:00 启动形态池（用于偏好标记，非硬门控）"""
    if not GC_POOL_PATH.exists():
        return set()
    try:
        raw = json.loads(GC_POOL_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return {_bare(s) for s in raw}
        if isinstance(raw, dict):
            return {_bare(s) for s in (raw.get("symbols") or [])}
        return set()
    except Exception:
        return set()


def load_yjbb_map() -> dict[str, float]:
    """加载最新季报的净利润同比增长（用于业绩门控）"""
    import akshare as ak
    for date in ["20260331", "20251231", "20260630"]:
        try:
            df = ak.stock_yjbb_em(date=date)
            if df is not None and not df.empty and len(df) > 1000:
                break
        except Exception:
            continue
    else:
        return {}

    result = {}
    for _, row in df.iterrows():
        try:
            code = str(row["股票代码"]).zfill(6)
            yoy = float(str(row.get("净利润-同比增长", "0") or "0").replace("%", "").strip())
            result[code] = yoy
        except (ValueError, TypeError, KeyError):
            continue
    log(f"  季报业绩: {len(result)} 条（{date}）")
    return result


# ── 2. 实时资金流扫描（akshare 免费）──

def fetch_live_fund_flow() -> pd.DataFrame:
    """akshare全市场资金流扫描（免费，~13s），返回 DataFrame"""
    import akshare as ak

    t0 = time.time()
    df = ak.stock_fund_flow_individual(symbol="即时")

    # 标准化
    df["code6"] = df["股票代码"].map(_bare)
    df["name"] = df["股票简称"]

    # 解析金额字段
    def _parse(s):
        if s is None or (isinstance(s, float) and pd.isna(s)):
            return 0.0
        s = str(s).strip()
        try:
            if s.endswith("亿"):
                return float(s[:-1]) * 1e8
            elif s.endswith("万"):
                return float(s[:-1]) * 1e4
            return float(s)
        except (ValueError, AttributeError):
            return 0.0

    def _parse_pct(s):
        if s is None or (isinstance(s, float) and pd.isna(s)):
            return 0.0
        try:
            return float(str(s).replace("%", "").strip())
        except (ValueError, AttributeError):
            return 0.0

    df["main_inflow"] = df["流入资金"].apply(_parse)
    df["main_outflow"] = df["流出资金"].apply(_parse)
    if "净额" in df.columns:
        df["main_net"] = df["净额"].apply(_parse)
    else:
        df["main_net"] = df["main_inflow"] - df["main_outflow"]
    df["active_buy_ratio"] = df.apply(
        lambda r: r["main_inflow"] / (r["main_inflow"] + r["main_outflow"])
        if (r["main_inflow"] + r["main_outflow"]) > 0 else 0.5,
        axis=1,
    )
    df["change_pct"] = df["涨跌幅"].apply(_parse_pct)
    df["turnover"] = df["换手率"].apply(_parse_pct)
    df["price"] = df["最新价"].apply(lambda x: float(x) if x else 0.0)

    elapsed = time.time() - t0
    log(f"  全市场资金扫描: {len(df)} 只, 耗时 {elapsed:.1f}s")

    # 去掉无效行
    df = df[df["code6"].notna() & (df["code6"] != "")]
    # 去重（akshare 偶有重复行）
    before = len(df)
    df = df.drop_duplicates(subset=["code6"], keep="first")
    if len(df) < before:
        log(f"  (去重: {before} → {len(df)})")
    return df


# ── 3. 双轨评分 ──

def compute_momentum_z(df: pd.DataFrame) -> np.ndarray:
    """Cross-sectional z-score of momentum factors"""
    scores = np.zeros(len(df), dtype=float)

    for col, w in [
        ("main_net", W_MAIN_NET),
        ("active_buy_ratio", W_ACTIVE_BUY),
        ("change_pct", W_CHG_PCT),
        ("turnover", W_TURNOVER),
    ]:
        vals = df[col].values.astype(float)
        vals = np.where(np.isfinite(vals), vals, 0.0)
        mu = np.mean(vals)
        sigma = np.std(vals) + 1e-12
        scores += ((vals - mu) / sigma) * w

    return scores


def compute_icir_z(icir_alphas: np.ndarray) -> np.ndarray:
    """Cross-sectional z-score of ICIR alphas"""
    vals = np.where(np.isfinite(icir_alphas), icir_alphas, 0.0)
    mu = np.mean(vals)
    sigma = np.std(vals) + 1e-12
    return (vals - mu) / sigma


# ── 4. 门控链 ──

def apply_gates(
    df: pd.DataFrame,
    scores: np.ndarray,
    imap: dict,
    board_flow: dict[str, str],
    excluded: set[str],
    yjbb_map: dict[str, float],
    gc_pool: set[str],
) -> tuple[pd.DataFrame, np.ndarray]:
    """应用过滤门控链"""
    n0 = len(df)
    reasons: list[tuple[int, str]] = []  # (index, reason)

    for i in range(len(df)):
        sym = df.iloc[i]["code6"]
        reason = ""

        # 排除列表
        if sym in excluded:
            reason = "排除列表"

        # 硬剔除：跌幅超限
        if not reason:
            chg = float(df.iloc[i].get("change_pct", 0) or 0)
            if chg < HARD_DROP:
                reason = f"跌幅{chg:.1f}%(超{HARD_DROP:.0f}%)"

        # 业绩门：净利润同比大幅下降
        if not reason:
            profit_yoy = yjbb_map.get(sym)
            if profit_yoy is not None and profit_yoy < PROFIT_DECLINE_THRESHOLD:
                reason = f"净利同比{profit_yoy:+.1f}%"

        if reason:
            reasons.append((i, reason))

    # 标记剔除
    drop_indices = {r[0] for r in reasons}
    keep = [i for i in range(len(df)) if i not in drop_indices]
    if len(reasons) > 0:
        log(f"  门控剔除: {len(drop_indices)} 只")
        for idx, rsn in reasons[:5]:
            s = df.iloc[idx]
            log(f"    ❌ {s.get('name', '?')}({s.get('code6', '?')}) — {rsn}")

    df = df.iloc[keep].reset_index(drop=True)
    scores = scores[keep]

    # 板块级别加分降权（不剔除）
    for i in range(len(df)):
        sym = df.iloc[i]["code6"]
        sector = get_sector(sym, imap)
        tier = board_flow.get(sector, "")
        if tier == "prefer":
            scores[i] *= 1.05
        elif tier == "avoid":
            scores[i] *= 0.90

    # 启动池内标的额外加分
    for i in range(len(df)):
        sym = df.iloc[i]["code6"]
        if sym in gc_pool:
            scores[i] *= 1.03

    return df, scores


def enforce_sector_diversity(
    df: pd.DataFrame,
    scores: np.ndarray,
    imap: dict,
) -> tuple[pd.DataFrame, np.ndarray]:
    """按板块集中度限制重排序并截断"""
    # 按分数降序排列
    order = np.argsort(-scores)
    df = df.iloc[order].reset_index(drop=True)
    scores = scores[order]

    # 选择前 TOP_N 只，同时遵守 SECTOR_MAX_POOL
    sector_count: dict[str, int] = defaultdict(int)
    selected_indices = []

    for i in range(min(len(df), TOP_N * 2)):
        sym = df.iloc[i]["code6"]
        sector = get_sector(sym, imap)
        if sector_count[sector] >= SECTOR_MAX_POOL:
            continue
        sector_count[sector] += 1
        selected_indices.append(i)
        if len(selected_indices) >= TOP_N:
            break

    # 如果不够 TOP_N，补选
    if len(selected_indices) < TOP_N:
        for i in range(len(df)):
            if i not in selected_indices:
                selected_indices.append(i)
                if len(selected_indices) >= TOP_N:
                    break

    df = df.iloc[selected_indices].reset_index(drop=True)
    scores = scores[selected_indices]

    # 板块集中度日志
    log(f"  板块分布: {dict(sorted(sector_count.items(), key=lambda x: -x[1])[:8])}")
    return df, scores


# ── 5. 主入口 ──

def run_live_scan() -> int:
    """09:35 全市场动量扫描主入口"""
    log("=" * 60)
    log("09:35 全市场动量扫描 — 双轨评分 (ICIR + 实时资金流)")

    # ---- 1. 加载数据 ----
    log("1. 加载基础数据...")
    icir_map = load_icir_scores()
    imap = load_industry_map()
    board_flow = load_board_flow()
    excluded = load_excluded_symbols()
    gc_pool = load_gc_pool()
    yjbb_map = load_yjbb_map()

    log(f"  行业映射: {len(imap)} 只 | 排除列表: {len(excluded)} | 启动池: {len(gc_pool)}")

    # ---- 2. 全市场资金扫描 ----
    log("2. 全市场实时资金扫描（akshare免费）...")
    df = fetch_live_fund_flow()
    if df.empty:
        log("❌ 无实时资金数据")
        return 1

    # ---- 3. 双轨评分 ----
    log("3. 双轨评分...")

    # 动量分
    momentum_z = compute_momentum_z(df)
    momentum_z = np.where(np.isfinite(momentum_z), momentum_z, 0.0)

    # ICIR 分
    icir_alphas = np.array([
        icir_map.get(code, {}).get("icir_alpha", np.nan)
        for code in df["code6"]
    ], dtype=float)

    has_icir = np.isfinite(icir_alphas)
    icir_z = np.zeros(len(df), dtype=float)
    if has_icir.any():
        valid_icir = icir_alphas[has_icir]
        mu = np.mean(valid_icir)
        sigma = np.std(valid_icir) + 1e-12
        icir_z[has_icir] = (valid_icir - mu) / sigma

    # 融合评分
    final_scores = np.zeros(len(df), dtype=float)
    n_icir = 0
    n_new = 0
    for i in range(len(df)):
        if has_icir[i]:
            final_scores[i] = icir_z[i] * W_ICIR + momentum_z[i] * W_MOMENTUM
            n_icir += 1
        else:
            final_scores[i] = momentum_z[i] * NEW_STOCK_PENALTY
            n_new += 1

    log(f"  ICIR+动量融合: {n_icir} 只 | 仅动量(新票): {n_new} 只")

    # ---- 4. 门控链 ----
    log("4. 门控链...")
    df, final_scores = apply_gates(df, final_scores, imap, board_flow, excluded, yjbb_map, gc_pool)

    if df.empty:
        log("❌ 门控后为空")
        return 1

    # ---- 5. 板块分散 + 排序 ----
    log("5. 板块分散 + 排序...")
    df, final_scores = enforce_sector_diversity(df, final_scores, imap)

    # ---- 6. 组装输出 ----
    log("6. 组装结果...")
    run_time = datetime.now().isoformat()
    recommendations = []

    for i in range(len(df)):
        row = df.iloc[i]
        sym = row["code6"]
        name = row.get("name", "")
        icir_entry = icir_map.get(sym, {})
        sector = get_sector(sym, imap)
        gc_bonus = " 启动池" if sym in gc_pool else ""
        sector_tag = ""
        tier = board_flow.get(sector, "")
        if tier == "prefer":
            sector_tag = " +板块prefer"
        elif tier == "avoid":
            sector_tag = " -板块avoid"

        rec = {
            "symbol": sym,
            "name": name,
            "score": round(float(final_scores[i]), 4),
            "lgb_score": round(float(final_scores[i]), 4),
            "ml_score": round(float(final_scores[i]), 4),
            "momentum_score": round(float(momentum_z[i] if i < len(momentum_z) else 0), 4),
            "icir_alpha": round(float(icir_entry.get("icir_alpha", 0)), 4) if sym in icir_map else 0,
            "buy_price": float(row.get("price", 0) or 0),
            "target_price": float(icir_entry.get("target_price", 0) or 0),
            "stop_price": float(icir_entry.get("stop_price", 0) or 0),
            "change_pct": float(row.get("change_pct", 0) or 0),
            "main_net": float(row.get("main_net", 0) or 0),
            "active_buy_ratio": round(float(row.get("active_buy_ratio", 0) or 0), 4),
            "turnover": float(row.get("turnover", 0) or 0),
            "price": float(row.get("price", 0) or 0),
            "sector": sector,
            "industry_l1": sector,
            "in_gc_pool": sym in gc_pool,
            "has_icir": sym in icir_map,
            "sector_tag": sector_tag.strip() or "",
        }

        # 如果没有 icir 的 target/stop，从实时价格推算
        if rec["target_price"] <= 0 and rec["buy_price"] > 0:
            rec["target_price"] = round(rec["buy_price"] * 1.04, 2)
        if rec["stop_price"] <= 0 and rec["buy_price"] > 0:
            rec["stop_price"] = round(rec["buy_price"] * 0.97, 2)

        recommendations.append(rec)

    # ---- 7. 统计 ----
    n_elim_earnings = sum(
        1 for r in recommendations if r.get("change_pct", 0) < HARD_DROP
    )
    n_gc = sum(1 for r in recommendations if r.get("in_gc_pool"))
    n_new_picks = sum(1 for r in recommendations if not r.get("has_icir"))

    log(f"\n{'='*50}")
    log(f"✅ 扫描完成!")
    log(f"   推荐: {len(recommendations)} 只")
    log(f"   其中启动池标的: {n_gc} 只")
    log(f"   新发现(无ICIR): {n_new_picks} 只")
    log(f"   板块标注: {sum(1 for r in recommendations if r.get('sector_tag'))} 只有板块信号")
    log(f"\n🏆 Top {len(recommendations)} 推荐:")
    for i, r in enumerate(recommendations[:10], 1):
        tag = r.get("sector_tag", "") or ""
        gc = " 📦" if r.get("in_gc_pool") else ""
        new = " 🆕" if not r.get("has_icir") else ""
        log(f"   {i}. {r['name']}({r['symbol']}) score={r['score']:.4f}"
            f" chg={r['change_pct']:+.1f}%"
            f" net={r['main_net']/1e4:.0f}w"
            f" abr={r['active_buy_ratio']:.2f}"
            f" [{r['sector']}]{tag}{gc}{new}")

    # ---- 8. 写回 daily_recommend.json ----
    # 保留旧文件的元数据字段
    old_meta = {}
    if REC_PATH.exists():
        try:
            old = json.loads(REC_PATH.read_text(encoding="utf-8"))
            for k in ("live_rerank", "pre_market_gate", "earnings_gate", "stats", "env"):
                if k in old:
                    old_meta[k] = old[k]
        except Exception:
            pass

    output = {
        "run_at": run_time,
        "scanner": "live_momentum_scanner",
        "recommendations": recommendations,
        "live_momentum_scan": {
            "n_total_scanned": len(df),
            "n_final": len(recommendations),
            "n_icir_stocks": n_icir,
            "n_new_stocks": n_new,
            "n_gc_pool": n_gc,
            "scanned_at": run_time,
        },
        **old_meta,
    }

    REC_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"\n📁 写入: {REC_PATH} ({len(recommendations)} 只)")

    # ---- 9. 更新评分 Top10（无门槛榜）----
    try:
        _t0 = time.time()
        subprocess.check_call(
            [sys.executable, str(ROOT / "scripts/build_score_top10.py")],
            cwd=str(ROOT), timeout=120,
        )
        log(f"  ✅ score_top10 已更新（耗时 {time.time()-_t0:.1f}s）")
    except Exception as _e:
        log(f"  ⚠️ score_top10 更新跳过: {_e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(run_live_scan())
