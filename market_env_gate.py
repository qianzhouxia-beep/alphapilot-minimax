#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""大盘 / 科技板环境门控（多日趋势）。

已有 sector_gate.py 只做行业 ±3% 软调权，不看指数。
本模块补上：
  1) 用多日涨跌判断上证/深成/创业板/科创50是否持续走弱
  2) 走弱板对应股票：降分；严重走弱：硬过滤（尽量不选）

指数源：东财 push2his（上海机可用）
  上证 1.000001 / 深成 0.399001 / 创业板 0.399006 / 科创50 1.000688
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent
CACHE_PATH = ROOT / "output" / "market_env_snapshot.json"

INDEXES = {
    "sh_main": {"name": "上证指数", "secid": "1.000001"},
    "sz_main": {"name": "深证成指", "secid": "0.399001"},
    "chinext": {"name": "创业板指", "secid": "0.399006"},
    "star50": {"name": "科创50", "secid": "1.000688"},
}

S = requests.Session()
S.trust_env = False
S.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://quote.eastmoney.com/",
    }
)


def _bare(sym: str) -> str:
    s = str(sym or "").lower().replace("sh", "").replace("sz", "").replace("bj", "")
    return s[-6:]


def stock_board(symbol: str) -> str:
    """返回股票所属环境桶：chinext / star50 / main。"""
    c = _bare(symbol)
    if c.startswith(("300", "301")):
        return "chinext"
    if c.startswith("688"):
        return "star50"
    return "main"


def _parse_em_klines(rows: list) -> list[dict]:
    out = []
    for row in rows:
        p = str(row).split(",")
        if len(p) < 11:
            continue
        try:
            out.append(
                {
                    "date": p[0][:10],
                    "open": float(p[1]),
                    "close": float(p[2]),
                    "high": float(p[3]),
                    "low": float(p[4]),
                    "change_pct": float(p[8]),
                }
            )
        except Exception:
            continue
    return out


def fetch_index_klines_em(secid: str, lmt: int = 30) -> list[dict]:
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": secid,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": 101,
        "fqt": 1,
        "end": "20500101",
        "lmt": lmt,
    }
    last_err = None
    for attempt in range(3):
        try:
            r = S.get(url, params=params, timeout=15)
            r.raise_for_status()
            rows = (r.json().get("data") or {}).get("klines") or []
            out = _parse_em_klines(rows)
            if out:
                return out
        except Exception as e:
            last_err = e
            time.sleep(0.4 * (attempt + 1))
    if last_err:
        raise last_err
    return []


def fetch_index_klines_sina(symbol: str, lmt: int = 30) -> list[dict]:
    """新浪指数日K：symbol 如 sh000001 / sz399006。"""
    url = (
        "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        f"CN_MarketData.getKLineData?symbol={symbol}&scale=240&ma=no&datalen={lmt}"
    )
    r = S.get(url, headers={**S.headers, "Referer": "https://finance.sina.com.cn"}, timeout=15)
    r.raise_for_status()
    arr = r.json()
    if not isinstance(arr, list):
        return []
    out = []
    prev = None
    for row in arr:
        try:
            close = float(row["close"])
            day = str(row["day"])[:10]
            chg = 0.0 if prev is None or prev <= 0 else (close / prev - 1.0) * 100
            out.append(
                {
                    "date": day,
                    "open": float(row["open"]),
                    "close": close,
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "change_pct": round(chg, 2),
                }
            )
            prev = close
        except Exception:
            continue
    return out


# 东财 secid → 新浪指数代码
SINA_SYMBOL = {
    "1.000001": "sh000001",
    "0.399001": "sz399001",
    "0.399006": "sz399006",
    "1.000688": "sh000688",
}


def fetch_index_klines(secid: str, lmt: int = 30) -> list[dict]:
    try:
        out = fetch_index_klines_em(secid, lmt=lmt)
        if out:
            return out
    except Exception:
        pass
    sina = SINA_SYMBOL.get(secid)
    if sina:
        return fetch_index_klines_sina(sina, lmt=lmt)
    return []


