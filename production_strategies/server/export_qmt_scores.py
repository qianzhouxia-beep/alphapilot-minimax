#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导出 QMT scores 每日文件 (2026-08-03, 修复 2026-08-08)

从 daily_recommend.json 的 recommendations 提取 {code.SZ: score},
写为 output/qmt_scores/{YYYYMMDD}.json, 供本地 QMT ML选股策略读取。

QMT 侧 ML选股 (qmt_model_01_ml选股_v207.py / qmt_model_full_chain_v1.py)
读 C:/alphapilot/scores/{date}.json, 取 Top2 买入。

排序约定（关键，勿改）:
  recommendations 在 09:35 终选后由 morning_live_fund_select.py 重写,
  顺序 = 资金门(money_flow_pass)通过者在前(按 score 降序) + 未过者在后。
  网页「今日推荐」Top2 = recommendations[:recommend_top_n] (保序)。
  因此本脚本必须 **保留 recommendations 的原始顺序** 导出,
  让 QMT Top2 与网页正式推荐对齐。
  ⚠️ 严禁再按 score 重排——那会把资金门刷掉的纯高分股(如 08-07 锐捷/威迈斯)
     重新顶上 Top2, 与网页不一致 (2026-08-08 修复)。
"""
import json
import os
import sys
from datetime import datetime, date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REC_JSON = ROOT / "output" / "daily_recommend.json"
OUT_DIR = ROOT / "output" / "qmt_scores"
FF_HIST_JSON = ROOT / "data" / "fund_flow_history.json"
KLINE_PARQUET = ROOT / "data" / "kline_cache" / "kline_all.parquet"


def _project_root() -> Path:
    """export 可能在仓库根或 production_strategies/server/；数据在仓库根。"""
    if (ROOT / "data" / "kline_cache" / "kline_all.parquet").exists():
        return ROOT
    cand = ROOT.parents[1] if len(ROOT.parents) > 1 else ROOT
    if (cand / "data" / "kline_cache" / "kline_all.parquet").exists():
        return cand
    return ROOT


def _bare(sym: str) -> str:
    s = str(sym or "").split(".")[0].upper()
    for p in ("SH", "SZ", "BJ"):
        s = s.replace(p, "")
    return s.zfill(6)[-6:] if s else ""


def _is_limit_bar(ret, code: str) -> float:
    if ret is None or (isinstance(ret, float) and ret != ret):
        return 0.0
    c = str(code)
    if c.startswith(("300", "301", "688", "689")):
        return 1.0 if ret >= 0.195 else 0.0
    return 1.0 if ret >= 0.098 else 0.0


LOUD_VOL_RATIO = 2.5  # T-1 vol/MA20; up-day extreme = loud_vol soft reject


def _load_t1_path_frame(code_set: set):
    """T-1 features: path_fade / lim10 / loud_vol / short-narrow-shrink (sns).

    Returns (feat_df indexed by symbol, t1) or (None, None).
    """
    try:
        import pandas as pd
    except Exception:
        return None, None
    root = _project_root()
    kline = root / "data" / "kline_cache" / "kline_all.parquet"
    if not kline.exists() or not code_set:
        return None, None
    cols = ["symbol", "date", "open", "high", "low", "close", "volume"]
    try:
        df = pd.read_parquet(kline, columns=cols)
    except Exception:
        df = pd.read_parquet(
            kline, columns=["symbol", "date", "open", "high", "low", "close"]
        )
        df["volume"] = float("nan")
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df["symbol"] = df["symbol"].map(_bare)
    df = df[df["symbol"].isin(code_set)].sort_values(["symbol", "date"])
    if df.empty:
        return None, None
    g = df.groupby("symbol", group_keys=False)
    df["prev_close"] = g["close"].shift(1)
    df["ret"] = g["close"].pct_change()
    df["ret_10d"] = g["close"].pct_change(10)
    df["ma25"] = g["close"].transform(lambda s: s.rolling(25, min_periods=15).mean())
    df["ma25_prev"] = g["ma25"].shift(5)
    df["ma25_slope"] = df["ma25"] / (df["ma25_prev"] + 1e-9) - 1.0
    df["is_limit"] = [
        _is_limit_bar(r, c) for r, c in zip(df["ret"], df["symbol"])
    ]
    df["limit_cnt_5d"] = g["is_limit"].transform(
        lambda s: s.rolling(5, min_periods=1).sum()
    )
    df["limit_cnt_10d"] = g["is_limit"].transform(
        lambda s: s.rolling(10, min_periods=1).sum()
    )
    rng = (df["high"] - df["low"]).replace(0, float("nan"))
    df["close_pos"] = (df["close"] - df["low"]) / rng
    df["gap_pct"] = df["open"] / df["prev_close"] - 1.0
    df["is_yin"] = df["close"] < df["open"]
    df["is_yang"] = df["close"] > df["open"]
    df["day_range"] = (df["high"] - df["low"]) / (df["prev_close"] + 1e-9)
    # path_fade: recent limit + gap-up HOLC. No lim10 exemption.
    df["path_fade"] = (
        (df["limit_cnt_5d"] >= 1)
        & (df["gap_pct"] >= 0.01)
        & df["is_yin"]
        & (df["close_pos"] <= 0.15)
    )
    # loud_vol: up-day volume / MA20 extreme (锣鼓喧天)
    df["vol_ma20"] = g["volume"].transform(lambda s: s.rolling(20, min_periods=5).mean())
    df["vol_ma_ratio"] = df["volume"] / (df["vol_ma20"] + 1e-9)
    df["loud_vol"] = (df["vol_ma_ratio"] >= LOUD_VOL_RATIO) & (df["ret"] > 0)
    # short-narrow-shrink (sns): quiet_accum + up_shrink
    df["range_med_5"] = g["day_range"].transform(
        lambda s: s.rolling(5, min_periods=3).median()
    )
    df["yang_cnt_5"] = g["is_yang"].transform(
        lambda s: s.rolling(5, min_periods=3).sum()
    )
    df["vol_ma5"] = g["volume"].transform(lambda s: s.rolling(5, min_periods=3).mean())
    df["quiet_accum"] = (
        (df["range_med_5"] <= 0.03)
        & (df["yang_cnt_5"] >= 3)
        & (df["vol_ma5"] <= df["vol_ma20"] * 1.0)
    )
    df["_up_v"] = df["volume"].where(df["ret"] > 0)
    df["_dn_v"] = df["volume"].where(df["ret"] < 0)
    df["up_vol_10"] = g["_up_v"].transform(lambda s: s.rolling(10, min_periods=2).mean())
    df["dn_vol_10"] = g["_dn_v"].transform(lambda s: s.rolling(10, min_periods=2).mean())
    df["up_dn_vol_ratio"] = df["up_vol_10"] / (df["dn_vol_10"] + 1e-9)
    df["up_shrink"] = df["up_dn_vol_ratio"] <= 0.9
    df["sns_score"] = (
        df["quiet_accum"].astype(float) + df["up_shrink"].astype(float)
    )
    today = datetime.now().strftime("%Y-%m-%d")
    dates = sorted(df["date"].unique())
    t1 = None
    for d in reversed(dates):
        if d < today:
            t1 = d
            break
    if t1 is None:
        t1 = dates[-1]
    feat = df[df["date"] == t1].set_index("symbol")
    return feat, t1


def _gene_rerank_candidates(cand_rows: list) -> list:
    """Top10 gene + path_fade/loud_vol demote + sns_score boost (2026-09-04).

    gene_score = rank(lim10)+rank(ma25_slope)+rank(ret_10d) — lim weight NOT raised.
    Sort: path_fade asc, loud_vol asc, gene_score desc, sns_score desc, rank_raw asc.
    """
    if len(cand_rows) < 2:
        return cand_rows
    try:
        import pandas as pd
    except Exception as e:
        print(f"[GENE] skip (no pandas): {e}", flush=True)
        return cand_rows
    try:
        codes = [_bare(r.get("symbol")) for r in cand_rows]
        code_set = {c for c in codes if c}
        feat, t1 = _load_t1_path_frame(code_set)
        if feat is None or feat.empty:
            print("[GENE] skip (no t1 feat)", flush=True)
            return cand_rows

        scored = []
        for r in cand_rows:
            code = _bare(r.get("symbol"))
            row = dict(r)
            row["rank_raw"] = int(r.get("rank") or 0)
            try:
                fr = feat.loc[code]
                row["_lim"] = float(fr["limit_cnt_10d"])
                row["_slope"] = float(fr["ma25_slope"])
                row["_r10"] = float(fr["ret_10d"])
                row["_lim5"] = float(fr["limit_cnt_5d"])
                row["_path_fade"] = bool(fr["path_fade"])
                row["_loud_vol"] = bool(fr["loud_vol"]) if fr["loud_vol"] == fr["loud_vol"] else False
                row["_quiet"] = bool(fr["quiet_accum"]) if fr["quiet_accum"] == fr["quiet_accum"] else False
                row["_up_shrink"] = bool(fr["up_shrink"]) if fr["up_shrink"] == fr["up_shrink"] else False
                row["_sns"] = float(fr["sns_score"]) if fr["sns_score"] == fr["sns_score"] else 0.0
                row["_vmr"] = float(fr["vol_ma_ratio"]) if fr["vol_ma_ratio"] == fr["vol_ma_ratio"] else None
                row["_gap"] = float(fr["gap_pct"]) if fr["gap_pct"] == fr["gap_pct"] else None
                row["_cpos"] = float(fr["close_pos"]) if fr["close_pos"] == fr["close_pos"] else None
            except Exception:
                row["_lim"] = float("nan")
                row["_slope"] = float("nan")
                row["_r10"] = float("nan")
                row["_lim5"] = float("nan")
                row["_path_fade"] = False
                row["_loud_vol"] = False
                row["_quiet"] = False
                row["_up_shrink"] = False
                row["_sns"] = 0.0
                row["_vmr"] = None
                row["_gap"] = None
                row["_cpos"] = None
            scored.append(row)

        sdf = pd.DataFrame(scored)
        for col, out in (("_lim", "rk_lim"), ("_slope", "rk_slope"), ("_r10", "rk_r10")):
            rk = sdf[col].rank(pct=True, method="average")
            sdf[out] = rk.fillna(rk.median() if rk.notna().any() else 0.5)
        sdf["gene_score"] = sdf["rk_lim"] + sdf["rk_slope"] + sdf["rk_r10"]
        # demote path_fade + loud_vol; boost sns_score; lim weight unchanged
        sdf = sdf.sort_values(
            ["_path_fade", "_loud_vol", "gene_score", "_sns", "rank_raw"],
            ascending=[True, True, False, False, True],
        )
        out = []
        n_fade = n_loud = 0
        for i, (_, r) in enumerate(sdf.iterrows(), 1):
            item = {k: r[k] for k in cand_rows[0].keys() if k in r.index}
            for k in cand_rows[0].keys():
                if k not in item:
                    item[k] = r[k] if k in r.index else None
            item["rank"] = i
            item["rank_raw"] = int(r["rank_raw"])
            item["gene_score"] = round(float(r["gene_score"]), 4)
            item["limit_cnt_10d"] = None if r["_lim"] != r["_lim"] else round(float(r["_lim"]), 4)
            item["limit_cnt_5d"] = None if r["_lim5"] != r["_lim5"] else round(float(r["_lim5"]), 4)
            item["path_fade"] = bool(r["_path_fade"])
            item["loud_vol"] = bool(r["_loud_vol"])
            item["quiet_accum"] = bool(r["_quiet"])
            item["up_shrink"] = bool(r["_up_shrink"])
            item["sns_score"] = round(float(r["_sns"]), 4)
            item["vol_ma_ratio"] = None if r["_vmr"] is None else round(float(r["_vmr"]), 4)
            if item["path_fade"]:
                n_fade += 1
            if item["loud_vol"]:
                n_loud += 1
            item["gene_parts"] = {
                "limit_cnt_10d": item["limit_cnt_10d"],
                "ma25_slope": None if r["_slope"] != r["_slope"] else round(float(r["_slope"]), 4),
                "ret_10d": None if r["_r10"] != r["_r10"] else round(float(r["_r10"]), 4),
                "path_fade": item["path_fade"],
                "loud_vol": item["loud_vol"],
                "quiet_accum": item["quiet_accum"],
                "up_shrink": item["up_shrink"],
                "sns_score": item["sns_score"],
                "vol_ma_ratio": item["vol_ma_ratio"],
                "t1_gap_pct": None if r["_gap"] is None else round(float(r["_gap"]), 4),
                "t1_close_pos": None if r["_cpos"] is None else round(float(r["_cpos"]), 4),
            }
            out.append(item)
        top = [(x["symbol"], x["rank"], x.get("path_fade"), x.get("loud_vol"),
                x.get("sns_score")) for x in out[:3]]
        print(f"[GENE] reranked {len(out)} cands t1={t1} path_fade={n_fade} "
              f"loud_vol={n_loud}; new top3={top}", flush=True)
        return out
    except Exception as e:
        print(f"[GENE] skip (error): {e}", flush=True)
        return cand_rows


def _stamp_path_and_lim10(rows: list) -> list:
    """Stamp T-1 lim10 + path_fade + loud_vol + sns onto fullpool_live.

    path_fade = 近5日有涨停 + T-1 高开低走收低。loud_vol = 涨日 vol/MA20>=2.5。
    """
    if not rows:
        return rows
    try:
        codes = [_bare(r.get("symbol")) for r in rows]
        code_set = {c for c in codes if c}
        feat, t1 = _load_t1_path_frame(code_set)
        if feat is None or feat.empty:
            print("[PATH] skip (no t1 feat)", flush=True)
            return rows
        n_ok = n_fade = n_loud = n_quiet = 0
        for r in rows:
            bc = _bare(r.get("symbol"))
            if bc in feat.index:
                fr = feat.loc[bc]
                if fr["limit_cnt_10d"] == fr["limit_cnt_10d"]:
                    r["limit_cnt_10d"] = round(float(fr["limit_cnt_10d"]), 4)
                    n_ok += 1
                else:
                    r["limit_cnt_10d"] = None
                r["limit_cnt_5d"] = (
                    None if fr["limit_cnt_5d"] != fr["limit_cnt_5d"]
                    else round(float(fr["limit_cnt_5d"]), 4)
                )
                r["path_fade"] = bool(fr["path_fade"])
                if r["path_fade"]:
                    n_fade += 1
                r["loud_vol"] = bool(fr["loud_vol"]) if fr["loud_vol"] == fr["loud_vol"] else False
                if r["loud_vol"]:
                    n_loud += 1
                r["quiet_accum"] = (
                    bool(fr["quiet_accum"]) if fr["quiet_accum"] == fr["quiet_accum"] else False
                )
                if r["quiet_accum"]:
                    n_quiet += 1
                r["up_shrink"] = (
                    bool(fr["up_shrink"]) if fr["up_shrink"] == fr["up_shrink"] else False
                )
                r["sns_score"] = (
                    None if fr["sns_score"] != fr["sns_score"]
                    else round(float(fr["sns_score"]), 4)
                )
                r["vol_ma_ratio"] = (
                    None if fr["vol_ma_ratio"] != fr["vol_ma_ratio"]
                    else round(float(fr["vol_ma_ratio"]), 4)
                )
                r["t1_gap_pct"] = (
                    None if fr["gap_pct"] != fr["gap_pct"]
                    else round(float(fr["gap_pct"]), 4)
                )
                r["t1_close_pos"] = (
                    None if fr["close_pos"] != fr["close_pos"]
                    else round(float(fr["close_pos"]), 4)
                )
            else:
                r["limit_cnt_10d"] = None
                r["limit_cnt_5d"] = None
                r["path_fade"] = False
                r["loud_vol"] = False
                r["quiet_accum"] = False
                r["up_shrink"] = False
                r["sns_score"] = None
                r["vol_ma_ratio"] = None
        print(
            f"[PATH] stamped lim10={n_ok}/{len(rows)} path_fade={n_fade} "
            f"loud_vol={n_loud} quiet={n_quiet} (t1={t1})",
            flush=True,
        )
        return rows
    except Exception as e:
        print(f"[PATH] skip (error): {e}", flush=True)
        return rows


def _market_env() -> dict:
    """市场环境标记（2026-09-03 v2.31 弱市破位敏感卖出配套）。

    口径与 bt_research/bt_weak_winner_score.py 一致：全 A 主力净流入 5 日累计
    的全历史分位 → state5_q（1=深流出）；weak_regime = (q==1)。
    交易端（QMT 轨道 A v2.31+）读 candidates/fullpool JSON 的 market_env，
    弱市收紧破位卖出参数；未读到时按非弱市处理（行为与旧版一致）。
    计算失败时返回空 dict，绝不影响导出主流程。
    """
    try:
        root = _project_root()
        ff = root / "data" / "fund_flow_history.json"
        raw = json.loads(ff.read_text(encoding="utf-8"))
        daily = {}
        for series in raw.values():
            if not isinstance(series, dict):
                continue
            for d, v in series.items():
                try:
                    daily[d] = daily.get(d, 0.0) + float(v)
                except (TypeError, ValueError):
                    continue
        if len(daily) < 30:
            return {}
        import math
        import pandas as pd
        s = pd.Series(daily).sort_index()
        tot5 = s.rolling(5, min_periods=3).sum().dropna()
        if tot5.empty:
            return {}
        q = int(min(5, max(1, math.ceil(tot5.rank(pct=True).iloc[-1] * 5))))
        return {"state5_q": q, "weak_regime": q == 1,
                "asof": str(tot5.index[-1])}
    except Exception:
        return {}


def _norm_code(sym: str) -> str:
    """统一为 QMT 需要的 '600000.SH' / '000001.SZ' 格式"""
    s = str(sym or "").strip().upper()
    if "." in s:                      # 已带后缀 (600000.SH / SH600000?)
        parts = s.replace("SH", "").replace("SZ", "").replace("BJ", "")
        return parts[-6:] + "." + s[-2:] if s[-2:] in ("SH", "SZ") else parts[-6:] + ".SH" if parts[-6:].startswith(("6", "5", "9")) else parts[-6:] + ".SZ"
    s = s.replace("SH", "").replace("SZ", "").replace("BJ", "")
    s = s[-6:]
    if s.startswith(("6", "5", "9")):
        return s + ".SH"
    return s + ".SZ"


def _ff_hist_main_net_5d(code6: str) -> float:
    """主力 5 日净流入（元）：读 data/fund_flow_history.json（东财历史资金流）。

    与 money_flow_gate.py 的 hard_main_net_5d 硬门同一数据源/同一算法：
    取最近 5 个交易日的 main_net 求和。文件缺失/股票缺失/无值 -> 0.0
    （QMT 端把 0.0 视为"缺数据跳过资金硬门"，见轨道 B 策略）。
    """
    try:
        if not FF_HIST_JSON.exists():
            return 0.0
        raw = FF_HIST_JSON.read_text(encoding="utf-8")
        cut = raw.rfind("}")
        if cut > 0:
            raw = raw[:cut + 1]
        hist = json.loads(raw)
    except Exception:
        return 0.0
    h = hist.get(str(code6).strip()) if isinstance(hist, dict) else None
    if not h or not isinstance(h, dict):
        return 0.0
    nets = []
    for _v in list(h.values())[-5:]:
        try:
            if _v is not None:
                nets.append(float(_v))
        except (TypeError, ValueError):
            pass
    return round(sum(nets), 2) if nets else 0.0


def export_fullpool():
    """轨道 B fullpool 导出（06:30 cron，不碰现有 09:36 导出）。

    从 05:00 pipeline 写回的 daily_recommend.json 的 recommendations
    导出全量候选池 {YYYYMMDD}.fullpool.json，供 QMT 轨道 B 竞价选股策略
    （TrackB_track_b_qmt_auction_sim.py / TrackB_track_b_qmt_auction_live.py /
    TrackB_track_b_tdx_auction_sim.py）做 09:25-09:35 门控选股。

    fresh 校验：daily_recommend.json 的 mtime 须为今天（05:00 pipeline
    刚写回），防止读到昨日残留。周末/管线未跑 -> SKIP。

    字段约定（与 DUAL_TRACK_BRIEFING.md §4.2/§4.5 对齐）：
      symbol     : QMT 格式代码 600000.SH
      name       : 名称
      rank       : 顺序号（05:00 池原序，非资金门重排后）
      industry_l1: 一级行业（板块聚合用）
      score_0500 : 05:00 模型分 = icir_raw_score → score_raw → ml_score
                   （逐级 fallback；均缺 -> 不导出该行）
      main_net_5d: 主力 5 日净流入（元）；recommendations 缺失时从
                   fund_flow_history.json 补算；仍无 -> 0.0（QMT 端跳过硬门）
      不导出 pre_market_* —— 09:25 竞价门控由 QMT 端独立重算（交叉验证 §6-6）。
    """
    if not REC_JSON.exists():
        print("[FULLPOOL] daily_recommend.json 不存在", flush=True)
        return 1
    today = date.today()
    try:
        mtime = date.fromtimestamp(REC_JSON.stat().st_mtime)
    except Exception:
        print("[FULLPOOL] stat 失败，跳过", flush=True)
        return 1
    if mtime != today:
        print(f"[FULLPOOL] SKIP mtime={mtime} != 今天 {today}（管线未跑/残留）",
              flush=True)
        return 1

    with open(REC_JSON, encoding="utf-8") as f:
        rec = json.load(f)
    pool = rec.get("recommendations") or rec.get("full_candidate_pool") or []
    if not pool:
        print("[FULLPOOL] recommendations 为空", flush=True)
        return 1

    rows = []
    for i, it in enumerate(pool):
        sym = it.get("symbol")
        if not sym:
            continue
        score = (it.get("icir_raw_score")
                 if it.get("icir_raw_score") is not None
                 else (it.get("score_raw")
                       if it.get("score_raw") is not None
                       else it.get("ml_score")))
        if score is None:
            continue
        code6 = "".join(ch for ch in str(sym).split(".")[0] if ch.isdigit())
        m5 = it.get("main_net_5d")
        if m5 is None:
            m5 = _ff_hist_main_net_5d(code6)
        # score = A 臂最终分（含形态突破/趋势/草木皆兵等软加分），
        # 供轨道 B 竞价阶段优先排序；score_0500 保留裸模型分做参考。
        final_score = it.get("score")
        rows.append({
            "symbol": _norm_code(sym),
            "name": it.get("name") or "",
            "rank": i + 1,
            "industry_l1": it.get("industry_l1") or "",
            "score_0500": round(float(score), 4),
            "score": round(float(final_score), 4) if final_score is not None else None,
            "pattern_breakout": bool(it.get("pattern_breakout")),
            "pattern_breakout_delta": round(float(it.get("pattern_breakout_delta") or 0), 4),
            "main_net_5d": round(float(m5 or 0), 2),
        })

    if not rows:
        print("[FULLPOOL] 无有效行", flush=True)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    out_path = OUT_DIR / f"{date_str}.fullpool.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "date": date_str,
            "asof": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": "05:00_pipeline_recommendations",
            "market_env": _market_env(),
            "n": len(rows),
            "rows": rows,
        }, f, ensure_ascii=False, indent=2)
    print(f"[FULLPOOL] OK {len(rows)} 只 → {out_path}", flush=True)
    return 0


def export_fullpool_live():
    """轨道 B 实时 fullpool 导出（09:36 cron，紧随 live_momentum_scanner +
    morning_live_fund_select 之后）。

    与 06:30 --fullpool 的区别：daily_recommend.json 在 09:35 已被
    live_momentum_scanner 重排（score = 0.6×管线106维分 + 0.4×实时资金动量z）
    并被 morning_live_fund_select 打上资金门/研报门结果。因此本导出把
    全部 106 维因子 + 实时动量 + 资金门 + 研报门的一次性结果打包成
    {YYYYMMDD}.fullpool_live.json，QMT 轨道 B 09:36 后读取它做最终动态
    确认下单，不再需要 QMT 端重算 5 点管线的因子/门控。

    排序约定：保留 recommendations 原始顺序（money_flow_pass 通过者在前）。
    score 字段 = 实时融合分（scanner 重排后），与 Track A 的 {date}.json 同源。

    字段约定（fullpool_live 专有，比 fullpool 更全）：
      symbol          : QMT 格式代码
      name / industry_l1
      score           : 09:35 实时融合分（主排序依据，scanner 已 0.6/0.4 融合）
      score_0500      : 05:00 管线原始模型分
      _live_momentum_z: 实时资金动量 z-score
      money_flow_pass : 服务器资金门结果（True/False）
      research_tier   : 研报门档位（s0/s1/s2/a/b/None）
      research_prefer_hit
      main_net        : 今日实时主力净额
      main_net_5d     : 主力 5 日净流入
      active_buy_ratio: 实时主动买占比（live_abr 优先）
      turnover / volume_ratio / change_pct
      pre_market_gap_pct / pre_market_action  (09:25 竞价门控结果)
    """
    if not REC_JSON.exists():
        print("[FULLPOOL_LIVE] daily_recommend.json 不存在", flush=True)
        return 1
    with open(REC_JSON, encoding="utf-8") as f:
        rec = json.load(f)

    # fresh 校验：morning_live_at 须为今天（09:35 终选重排已发生）
    today = datetime.now().strftime("%Y-%m-%d")
    ml_at = str(rec.get("morning_live_at") or "")
    if not ml_at.startswith(today):
        print(f"[FULLPOOL_LIVE] SKIP morning_live_at 非今日({ml_at})，"
              f"09:35 重排未发生", flush=True)
        return 1

    # 09:35 重排后 recommendations = 资金门通过者在前 + 未过者在后（保序勿排）
    pool = rec.get("recommendations") or rec.get("full_candidate_pool") or []
    if not pool:
        print("[FULLPOOL_LIVE] recommendations 为空", flush=True)
        return 1

    rows = []
    for i, it in enumerate(pool):
        sym = it.get("symbol")
        if not sym:
            continue
        sc = it.get("score")
        if sc is None:
            continue
        code6 = "".join(ch for ch in str(sym).split(".")[0] if ch.isdigit())
        m5 = it.get("main_net_5d")
        if m5 is None:
            m5 = _ff_hist_main_net_5d(code6)
        base_score = (it.get("icir_raw_score")
                      if it.get("icir_raw_score") is not None
                      else (it.get("score_raw")
                            if it.get("score_raw") is not None
                            else it.get("ml_score")))

        # 分层资金流：live_* 优先（东财 ulist 修复后），否则 money_flow_gate 的 Wind 分档
        def _layer(live_key: str, wind_key: str) -> float:
            v = it.get(live_key)
            if v is None:
                v = it.get(wind_key)
            return round(float(v or 0), 2)

        rows.append({
            "symbol": _norm_code(sym),
            "name": it.get("name") or "",
            "rank": i + 1,
            "industry_l1": it.get("industry_l1") or "",
            "score": round(float(sc), 4),
            "score_0500": round(float(base_score), 4)
                          if base_score is not None else None,
            "live_momentum_z": round(float(it.get("_live_momentum_z") or 0), 4),
            "money_flow_pass": bool(it.get("money_flow_pass")),
            "research_tier": it.get("research_tier"),
            "research_prefer_hit": bool(it.get("research_prefer_hit")),
            "main_net": round(float(it.get("live_main_net")
                                    if it.get("live_main_net") is not None
                                    else it.get("main_net") or 0), 2),
            "main_net_5d": round(float(m5 or 0), 2),
            "main_net_3d": round(float(it.get("main_net_3d") or 0), 2),
            "main_net_10d": round(float(it.get("main_net_10d") or 0), 2),
            "fund_pos_days_5": int(it.get("fund_pos_days_5") or 0),
            "fund_soft_bonus": round(float(it.get("fund_soft_bonus") or 0), 4),
            "fund_hard_fail": bool(it.get("fund_hard_fail")),
            "money_phase": it.get("money_phase"),
            "super_large_net": _layer("live_super_large_net", "wind_inst_net"),
            "large_net": _layer("live_large_net", "wind_large_net"),
            "mid_net": _layer("live_mid_net", "wind_mid_net"),
            "small_net": _layer("live_small_net", "wind_retail_net"),
            "active_buy_ratio": round(float(it.get("live_abr")
                                            if it.get("live_abr") is not None
                                            else it.get("active_buy_ratio") or 0), 4),
            "turnover": round(float(it.get("turnover") or 0), 2),
            "volume_ratio": round(float(it.get("volume_ratio") or 0), 2),
            "change_pct": round(float(it.get("live_change_pct")
                                      if it.get("live_change_pct") is not None
                                      else it.get("change_pct") or 0), 2),
            "pre_market_gap_pct": it.get("pre_market_gap_pct"),
            "pre_market_action": it.get("pre_market_action"),
        })

    # 资金流排名（全池内 main_net 百分位 0~100，越大越强；同值取均值）
    if rows:
        vals = sorted(r["main_net"] for r in rows)
        n = len(vals)
        for r in rows:
            rank = sum(1 for v in vals if v < r["main_net"]) / max(n, 1)
            rank += 0.5 * sum(1 for v in vals if v == r["main_net"]) / max(n, 1)
            r["fund_rank"] = round(rank * 100.0, 2)

    # 数据合理性兜底：abr 须∈[0,1]、chg 须∈[-30,30]。
    # 服务器表头漂移/接口异常时会把净额当 abr（如 22298681）、把涨跌幅当大数（如 273），
    # 直接据此放行会把垃圾股排进 Top1（2026-08-19 002437 誉衡药业 case）。
    # 客户端 P2 有 c>=prev_close 兜底不下单，但 A1 决策/网页指令必须同样不推荐。
    n_data_err = 0
    for r in rows:
        abr = r.get("active_buy_ratio")
        chg = r.get("change_pct")
        errs = []
        if not (isinstance(abr, (int, float)) and 0.0 <= float(abr) <= 1.0):
            errs.append(f"abr={abr}异常")
        if not (isinstance(chg, (int, float)) and -30.0 <= float(chg) <= 30.0):
            errs.append(f"chg={chg}异常")
        if errs:
            n_data_err += 1
            r["money_flow_pass"] = False
            r["data_error"] = "|".join(errs)
            r["drop_reason"] = (r.get("drop_reason") or "") + "|data_garbage"
    if n_data_err:
        print(f"[FULLPOOL_LIVE] 数据异常强制 fail: {n_data_err} 只", flush=True)

    if not rows:
        print("[FULLPOOL_LIVE] 无有效行", flush=True)
        return 1

    # Track B: T-1 lim10 + path_fade（涨停后高开低走）
    rows = _stamp_path_and_lim10(rows)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    out_path = OUT_DIR / f"{date_str}.fullpool_live.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "date": date_str,
            "asof": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": "09:35_live_rerank(momentum0.4+pipeline0.6)_+money_gate+research_gate",
            "market_env": _market_env(),
            "morning_live_at": ml_at,
            "buy_rank_hint": "lim10_skip_path_fade_loud_vol",
            "n": len(rows),
            "rows": rows,
        }, f, ensure_ascii=False, indent=2)
    print(f"[FULLPOOL_LIVE] OK {len(rows)} 只 → {out_path}", flush=True)
    n_pass = sum(1 for r in rows if r["money_flow_pass"])
    print(f"[FULLPOOL_LIVE] money_flow_pass={n_pass}/{len(rows)}", flush=True)
    return 0


def main():
    if "--fullpool" in sys.argv:
        return export_fullpool()
    if "--fullpool-live" in sys.argv:
        return export_fullpool_live()
    if not REC_JSON.exists():
        print(f"[ERR] {REC_JSON} 不存在", flush=True)
        return 1
    with open(REC_JSON, encoding="utf-8") as f:
        rec = json.load(f)

    # 新鲜度校验（2026-08-08）：recommendations 须为「今天」定稿的
    # daily_recommend.json 的 morning_live_at 字段 = 09:35 终选时间。
    # 防止 cron 误跑/延迟跑时读到昨日残留内容。
    today = datetime.now().strftime("%Y-%m-%d")
    ml_at = str(rec.get("morning_live_at") or "")
    if not ml_at.startswith(today):
        print(f"[SKIP] morning_live_at 非今日({ml_at})，可能是旧数据", flush=True)
        return 1

    # 优先用 recommendations(09:35 终选重排后的正式推荐), 其次 full_candidate_pool(原始候选池)
    # 修复 2026-08-03: 原逻辑优先 pool 导致 QMT Top2 与正式推荐不一致(川能动力 vs 丸美生物)
    # 修复 2026-08-08: 原逻辑按 score 重排, 丢弃资金门顺序, 导致 QMT Top2 与网页正式推荐不一致
    pool = rec.get("recommendations") or rec.get("full_candidate_pool") or []
    scores = {}
    for it in pool:
        sym = it.get("symbol")
        sc = it.get("score")
        if sym and sc is not None:
            scores[_norm_code(sym)] = round(float(sc), 4)

    if not scores:
        print("[WARN] pool 为空, 无评分可导出", flush=True)
        return 1

    # 保留 recommendations 原始顺序(资金门通过者在前) —— 勿排序
    # 这样 QMT 侧 list(scores.items())[:2] 即网页正式推荐 Top2

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    out_path = OUT_DIR / f"{date_str}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(scores, f, ensure_ascii=False)
    top2 = list(scores.items())[:2]
    print(f"[OK] 导出 {len(scores)} 只 → {out_path}", flush=True)
    print(f"[OK] Top2(按正式推荐顺序): {top2}", flush=True)

    # ── 2026-08-09: 额外导出 Top10 候选池（供 QMT 模拟盘「先到先得」使用）──
    # 结构: {"date": "YYYYMMDD", "candidates": [{"symbol", "name", "score", "rank"}...]}
    cand_out = OUT_DIR / f"{date_str}.candidates.json"
    fusion_by = {}
    try:
        _ap = ROOT
        if not (_ap / "scripts" / "build_score_top10.py").exists():
            _ap = ROOT.parents[1]
        if str(_ap) not in sys.path:
            sys.path.insert(0, str(_ap))
        from scripts.build_score_top10 import compute_fusion
        ranked = compute_fusion([dict(x) for x in pool if isinstance(x, dict)])
        for r in ranked:
            fs = r.get("_fusion_scores")
            if fs:
                fusion_by[_norm_code(r.get("symbol"))] = fs
        print(f"[FUSION] stamped {len(fusion_by)} rows (order unchanged)", flush=True)
    except Exception as e:
        print(f"[FUSION] stamp skip: {e}", flush=True)
    cand_rows = []
    for i, it in enumerate(pool):
        sym = it.get("symbol")
        sc = it.get("score")
        if sym and sc is not None:
            row = {
                "symbol": _norm_code(sym),
                "name": it.get("name") or "",
                "score": round(float(sc), 4),
                "rank": i + 1,
                "fund_hard_fail": bool(it.get("fund_hard_fail")),
                "main_net_5d": round(float(it.get("main_net_5d") or 0), 2),
                "main_net_3d": round(float(it.get("main_net_3d") or 0), 2),
                "fund_pos_days_5": int(it.get("fund_pos_days_5") or 0),
            }
            fs = fusion_by.get(_norm_code(sym))
            if fs:
                row["fusion_scores"] = fs
            cand_rows.append(row)
        if len(cand_rows) >= 10:
            break
    # 2026-09-03 方案 A：Top10 内基因+趋势重排（资金不参与排序）
    # 仅改 candidates.json 的 rank/顺序；网页 recommendations / {date}.json 保序不动。
    n_before = len(cand_rows)
    cand_rows = _gene_rerank_candidates(cand_rows)
    with open(cand_out, "w", encoding="utf-8") as f:
        json.dump({
            "date": date_str,
            "asof": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "market_env": _market_env(),
            "rank_mode": "gene_pathfade_loudvol_demote_sns_boost",
            "candidates": cand_rows,
        }, f, ensure_ascii=False, indent=2)
    print(f"[OK] 候选池 {len(cand_rows)} 只 (gene-rerank, was {n_before}) → {cand_out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
