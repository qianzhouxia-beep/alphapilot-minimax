#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
09:35 全市场动量扫描 — 双轨评分（ICIR + 实时资金流）

方案：
  05:00 管线保存全量 ICIR 分数（output/icir_all_scores.json）
  09:35 本脚本：
    - 管线候选 >=100：在 pipeline 池内叠加实时资金流重排（0.6 管线 + 0.4 动量）
    - 管线候选 <100：涨幅 Top~1000 资金轨（ICIR+动量+门控；弱市/降仓仍启用）
  09:35 akshare 资金流（失败则同花顺 zdf 降序分页，取 ~1000）
  合并：final = ICIR_z × 0.5 + momentum_z × 0.5
  新票（无 ICIR）：final = momentum_z × 0.9
  → 门控链 → Top N（默认 50）→ morning_live 资金门 → Top10/Top2

数据源（全部免费）：
  - akshare stock_fund_flow_individual：主力净额、主动买入比、涨跌幅、换手率
  - 同花顺 THS zdf desc 分页（akshare 失败时， intentional top~1000）
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
PIPELINE_MIN_CANDIDATES = int(os.getenv("PIPELINE_MIN_CANDIDATES", "100"))
MOMENTUM_TOP_N = int(os.getenv("MOMENTUM_TOP_N", "1000"))  # 09:35 资金轨：涨幅靠前 ~N 只
HARD_DROP = -5.0          # 跌超 5% 硬剔除
SECTOR_MAX_TOP10 = 2      # Top10 同板块最多 2 只
SECTOR_MAX_POOL = 4       # 全池同板块最多 4 只

# 动量因子权重
W_MAIN_NET = 0.35
W_ACTIVE_BUY = 0.25
W_CHG_PCT = 0.25
W_TURNOVER = 0.15

# 板块实时资金流加成（CapitalPulse 每 3 秒采集，读 data/sector_flow_realtime.sqlite3）
W_SECTOR_FLOW = float(os.getenv("W_SECTOR_FLOW", "0.10"))


def _load_feedback_params() -> dict[str, float]:
    """读 RD 调权输出 config/feedback_params.env（16:15 由 feedback_auto_tune 写入）。

    文件不存在/解析失败 → 空 dict，调用方回退默认权重，行为与未接线时完全一致。
    """
    p = ROOT / "config" / "feedback_params.env"
    out: dict[str, float] = {}
    try:
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                try:
                    out[k.strip()] = float(v.strip())
                except (TypeError, ValueError):
                    pass
    except Exception:
        pass
    return out


# ICIR 与动量融合权重（RD 反馈闭环自动调整；env 缺失时回退 0.50/0.50）
_FEEDBACK_PARAMS = _load_feedback_params()
W_ICIR = float(os.getenv("W_ICIR", _FEEDBACK_PARAMS.get("W_ICIR", 0.50)))
W_MOMENTUM = float(os.getenv("W_MOMENTUM", _FEEDBACK_PARAMS.get("W_MOMENTUM", 0.50)))
NEW_STOCK_PENALTY = 0.9   # 无 ICIR 的新票折价