def _trend_from_klines(kl: list[dict]) -> dict:
    if not kl:
        return {
            "ok": False,
            "ret_3d": 0.0,
            "ret_5d": 0.0,
            "ret_10d": 0.0,
            "day_chg": 0.0,
            "below_ma10": False,
            "weak": False,
            "severe": False,
            "last_close": None,
            "last_date": None,
        }
    closes = [x["close"] for x in kl]
    chgs = [x["change_pct"] for x in kl]

    def sum_last(n):
        return float(sum(chgs[-n:])) if len(chgs) >= n else float(sum(chgs))

    ret_3d = sum_last(3)
    ret_5d = sum_last(5)
    ret_10d = sum_last(10)
    day_chg = float(chgs[-1]) if chgs else 0.0
    ma10 = sum(closes[-10:]) / min(10, len(closes))
    below_ma10 = closes[-1] < ma10

    # 持续走弱：5日与10日同为负，或跌破MA10且近5日为负
    weak = (ret_5d <= -2.0 and ret_10d <= -1.0) or (below_ma10 and ret_5d <= -1.0)
    # 严重走弱：多日趋势明显下行
    severe = (ret_5d <= -5.0 and ret_10d <= -3.0) or (ret_3d <= -4.0 and ret_5d <= -4.0)

    return {
        "ok": True,
        "ret_3d": round(ret_3d, 2),
        "ret_5d": round(ret_5d, 2),
        "ret_10d": round(ret_10d, 2),
        "day_chg": round(day_chg, 2),
        "below_ma10": bool(below_ma10),
        "weak": bool(weak),
        "severe": bool(severe),
        "last_close": closes[-1],
        "last_date": kl[-1]["date"],
    }


# 科技风格行业（通达信 L1）：科技指数严重走弱时硬剔除
TECH_INDUSTRY_L1 = frozenset({"电子", "计算机", "通信", "传媒", "国防军工"})


def _flags_from_indexes(indexes: dict) -> dict:
    tech_weak = bool(indexes.get("chinext", {}).get("weak") or indexes.get("star50", {}).get("weak"))
    tech_severe = bool(indexes.get("chinext", {}).get("severe") or indexes.get("star50", {}).get("severe"))
    market_weak = bool(indexes.get("sh_main", {}).get("weak") and indexes.get("sz_main", {}).get("weak"))
    market_severe = bool(
        indexes.get("sh_main", {}).get("severe") and indexes.get("sz_main", {}).get("severe")
    )
    # 当日瀑布：上证+深成同日跌幅均 ≤ -2%（与 T+1 协议配套的 nuclear 条件）
    sh_day = indexes.get("sh_main", {}).get("day_chg")
    sz_day = indexes.get("sz_main", {}).get("day_chg")
    try:
        market_crash_day = (
            sh_day is not None
            and sz_day is not None
            and float(sh_day) <= -2.0
            and float(sz_day) <= -2.0
        )
    except (TypeError, ValueError):
        market_crash_day = False
    return {
        "tech_weak": tech_weak,
        "tech_severe": tech_severe,
        "market_weak": market_weak,
        "market_severe": market_severe,
        "market_crash_day": bool(market_crash_day),
    }


def position_exposure_legacy(flags: dict | None) -> float:
    """旧口径：market_severe → 空仓（OOS 对照 A1_cur）。"""
    f = flags or {}
    if f.get("market_severe"):
        return 0.0
    if f.get("market_weak") or f.get("tech_severe"):
        return 0.5
    return 1.0


def position_exposure_ladder(flags: dict | None) -> float:
    """仓位阶梯 v2：severe+crash→0；severe→0.25；weak/tech→0.5；其余 1.0。"""
    f = flags or {}
    if f.get("market_severe") and f.get("market_crash_day"):
        return 0.0
    if f.get("market_severe"):
        return 0.25
    if f.get("market_weak") or f.get("tech_severe"):
        return 0.5
    return 1.0


def position_exposure(flags: dict | None, permission: dict | None = None) -> float:
    """生产默认：有 permission 快照时走许可门；否则回退阶梯 v2。"""
    if permission is not None:
        from permission_gate import position_exposure_permission

        return position_exposure_permission(flags, permission)
    # env 里可能已写入 permission_on 等，但无完整 up3 时仍用阶梯
    return position_exposure_ladder(flags)


def recommend_top_n(expo: float, default: int = 2) -> int:
    """下单主臂只数：薄仓 Top1，半仓/满仓 Top2，空仓 0。

    注意：展示/缓存池用 recommend_pool_n（薄仓保留 Top10），
    本函数只约束 paper / 实盘信号条数。
    """
    try:
        e = float(expo)
    except (TypeError, ValueError):
        e = 1.0
    if e <= 0:
        return 0
    if e < 0.5:
        return 1
    return int(default)


def recommend_pool_n(
    expo: float,
    *,
    thin_pool: int = 10,
    normal_pool: int = 50,
    default_trade: int = 2,
) -> int:
    """推荐池保留只数：薄仓 Top10（下单仍 Top1）；半仓/满仓 Top50；空仓 0。"""
    try:
        e = float(expo)
    except (TypeError, ValueError):
        e = 1.0
    if e <= 0:
        return 0
    if e < 0.5:
        return int(thin_pool)
    trade = recommend_top_n(e, default=default_trade)
    return max(int(normal_pool), int(trade))


def fetch_all_index_klines(lmt: int = 120) -> dict[str, list[dict]]:
    """拉取各指数日 K，供回测 as-of 复用。"""
    out: dict[str, list[dict]] = {}
    for key, meta in INDEXES.items():
        try:
            kl = fetch_index_klines(meta["secid"], lmt=lmt)
            out[key] = kl or []
        except Exception as e:
            print(f"  ⚠️ index hist fail {meta['name']}: {e}", flush=True)
            out[key] = []
    return out


def build_env_asof(index_hist: dict[str, list[dict]], asof: str) -> dict:
    """用 as-of 日及之前的指数 K 线构建环境快照（无未来函数）。"""
    indexes = {}
    for key, meta in INDEXES.items():
        kl_all = index_hist.get(key) or []
        kl = [x for x in kl_all if str(x.get("date", ""))[:10] <= asof][-30:]
        if not kl:
            indexes[key] = {
                "name": meta["name"],
                "secid": meta["secid"],
                "ok": False,
                "weak": False,
                "severe": False,
                "ret_5d": 0.0,
                "ret_10d": 0.0,
            }
            continue
        tr = _trend_from_klines(kl)
        indexes[key] = {"name": meta["name"], "secid": meta["secid"], **tr}
    flags = _flags_from_indexes(indexes)
    snap = {
        "ts": f"{asof}T15:00:00",
        "asof": asof,
        "indexes": indexes,
        "flags": flags,
        "position_exposure": position_exposure_ladder(flags),
        "exposure_mode": "ladder_v2",
    }
    return snap


def build_market_env(lmt: int = 30) -> dict:
    indexes = {}
    for key, meta in INDEXES.items():
        try:
            kl = fetch_index_klines(meta["secid"], lmt=lmt)
            if not kl:
                raise RuntimeError("empty klines from em/sina")
            tr = _trend_from_klines(kl)
            indexes[key] = {"name": meta["name"], "secid": meta["secid"], **tr}
        except Exception as e:
            indexes[key] = {
                "name": meta["name"],
                "secid": meta["secid"],
                "ok": False,
                "error": str(e),
                "weak": False,
                "severe": False,
                "ret_5d": 0.0,
                "ret_10d": 0.0,
            }
            print(f"  ⚠️ index fetch fail {meta['name']}: {e}", flush=True)

    flags = _flags_from_indexes(indexes)
    asof = None
    for k in ("sh_main", "sz_main"):
        asof = (indexes.get(k) or {}).get("last_date") or asof
    asof = str(asof or time.strftime("%Y-%m-%d"))[:10]
    snap = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "asof": asof,
        "indexes": indexes,
        "flags": flags,
        "position_exposure": position_exposure_ladder(flags),
        "exposure_mode": "ladder_v2",
    }
    try:
        from permission_gate import enrich_env_with_permission

        enrich_env_with_permission(snap, asof=asof)
    except Exception as e:
        print(f"  ⚠️ permission gate skip: {e}", flush=True)
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    return snap


def load_or_build_env(force: bool = False) -> dict:
    if not force and CACHE_PATH.exists():
        try:
            snap = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            # 当天缓存可复用
            if str(snap.get("ts", "")).startswith(time.strftime("%Y-%m-%d")):
                return snap
        except Exception:
            pass
    return build_market_env()


def board_penalty(board: str, env: dict) -> tuple[float, str, bool]:
    """
    返回 (score_delta, reason, hard_drop)
    hard_drop=True 表示应从候选中剔除。
    """
    idx = env.get("indexes") or {}
    flags = env.get("flags") or {}
    delta = 0.0
    reasons = []
    hard = False

    if board == "chinext":
        st = idx.get("chinext") or {}
        if st.get("severe"):
            # 默认不再硬删：过去走弱 ≠ 未来不能涨；改为重降权
            hard = False
            delta -= 0.12
            reasons.append(f"创业板严重走弱5d={st.get('ret_5d')}%/10d={st.get('ret_10d')}%(软降权)")
        elif st.get("weak"):
            delta -= 0.08
            reasons.append(f"创业板走弱5d={st.get('ret_5d')}%")
    elif board == "star50":
        st = idx.get("star50") or {}
        if st.get("severe"):
            hard = False
            delta -= 0.12
            reasons.append(f"科创50严重走弱5d={st.get('ret_5d')}%/10d={st.get('ret_10d')}%(软降权)")
        elif st.get("weak"):
            delta -= 0.08
            reasons.append(f"科创50走弱5d={st.get('ret_5d')}%")

    # 大盘整体弱：所有票软降权；双指数严重走弱时主板上也更谨慎
    if flags.get("market_severe"):
        delta -= 0.06
        reasons.append("沪深双指数严重走弱")
        if board == "main":
            # 主板不硬杀，但降权更重
            delta -= 0.02
    elif flags.get("market_weak"):
        delta -= 0.03
        reasons.append("沪深双指数走弱")

    # 科技整体弱但对主板只轻降（风格切换）
    if board == "main" and flags.get("tech_severe"):
        delta += 0.01  # 轻微偏向非科技（可选）
    if board in ("chinext", "star50") and flags.get("tech_weak") and not hard:
        delta -= 0.02

    return round(delta, 4), "; ".join(reasons) if reasons else "", hard