# 季报业绩下降剔除阈值
PROFIT_DECLINE_THRESHOLD = -50


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _resolve_exposure_meta(old: dict | None = None) -> dict[str, Any]:
    """写回 recommend 时必须带仓位元数据；缺失会被 morning_live 误判为 nuclear=0。"""
    old = old or {}
    try:
        from market_env_gate import (
            load_or_build_env,
            position_exposure,
            recommend_pool_n,
            recommend_top_n,
        )
        from permission_gate import enrich_env_with_permission

        env = load_or_build_env(force=False)
        if env.get("exposure_mode") != "permission_v1":
            enrich_env_with_permission(env, asof=env.get("asof"))
        flags = env.get("flags") or {}
        expo = float(
            env.get("position_exposure", position_exposure(flags, env.get("permission")))
        )
        return {
            "asof": env.get("asof") or datetime.now().strftime("%Y-%m-%d"),
            "position_exposure": expo,
            "recommend_top_n": recommend_top_n(expo, default=2),
            "recommend_pool_n": recommend_pool_n(expo),
            "exposure_mode": env.get("exposure_mode") or "permission_v1",
            "market_env_flags": flags,
        }
    except Exception as e:
        log(f"  ⚠️ 仓位元数据刷新失败，回退旧值/默认: {e}")
        raw = old.get("position_exposure")
        try:
            expo = float(raw) if raw is not None else 1.0
        except (TypeError, ValueError):
            expo = 1.0
        return {
            "asof": old.get("asof") or datetime.now().strftime("%Y-%m-%d"),
            "position_exposure": expo,
            "recommend_top_n": int(
                old.get("recommend_top_n")
                if old.get("recommend_top_n") is not None
                else (0 if expo <= 0 else 2)
            ),
            "recommend_pool_n": int(old.get("recommend_pool_n") or TOP_N),
            "exposure_mode": old.get("exposure_mode") or "fallback_default",
            "market_env_flags": old.get("market_env_flags")
            if isinstance(old.get("market_env_flags"), dict)
            else {},
        }


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


def get_sector_l2(sym: str, imap: dict) -> str:
    """个股所属申万二级行业（CapitalPulse 板块快照口径），缺失回退一级。"""
    meta = imap.get(_bare(sym), {})
    if isinstance(meta, dict):
        return meta.get("industry_l2") or meta.get("industry_l1") or "其他"
    return "其他"


_CAP_PULSE_DB = ROOT / "data" / "sector_flow_realtime.sqlite3"


def load_capitalpulse_sector_flow() -> dict[str, float]:
    """读取 CapitalPulse 各板块最新实时主力净额 {板块名: main_net}。

    CapitalPulse 采集器每 3 秒全量更新 30 个申万二级行业；数据缺失/异常时
    返回空 dict（调用方按中性 0 处理，不阻断选股）。
    """
    if not _CAP_PULSE_DB.exists():
        return {}
    try:
        import sqlite3
        from datetime import date, datetime, timedelta, timezone
        cst = timezone(timedelta(hours=8))
        today = datetime.now(cst).date().isoformat()
        conn = sqlite3.connect(f"file:{_CAP_PULSE_DB}?mode=ro", uri=True, timeout=3)
        try:
            # 今日无数据（跨零点/采集器未滚日）时回退到库内最新交易日
            avail = conn.execute(
                "SELECT DISTINCT trade_date FROM sector_flow_snapshot ORDER BY trade_date DESC LIMIT 3"
            ).fetchall()
            dates = [str(r[0]) for r in avail]
            target = today if today in dates else (dates[0] if dates else "")
            if not target:
                return {}
            rows = conn.execute(
                """
                SELECT s.sector_code, s.sector_name, s.main_net
                FROM sector_flow_snapshot s
                INNER JOIN (
                    SELECT sector_code, MAX(source_time) AS source_time
                    FROM sector_flow_snapshot
                    WHERE trade_date = ?
                    GROUP BY sector_code
                ) latest
                    ON latest.sector_code = s.sector_code
                   AND latest.source_time = s.source_time
                WHERE s.trade_date = ?
                """,
                (target, target),
            ).fetchall()
        finally:
            conn.close()
        return {str(r[1]): float(r[2] or 0) for r in rows if r[1]}
    except Exception as e:  # noqa: BLE001
        log(f"⚠️ CapitalPulse 板块资金流读取失败(忽略): {e}")
        return {}


def sector_flow_z_by_stock(
    imap: dict,
    sector_flow: dict[str, float],
) -> dict[str, float]:
    """把板块实时主力净额转成截面 z，返回 {code6: sector_z}。

    以全市场股票（industry_map 全集）按所属板块 main_net 做截面标准化；
    候选池内无板块数据的股票得 0（中性）。
    """
    if not sector_flow:
        return {}
    per_stock = {}
    for sym, meta in imap.items():
        bare = _bare(sym)
        l2 = ""
        if isinstance(meta, dict):
            l2 = meta.get("industry_l2") or meta.get("industry_l1") or ""
        if l2 in sector_flow:
            per_stock[bare] = float(sector_flow[l2])
    if not per_stock:
        return {}
    vals = np.array(list(per_stock.values()), dtype=float)
    mu = float(np.mean(vals))
    sd = float(np.std(vals)) + 1e-12
    return {sym: (v - mu) / sd for sym, v in per_stock.items()}


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