def tech_industry_hard_drop(industry_l1: str | None, env: dict) -> bool:
    """兼容旧名：生产已改为软降权，此函数恒为 False（仅 legacy hard 模式可再打开）。"""
    return False


def tech_industry_soft_delta(industry_l1: str | None, env: dict) -> tuple[float, str]:
    """科技指数严重走弱时，对科技 L1 行业降分（不删除）。"""
    flags = env.get("flags") or {}
    if not flags.get("tech_severe"):
        return 0.0, ""
    if str(industry_l1 or "") not in TECH_INDUSTRY_L1:
        return 0.0, ""
    return -0.10, f"科技风格行业软降权({industry_l1})"


def apply_market_env_gate(
    items: list[dict[str, Any]],
    env: dict | None = None,
    hard_filter: bool = True,
    mode: str = "soft_demote",
    industry_map: dict | None = None,
) -> list[dict[str, Any]]:
    """
    指数环境门控。
    mode:
      - soft_demote: 生产默认。板/科技行业只降分不删；仅 expo=0 nuclear 清空
      - hard_only: 旧口径（板 severe / 科技行业硬删，不改分）— 对照用
      - soft_then_hard: 降分 + 旧硬删
      - soft_only: 只降分不删（含 nuclear 也不因 expo 清空，慎用）
    """
    if not items:
        return items
    env = env or load_or_build_env()
    # soft_demote / soft_only：不硬删个股；nuclear 仍可清空
    allow_stock_hard = hard_filter and mode in ("hard_only", "soft_then_hard")
    do_soft = mode in ("soft_then_hard", "soft_only", "soft_demote")
    allow_nuclear_empty = mode != "soft_only"
    imap = industry_map or {}
    expo = float(env.get("position_exposure", position_exposure(env.get("flags") or {})))

    if allow_nuclear_empty and allow_stock_hard and expo <= 0:
        print("  market_env_gate: nuclear → empty book (exposure=0)", flush=True)
        return []
    if allow_nuclear_empty and mode == "soft_demote" and expo <= 0:
        print("  market_env_gate: nuclear → empty book (exposure=0)", flush=True)
        return []

    out = []
    dropped = 0
    soft_n = 0
    for r in items:
        code = _bare(r.get("symbol") or r.get("code") or "")
        board = stock_board(code)
        delta, reason, hard = board_penalty(board, env)
        if allow_stock_hard and hard:
            dropped += 1
            continue
        ind_l1 = r.get("industry_l1")
        if not ind_l1 and code in imap:
            ind_l1 = (imap.get(code) or {}).get("industry_l1")
        # legacy hard tech wipe
        if allow_stock_hard and mode != "soft_demote":
            flags = env.get("flags") or {}
            if flags.get("tech_severe") and str(ind_l1 or "") in TECH_INDUSTRY_L1:
                dropped += 1
                continue
        tdelta, treason = tech_industry_soft_delta(ind_l1, env)
        if tdelta:
            delta += tdelta
            reason = (reason + "; " if reason else "") + treason
        base = float(r.get("score", 0) or 0)
        nr = dict(r)
        nr["market_env_board"] = board
        nr["market_env_reason"] = reason
        nr["position_exposure"] = expo
        if ind_l1:
            nr["industry_l1"] = ind_l1
        if do_soft and abs(delta) > 1e-12:
            soft_n += 1
            nr["score_raw_pre_mkt"] = round(base, 4)
            nr["market_env_delta"] = round(delta, 4)
            nr["score"] = round(max(0.01, base + delta), 4)
        else:
            nr["market_env_delta"] = 0.0
            nr["score"] = base
        out.append(nr)

    out.sort(key=lambda x: float(x.get("score", 0) or 0), reverse=True)
    if dropped or soft_n:
        print(
            f"  market_env_gate: mode={mode} hard-drop={dropped} soft-demote={soft_n} "
            f"kept={len(out)} exposure={expo}",
            flush=True,
        )
    return out


if __name__ == "__main__":
    env = build_market_env()
    print(json.dumps(env, ensure_ascii=False, indent=2))
    demo = [
        {"symbol": "300750", "score": 0.70, "name": "宁德时代"},
        {"symbol": "688981", "score": 0.68, "name": "中芯国际"},
        {"symbol": "600519", "score": 0.65, "name": "贵州茅台"},
    ]
    print(json.dumps(apply_market_env_gate(demo), ensure_ascii=False, indent=2))