_THS_COLS_10 = [
    "序号",
    "股票代码",
    "股票简称",
    "最新价",
    "涨跌幅",
    "换手率",
    "流入资金",
    "流出资金",
    "净额",
    "成交额",
]


def _fetch_ths_fund_flow_raw(max_rows: int | None = None) -> pd.DataFrame:
    """Scrape THS fund flow (zdf desc). max_rows stops early for top-N intentional pool."""
    import requests
    from bs4 import BeautifulSoup
    from akshare.utils.tqdm import get_tqdm
    from akshare.stock_feature.stock_fund_flow import _get_file_content_ths
    from py_mini_racer import MiniRacer

    def _headers() -> dict:
        js_code = MiniRacer()
        js_code.eval(_get_file_content_ths("ths.js"))
        return {
            "Accept": "text/html, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "hexin-v": js_code.call("v"),
            "Host": "data.10jqka.com.cn",
            "Referer": "http://data.10jqka.com.cn/funds/ggzjl/",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "X-Requested-With": "XMLHttpRequest",
        }

    url0 = "http://data.10jqka.com.cn/funds/ggzjl/field/code/order/desc/ajax/1/free/1/"
    r = requests.get(url0, headers=_headers(), timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, features="lxml")
    page_info = soup.find(name="span", attrs={"class": "page_info"})
    if page_info is None:
        raise RuntimeError("ths fund flow: page_info missing")
    page_num = int(str(page_info.text).split("/")[1])
    url_tpl = "http://data.10jqka.com.cn/funds/ggzjl/field/zdf/order/desc/page/{}/ajax/1/free/1/"

    frames = []
    tqdm = get_tqdm()
    for page in tqdm(range(1, page_num + 1), leave=False):
        rr = requests.get(url_tpl.format(page), headers=_headers(), timeout=20)
        rr.raise_for_status()
        tables = pd.read_html(rr.text)
        if not tables:
            continue
        frames.append(tables[0])
        if max_rows is not None:
            n_so_far = sum(len(f) for f in frames)
            if n_so_far >= max_rows:
                break
    if not frames:
        raise RuntimeError("ths fund flow: empty tables")
    big = pd.concat(frames, ignore_index=True)
    n = int(big.shape[1])
    if n >= 10:
        big = big.iloc[:, :10].copy()
        big.columns = _THS_COLS_10
    else:
        big.columns = _THS_COLS_10[:n]
        for c in _THS_COLS_10[n:]:
            big[c] = None
    return big


def _normalize_fund_flow_df(df: pd.DataFrame) -> pd.DataFrame:
    """Standardize akshare/THS raw fund-flow columns to code6/main_net/change_pct/..."""
    df = df.copy()
    df["code6"] = df["股票代码"].map(_bare)
    df["name"] = df["股票简称"]

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

    # Junk defense: column drift can poison chg/abr (e.g. chg=273, abr=22298681).
    df.loc[(df["change_pct"] < -30) | (df["change_pct"] > 30), "change_pct"] = 0.0
    df.loc[(df["active_buy_ratio"] < 0) | (df["active_buy_ratio"] > 1), "active_buy_ratio"] = 0.5
    return df


def fetch_momentum_top1000() -> pd.DataFrame:
    """Intentional 09:35 momentum pool: top ~MOMENTUM_TOP_N by change_pct (zdf desc).

    Used when 05:00 pipeline pool is small (< PIPELINE_MIN_CANDIDATES).
    Weak market / reduced exposure does NOT disable this path (intraday fund flow).
    """
    import akshare as ak

    t0 = time.time()
    top_n = MOMENTUM_TOP_N
    df = None
    last_err: Exception | None = None
    source = "akshare"
    for attempt in range(1, 4):
        try:
            cand = ak.stock_fund_flow_individual(symbol="即时")
            if cand is not None and not cand.empty and "股票代码" in cand.columns:
                df = cand
                break
            last_err = RuntimeError("akshare returned empty/unexpected columns")
        except Exception as e:
            last_err = e
            log(f"  akshare 资金流失败 attempt={attempt}: {type(e).__name__}: {e}")
            time.sleep(1.2 * attempt)

    if df is None or df.empty or "股票代码" not in getattr(df, "columns", []):
        log(f"  THS zdf-desc 分页（top~{top_n}，原因: {last_err}）")
        source = "ths_zdf_desc"
        df = _fetch_ths_fund_flow_raw(max_rows=top_n + 200)

    df = _normalize_fund_flow_df(df)
    df = df[df["code6"].notna() & (df["code6"] != "")]
    raw_n = len(df)
    df = df.sort_values("change_pct", ascending=False)
    df = df.drop_duplicates(subset=["code6"], keep="first").head(top_n).reset_index(drop=True)

    elapsed = time.time() - t0
    log(
        f"  momentum_top{top_n} [{source}]: raw={raw_n} "
        f"dedup_top={len(df)} elapsed={elapsed:.1f}s"
    )
    return df


def fetch_live_fund_flow() -> pd.DataFrame:
    """Full-universe fund flow for pipeline-pool rerank z-score baseline (akshare/THS)."""
    import akshare as ak

    t0 = time.time()
    df = None
    last_err: Exception | None = None
    for attempt in range(1, 4):
        try:
            cand = ak.stock_fund_flow_individual(symbol="即时")
            if cand is not None and not cand.empty and "股票代码" in cand.columns:
                df = cand
                break
            last_err = RuntimeError("akshare returned empty/unexpected columns")
        except Exception as e:
            last_err = e
            log(f"  akshare 资金流失败 attempt={attempt}: {type(e).__name__}: {e}")
            time.sleep(1.2 * attempt)

    if df is None or df.empty or "股票代码" not in getattr(df, "columns", []):
        log(f"  切换鲁棒同花顺抓取（原因: {last_err})")
        df = _fetch_ths_fund_flow_raw()

    df = _normalize_fund_flow_df(df)

    elapsed = time.time() - t0
    log(f"  全市场资金扫描: {len(df)} 只, 耗时 {elapsed:.1f}s")

    df = df[df["code6"].notna() & (df["code6"] != "")]
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
    """
    09:35 扫描入口（2026-07-31 重构）

    新方案（统一评分来源）：
      05:00 漏斗候选池 N 只（不固定）→ daily_recommend.json
      09:25 竞价门控写回同一池
      09:35 在 N 只内叠加实时资金流重排 → Top50 供 morning_live
    """
    log("=" * 60)
    log("09:35 管线候选重排 — 在 05:00 漏斗池内叠加实时资金流")

    # ── 0. 加载 05:00 pipeline 候选池（=已过全部门控的 500 只）──
    if not REC_PATH.exists():
        log(f"❌ {REC_PATH} 不存在，管线候选池不可用")
        return _momentum_top1000_scan(None)

    try:
        pipeline = json.loads(REC_PATH.read_text(encoding="utf-8"))
        # 优先用 scanner 上一轮写入的完整候选池（morning_live 会截断 recommendations）
        candidates = pipeline.get("full_candidate_pool") or pipeline.get("recommendations", [])
    except Exception as e:
        log(f"❌ 读取 {REC_PATH} 失败: {e}")
        return _momentum_top1000_scan(None)

    # ── 0b. 评分质量门控（宁可不操作）：pipeline 已标记 NO_TRADE → 当天不选股 ──
    _q = pipeline.get("_quality") or {}
    if _q.get("ok") is False:
        log(f"❌ 质量门控: {_q.get('reason')}")
        log("❌ 今日评分异常（NO_TRADE）→ 当天不选股，宁可不操作")
        return 0

    log(f"  管线候选池: {len(candidates)} 只")
    if len(candidates) < PIPELINE_MIN_CANDIDATES:
        log(
            f"⚠️ 管线候选 {len(candidates)} 只 < {PIPELINE_MIN_CANDIDATES} "
            f"→ 涨幅 Top{MOMENTUM_TOP_N} 资金轨"
        )
        log(
            "  （当日资金/动量优先；弱市/降仓仍启用，不因前几日大盘弱而跳过）"
        )
        return _momentum_top1000_scan(pipeline)

    # 构建 pipeline 候选索引
    pipe_map = {}  # code6 → candidate dict
    for c in candidates:
        sym = str(c.get("symbol", ""))
        pipe_map[sym] = c

    # ── 1. 加载辅助数据 ──
    log("1. 加载辅助数据...")
    imap = load_industry_map()
    board_flow = load_board_flow()
    excluded = load_excluded_symbols()
    log(f"  行业映射: {len(imap)} 只 | 排除列表: {len(excluded)}")

    # ── 2. 全市场资金扫描（需要全市场 5000 只做 z-score 标准化）──
    log("2. 全市场实时资金扫描（akshare）...")
    df = fetch_live_fund_flow()
    if df.empty:
        log("❌ 无实时资金数据")
        return 1

    # ── 3. 计算全市场动量 z-score ──
    log("3. 全市场动量 z-score（作标准化基准）...")
    momentum_z = compute_momentum_z(df)
    momentum_z = np.where(np.isfinite(momentum_z), momentum_z, 0.0)
    df["_momentum_z"] = momentum_z
    df["code6"] = df["code6"].astype(str)

    # 建立 code6 → fund_flow_row 的快速查找
    df_index = df.set_index("code6")

    # ── 4. 对 pipeline 500 只叠加实时资金流重排 ──
    log("4. 融合评分: pipeline_z × 0.6 + 实时动量 z × 0.4 + 板块实时资金 z × 0.1")
    PIPELINE_W = 0.6
    MOMENTUM_W = 0.4

    # 板块实时主力净额加成（CapitalPulse 每 3s 采集，缺失时中性 0）
    sector_flow = load_capitalpulse_sector_flow()
    sector_z = sector_flow_z_by_stock(imap, sector_flow)
    log(f"  CapitalPulse 板块实时资金流: {len(sector_flow)} 板块 / {len(sector_z)} 只命中")

    # pipeline_score 是 0~1 绝对分；先做 z-score 标准化，恢复与历史一致的无界口径
    pipe_scores = [float(c.get("score", 0) or 0) for c in pipe_map.values()]
    pipe_mu = float(np.mean(pipe_scores)) if pipe_scores else 0.0
    pipe_sd = float(np.std(pipe_scores)) + 1e-12
    pipe_z = {
        sym: (float(c.get("score", 0) or 0) - pipe_mu) / pipe_sd
        for sym, c in pipe_map.items()
    }

    reranked = []
    n_with_fundflow = 0
    n_no_fundflow = 0
    for sym, cand in pipe_map.items():
        base_score = float(cand.get("score", 0) or 0)
        base_z = pipe_z.get(sym, 0.0)
        # 注意: 必须用 loc + index membership，不能 df_index.get(sym)（那是取列不是取行）
        row = df_index.loc[sym] if sym in df_index.index else None
        if row is not None and not row.isna().all():
            mz = float(row["_momentum_z"]) if not pd.isna(row.get("_momentum_z", np.nan)) else 0.0
            merge_score = base_z * PIPELINE_W + mz * MOMENTUM_W
            # 注入实时数据
            cand["change_pct"] = float(row.get("change_pct", 0) or 0)
            cand["main_net"] = float(row.get("main_net", 0) or 0)
            cand["active_buy_ratio"] = round(float(row.get("active_buy_ratio", 0) or 0), 4)
            cand["turnover"] = float(row.get("turnover", 0) or 0)
            cand["price"] = float(row.get("price", 0) or 0)
            cand["_live_momentum_z"] = round(float(mz), 4)
            n_with_fundflow += 1
        else:
            # 无资金流数据：保留管线 z-score，避免系统性 ×0.6 压缩
            merge_score = base_z
            cand["_live_momentum_z"] = 0.0
            n_no_fundflow += 1

        # 板块实时资金流加成（软加分，不改变门控）
        sz = sector_z.get(sym, 0.0)
        if sz:
            merge_score += float(sz) * W_SECTOR_FLOW
            cand["_sector_flow_z"] = round(float(sz), 4)
        else:
            cand["_sector_flow_z"] = 0.0

        cand["score"] = round(float(merge_score), 4)
        cand["_pipeline_base_score"] = round(float(base_score), 4)
        cand["_pipeline_z"] = round(float(base_z), 4)

        if sym not in excluded:
            reranked.append(cand)

    reranked.sort(key=lambda x: -float(x.get("score") or 0))
    log(f"  管线池: {n_with_fundflow} 只有实时资金流, {n_no_fundflow} 只无")

    # ── 5. 近涨停过滤 ──
    log("5. 近涨停过滤 + 板块分散...")
    top50 = []
    for r in reranked:
        if len(top50) >= TOP_N:
            break
        chg = r.get("change_pct")
        if chg is not None:
            try:
                chg_f = float(chg)
                if abs(chg_f) > 1:
                    chg_f /= 100.0
                sym = r.get("symbol", "")
                lim = 0.20 if (sym and sym.startswith(("300", "301", "688"))) else 0.10
                if chg_f >= lim * 0.97:
                    continue
            except Exception:
                pass
        top50.append(r)

    # 板块分散
    top50 = _diversify(top50, imap)

    recommendations = top50
    run_time = datetime.now().isoformat()

    # ── 6. 统计日志 ──
    n_gc = sum(1 for r in recommendations if r.get("in_gc_pool"))
    n_pipeline_boost = sum(1 for r in recommendations if r.get("_pipeline_base_score", 0) > 0)
    log(f"\n{'='*50}")
    log(f"✅ 管线候选重排完成!")
    log(f"   推荐: {len(recommendations)} 只")
    log(f"   来自 05:00 管线池: {n_pipeline_boost} 只")
    log(f"   属启动池: {n_gc} 只")
    log(f"\n🏆 Top10:")
    for i, r in enumerate(recommendations[:10], 1):
        sz = r.get("sector", "")
        gc = " 📦" if r.get("in_gc_pool") else ""
        log(f"   {i}. {r.get('name','?')}({r.get('symbol','?')}) score={r.get('score',0):.4f}"
            f" pipeline={r.get('_pipeline_base_score',0):.4f}"
            f" live_z={r.get('_live_momentum_z',0):.4f}"
            f" chg={r.get('change_pct',0):+.1f}%"
            f" [{sz}]{gc}")

    # ── 7. 写回 daily_recommend.json ──
    # 保留旧元数据（竞价门控等）
    old_meta = {}
    for k in ("pre_market_gate", "earnings_gate", "stats", "env"):
        if k in pipeline:
            old_meta[k] = pipeline[k]

    expo_meta = _resolve_exposure_meta(pipeline)
    # ── ST/退市风险警示硬过滤（2026-08-25 事故：*ST威领被 Track B 买入）──
    def _st(nm):
        u = str(nm or "").upper()
        return "ST" in u or u.startswith("退") or "退市" in u
    st_recs = [r for r in recommendations if _st(r.get("name"))]
    if st_recs:
        recommendations = [r for r in recommendations if not _st(r.get("name"))]
        log(f"⚠️ ST/退市硬过滤剔除 {len(st_recs)} 只: "
            + ", ".join(f"{r.get('name')}({r.get('symbol')})" for r in st_recs[:10]))
    pool_filt = [r for r in reranked[:500] if not _st(r.get("name"))]
    output = {
        "run_at": run_time,
        "scanner": "live_momentum_scanner_pipeline_rerank",
        "protocol": "live_momentum_from_pipeline_500",
        "recommendations": recommendations,
        "full_candidate_pool": pool_filt,  # 保留完整池供 debug
        "live_momentum_scan": {
            "n_pipeline_candidates": len(candidates),
            "n_with_fundflow": n_with_fundflow,
            "n_final": len(recommendations),
            "scanned_at": run_time,
            "top_n": TOP_N,
            "blend": {"pipeline_w": PIPELINE_W, "momentum_w": MOMENTUM_W},
        },
        **old_meta,
        **expo_meta,
    }

    REC_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"\n📁 写入: {REC_PATH} ({len(recommendations)} 只) expo={expo_meta.get('position_exposure')}")

    # ── 8. 更新评分 Top10 ──
    try:
        _t0 = time.time()
        subprocess.check_call(
            [sys.executable, str(ROOT / "scripts/build_score_top10.py")],
            cwd=str(ROOT), timeout=120,
        )
        log(f"  ✅ score_top10 已更新（耗时 {time.time()-_t0:.1f}s）")
    except Exception:
        pass

    return 0


def _momentum_top1000_scan(old_pipeline: dict | None) -> int:
    """09:35 momentum fund path when pipeline pool is small.

    Intentional top ~MOMENTUM_TOP_N by change_pct (not full 5000 scan).
    ICIR + intraday momentum scoring, gates, sector diversity, near-limit filter.
    Weak/reduced exposure does NOT disable this path.
    """
    log("=" * 50)
    log(f"▶ 涨幅 Top{MOMENTUM_TOP_N} 资金轨（pipeline 池过小， intentional momentum scan）")
    icir_map = load_icir_scores()
    imap = load_industry_map()
    board_flow = load_board_flow()
    excluded = load_excluded_symbols()
    gc_pool = load_gc_pool()
    yjbb_map = load_yjbb_map()

    df = fetch_momentum_top1000()
    if df.empty:
        return 1

    momentum_z = compute_momentum_z(df)
    momentum_z = np.where(np.isfinite(momentum_z), momentum_z, 0.0)

    icir_alphas = np.array([icir_map.get(code, {}).get("icir_alpha", np.nan) for code in df["code6"]], dtype=float)
    has_icir = np.isfinite(icir_alphas)
    icir_z = np.zeros(len(df), dtype=float)
    if has_icir.any():
        mu = np.mean(icir_alphas[has_icir])
        sg = np.std(icir_alphas[has_icir]) + 1e-12
        icir_z[has_icir] = (icir_alphas[has_icir] - mu) / sg

    final = np.zeros(len(df), dtype=float)
    for i in range(len(df)):
        final[i] = (icir_z[i] * W_ICIR + momentum_z[i] * W_MOMENTUM) if has_icir[i] else momentum_z[i] * NEW_STOCK_PENALTY

    df, final = apply_gates(df, final, imap, board_flow, excluded, yjbb_map, gc_pool)
    if df.empty:
        return 1
    df, final = enforce_sector_diversity(df, final, imap)

    recommendations = []
    _limit_dropped = 0
    _new_dropped = 0
    _v1_dropped = 0
    # 新股：kline 有效交易日 < 60（无 list_date 时的代理）
    _bars_map = {}
    _vp_feats = {}
    try:
        import pandas as _pd
        from pathlib import Path as _P
        _kp = _P(__file__).resolve().parent / "data" / "kline_cache" / "kline_all.parquet"
        if _kp.exists() and len(df) > 0:
            _codes = [str(c).zfill(6)[-6:] for c in df["code6"].tolist()]
            _k = _pd.read_parquet(_kp, columns=["symbol", "date"])
            _k["symbol"] = _k["symbol"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(6).str[-6:]
            _k = _k[_k["symbol"].isin(set(_codes))]
            _bars_map = _k.groupby("symbol").size().to_dict()
    except Exception as _e:
        log(f"  [momentum_top] 新股bar计数跳过: {_e}")
    try:
        from vp_factors import batch_factors_for_symbols

        _vp_feats = batch_factors_for_symbols(
            [str(c).zfill(6)[-6:] for c in df["code6"].tolist()]
        )
    except Exception as _e:
        log(f"  [momentum_top] V1 因子跳过: {_e}")

    for i in range(len(df)):
        row = df.iloc[i]
        sym = str(row["code6"]).zfill(6)[-6:]
        chg_raw = float(row.get("change_pct", 0) or 0)
        chg_f = chg_raw
        if abs(chg_f) > 1:
            chg_f /= 100.0
        lim = 0.20 if (sym and sym.startswith(("300", "301", "688"))) else 0.10
        if chg_f >= lim * 0.97:
            _limit_dropped += 1
            continue
        n_bars = int(_bars_map.get(sym) or 0)
        if n_bars and n_bars < 60:
            _new_dropped += 1
            continue
        _vf = _vp_feats.get(sym) or {}
        if _vf.get("v1_hit") and not bool(row.get("in_gc_pool")):
            _v1_dropped += 1
            continue
        rec = {
            "symbol": sym, "name": row.get("name", ""),
            "score": round(float(final[i]), 4),
            # RD 反馈闭环排序输入（feedback_auto_tune 16:15 用这两个算因子 IC）
            "_icir_z": round(float(icir_z[i]), 4),
            "_momentum_z": round(float(momentum_z[i]), 4),
            "change_pct": chg_raw,
            "main_net": float(row.get("main_net", 0) or 0),
            "price": float(row.get("price", 0) or 0),
            "sector": get_sector(sym, imap),
        }
        if _vf.get("v1_hit"):
            rec["vp_v1_hit"] = True
        if "ST" in str(rec.get("name") or "").upper() \
                or str(rec.get("name") or "").startswith("退") \
                or "退市" in str(rec.get("name") or ""):
            continue
        recommendations.append(rec)
    log(
        f"  [momentum_top{MOMENTUM_TOP_N}] 过滤剔除: 近涨停={_limit_dropped} "
        f"新股(<60bar)={_new_dropped} V1放量追涨={_v1_dropped}"
    )

    run_time = datetime.now().isoformat()
    expo_meta = _resolve_exposure_meta(old_pipeline or {})
    old_meta = {}
    if old_pipeline:
        for k in ("pre_market_gate", "earnings_gate", "stats", "env"):
            if k in old_pipeline:
                old_meta[k] = old_pipeline[k]

    output = {
        "run_at": run_time,
        "scanner": "live_momentum_scanner_momentum_top1000",
        "protocol": "momentum_top1000_fund_flow",
        "recommendations": recommendations,
        "full_candidate_pool": recommendations,
        "live_momentum_scan": {
            "n_final": len(recommendations),
            "scanned_at": run_time,
            "momentum_top_n": MOMENTUM_TOP_N,
            "pipeline_candidates": len(
                (old_pipeline or {}).get("full_candidate_pool")
                or (old_pipeline or {}).get("recommendations")
                or []
            ),
            "intentional": True,
        },
        **old_meta,
        **expo_meta,
    }
    REC_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"\n📁 momentum_top{MOMENTUM_TOP_N} 写入: {REC_PATH} ({len(recommendations)} 只) expo={expo_meta.get('position_exposure')}")

    try:
        _t0 = time.time()
        subprocess.check_call(
            [sys.executable, str(ROOT / "scripts/build_score_top10.py")],
            cwd=str(ROOT), timeout=120,
        )
        log(f"  ✅ score_top10 已更新（耗时 {time.time()-_t0:.1f}s）")
    except Exception:
        pass

    return 0


def _fallback_full_scan() -> int:
    """Backward-compatible alias for _momentum_top1000_scan."""
    return _momentum_top1000_scan(None)


def _diversify(items: list, imap: dict) -> list:
    """简单板块分散: Top10 同板块 ≤2, 全池 ≤4"""
    from collections import defaultdict
    counts: dict[str, int] = defaultdict(int)
    result = []
    for it in items:
        sym = it.get("symbol", "")
        sector = get_sector(sym, imap)
        pos = len(result)
        limit = 2 if pos < 10 else 4
        if counts[sector] >= limit:
            continue
        counts[sector] += 1
        result.append(it)
        if len(result) >= TOP_N:
            break
    return result


if __name__ == "__main__":
    raise SystemExit(run_live_scan())
