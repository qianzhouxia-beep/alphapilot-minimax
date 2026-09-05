#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""09:35 盘中：消费 live_momentum 全市场重选池 → 资金门控 → 取可交易 Top2。

生产口径（与网页「今日推荐」一致）：
  09:35 live_momentum_scanner 已从 ~5000 只重写 daily_recommend；
  本脚本再做资金门 + 研报软加权，默认按 **score** 取 Top2 写入 morning_live_picks。

Env:
  MORNING_RANK_MODE=model|fund   默认 model（score；与今日推荐同序）
                                 fund=按主动买/主力净流入（旧实验臂，勿作生产默认）
  RESEARCH_GATE_MODE             默认 soft_hybrid（avoid 软降权 + prefer 加分 + 竞价/资金主线硬加权）
  HITHINK_P2_SIDE                默认 0：同花顺只标注；1=用旁支分改 Top2（须回测通过）
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path("/home/ubuntu/alphapilot")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

REC_PATH = ROOT / "output/daily_recommend.json"
PICKS_PATH = ROOT / "output/morning_live_picks.json"
ELIM_PATH = ROOT / "output/morning_live_elimination.json"
LIVE_TOP_N = 2
PICKS_CANDIDATE_N = int(os.environ.get("PICKS_CANDIDATE_N", "10"))  # 候选池大小(先到先得用)
# 生产默认 model：与今日推荐（资金门后按 score）同口径
_rank_raw = os.environ.get("MORNING_RANK_MODE", "model").strip().lower() or "model"
RANK_MODE = "fund" if _rank_raw == "fund" else "model"
MODE_NAME = (
    "morning_live_fund_top2" if RANK_MODE == "fund" else "morning_live_model_top2"
)

# 跟庄书 price_quantile_250 二次重排（2026-08-03，WorkBuddy 建议 #3）
# 单测 IC +0.107 全书最强，但融合零增益（与 ma20_dist 共线）→ 不进训练特征，
# 只用它的排序能力做 Top50→Top2 微调：score * (1 + (q250-0.5)*STRENGTH)
# 默认开；BOOK_RERANK_QUANTILE=0 关闭。
BOOK_RERANK_QUANTILE = (
    os.environ.get("BOOK_RERANK_QUANTILE", "1").strip().lower() in ("1", "true", "yes", "on")
)
BOOK_RERANK_STRENGTH = float(os.environ.get("BOOK_RERANK_STRENGTH", "0.10") or 0.10)

# ── 影子并行试运行（08-15 落地，RD 晋升加速路径 A）────────────────────────
# 生产 09:35 选股完成后，用 RD 候选模型对同一个 gated pool 重打分，取候选 Top2，
# 与生产 Top2 一并追加记录到 output/shadow_top2_history.jsonl（只记录、不改生产输出）。
# 激活方式：SHADOW_MODEL_DIR=/path/to/candidate/models  （默认不激活 → 零影响）
SHADOW_MODEL_DIR = os.environ.get("SHADOW_MODEL_DIR", "").strip() or None
SHADOW_HISTORY_PATH = ROOT / "output" / "shadow_top2_history.jsonl"
# 09:35 资金加分影子（热板块/5日小涨/连续2日流入）。默认开，只写 jsonl，不改 picks。
FUND_BONUS_SHADOW = os.environ.get("FUND_BONUS_SHADOW", "1").strip().lower() not in (
    "0", "false", "no", "off",
)
# 09:35 大盘资金状态影子（超短线：买什么 / 能不能留到 T+2）。默认开，只写 jsonl。
MARKET_REGIME_SHADOW = os.environ.get("MARKET_REGIME_SHADOW", "1").strip().lower() not in (
    "0", "false", "no", "off",
)
# 09:35 板块 quality 影子：生产(quality on) vs baseline(无 quality 调整)。默认开，只写 jsonl。
SECTOR_QUALITY_SHADOW = os.environ.get("SECTOR_QUALITY_SHADOW", "1").strip().lower() not in (
    "0", "false", "no", "off",
)
# 09:35 大盘资金环境×当日双热 影子（2026-09-02 条件回测）：默认开，只写 jsonl。
# state5_q==1（5日全A主力深流出）时对池内「涨幅+净流入双热」候选打只读标记。
# 依据见 knowledge/inbox/2026-09-02-market-flow-condition-chase.md；不改分不硬剔。
MARKET_FLOW_CONDITION_SHADOW = os.environ.get(
    "MARKET_FLOW_CONDITION_SHADOW", "1"
).strip().lower() not in ("0", "false", "no", "off")
# 09:35 Wind 四线环境影子（2026-09-02）：只读昨日央妈/量化 regime 写入 market_env。
# 用户明确「以历史判断明天不稳妥」→ 永不改分、永不闸门，仅供 2-4 周后交叉对照。
WIND_REGIME_SHADOW = os.environ.get(
    "WIND_REGIME_SHADOW", "1"
).strip().lower() not in ("0", "false", "no", "off")
# 09:35 live_tone 档位影子（2026-09-03 用户拍板）：只读记录 tone×Top2 到 jsonl。
LIVE_TONE_SHADOW = os.environ.get(
    "LIVE_TONE_SHADOW", "1"
).strip().lower() not in ("0", "false", "no", "off")
# 09:35 弱市画像分影子（2026-09-03 用户拍板任务A）：对候选池打只读 weak_score
# （T-1 全市场横截面 rank 合成，bt_weak_winner_score 验证：弱市 D10 命中率 3.9 倍）。
# 永不改分不改排序，2-4 周后对照生产 Top2。
WEAK_SCORE_SHADOW = os.environ.get(
    "WEAK_SCORE_SHADOW", "1"
).strip().lower() not in ("0", "false", "no", "off")
# 09:35 量价因子（2026-09-04 WB 完整研究报告）：F1 影子权重0；V1/V2 扣分/否决；F2 Watch。
VP_FACTOR_ENABLE = os.environ.get("VP_FACTOR_ENABLE", "1").strip().lower() not in (
    "0", "false", "no", "off",
)
VP_FACTOR_SHADOW = os.environ.get("VP_FACTOR_SHADOW", "1").strip().lower() not in (
    "0", "false", "no", "off",
)



def _shadow_rerank(
    gated: list[dict],
    pool_n: int,
    expo: float,
    prod_picks: list[dict],
) -> None:
    """候选模型对 gated 池重打分，取 Top2，append 到 shadow history。

    - 与生产完全同池、同时点；只读候选模型（rd_workshop/candidates/*/models）
    - 排序口径与生产一致：money_flow_pass 优先，再按候选 score 降序
    - 任何异常都不影响生产主链路（已由调用方 try 包裹）
    """
    md = SHADOW_MODEL_DIR
    if not md or not gated:
        return
    from concurrent.futures import ThreadPoolExecutor

    import pandas as pd

    from data_fetcher import get_kline_sina
    from vm25_scorer import VM25Scorer

    log(f"▶ 影子并行试运行: 候选模型 {md} 对 gated pool n={len(gated)} 重打分 ...")
    # VM25Scorer 通过 ALPHAPILOT_MODEL_DIR / ALPHAPILOT_EXTRA_FACTORS 定位候选模型，
    # 必须显式切到候选目录，避免误用生产 models/（SHADOW_MODEL_DIR 仅本旁路使用）
    _prev_model_dir = os.environ.get("ALPHAPILOT_MODEL_DIR")
    _prev_extra = os.environ.get("ALPHAPILOT_EXTRA_FACTORS")
    os.environ["ALPHAPILOT_MODEL_DIR"] = md
    _cand_run_dir = Path(md).parent  # .../candidates/<run>/models → <run>
    _cand_extra = _cand_run_dir / "normalized_factors.parquet"
    if _cand_extra.exists():
        os.environ["ALPHAPILOT_EXTRA_FACTORS"] = str(_cand_extra)
    else:
        os.environ.pop("ALPHAPILOT_EXTRA_FACTORS", None)
    vm = VM25Scorer(prefer="opt")
    try:
        vm.load()
    finally:
        # 恢复生产环境变量，避免污染后续生产逻辑
        if _prev_model_dir is None:
            os.environ.pop("ALPHAPILOT_MODEL_DIR", None)
        else:
            os.environ["ALPHAPILOT_MODEL_DIR"] = _prev_model_dir
        if _prev_extra is None:
            os.environ.pop("ALPHAPILOT_EXTRA_FACTORS", None)
        else:
            os.environ["ALPHAPILOT_EXTRA_FACTORS"] = _prev_extra
    if not vm.models:
        log("shadow: 候选模型加载失败，跳过（不影响生产）")
        return

    def _score_one(it: dict) -> dict | None:
        sym = it.get("symbol") or ""
        if not sym:
            return None
        cache_path = ROOT / "backtest_cache" / f"{_bare(sym)}.pkl"
        k = None
        if cache_path.exists():
            try:
                k = pd.read_pickle(cache_path)
            except Exception:
                k = None
        if k is None or k.empty or len(k) < 60:
            try:
                k = get_kline_sina(_bare(sym), "20250101")
            except Exception:
                return None
        if k is None or k.empty or len(k) < 60:
            return None
        try:
            r = vm.score(k, sym, sector_heat=0.0)
        except Exception:
            return None
        if not r or "error" in r:
            return None
        return {
            "symbol": sym,
            "name": it.get("name"),
            "score": float(r.get("score") or 0),
            "proba": float(r.get("lgb_score") or 0),
            "money_flow_pass": bool(it.get("money_flow_pass")),
        }

    with ThreadPoolExecutor(max_workers=8) as ex:
        scored = [r for r in ex.map(_score_one, gated) if r]
    if not scored:
        log("shadow: gated 池全部打分失败，跳过")
        return

    passed = [r for r in scored if r.get("money_flow_pass")]
    pool = passed if passed else scored
    pool.sort(key=lambda r: r["score"], reverse=True)
    shadow_top2 = pool[:LIVE_TOP_N]

    row = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "asof": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "model_dir": md,
        "n_gated": len(gated),
        "n_scored": len(scored),
        "pool_n": pool_n,
        "position_exposure": expo,
        # 生产实际 Top2（morning_pick_rank 1..LIVE_TOP_N）；含全部候选池于 n_gated
        "prod_picks": [
            {
                "symbol": p.get("symbol"),
                "name": p.get("name"),
                "score": p.get("score"),
            }
            for p in prod_picks
            if int(p.get("morning_pick_rank") or 0) in range(1, LIVE_TOP_N + 1)
        ] or [
            {"symbol": p.get("symbol"), "name": p.get("name"), "score": p.get("score")}
            for p in (prod_picks or [])[:LIVE_TOP_N]
        ],
        "shadow_picks": [
            {"symbol": p.get("symbol"), "name": p.get("name"), "score": p.get("score"), "proba": p.get("proba")}
            for p in shadow_top2
        ],
        "step": "T0",
    }
    SHADOW_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _upsert_shadow_history(row)
    log(
        "✅ shadow Top2: "
        + ", ".join(f"{p.get('name') or p.get('symbol')}(score={p.get('score')})" for p in shadow_top2)
        + " → " + str(SHADOW_HISTORY_PATH)
    )


def _shadow_asof_hour(rec: dict) -> int | None:
    raw = str(rec.get("asof") or "")
    try:
        return int(raw[11:13])
    except (TypeError, ValueError, IndexError):
        return None


def _prefer_official_shadow(old: dict, new: dict) -> dict:
    """同一天只留一条。优先 09:xx 首笔（正式 09:35），避免救援 watcher 重跑污染。"""
    oh, nh = _shadow_asof_hour(old), _shadow_asof_hour(new)
    if oh == 9 and nh != 9:
        return old
    if oh == 9 and nh == 9:
        return old if str(old.get("asof") or "") <= str(new.get("asof") or "") else new
    if nh == 9 and oh != 9:
        return new
    return new


def _upsert_shadow_history(row: dict) -> None:
    day = str(row.get("date") or "")
    existing: list[dict] = []
    if SHADOW_HISTORY_PATH.exists():
        for line in SHADOW_HISTORY_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                existing.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    kept: list[dict] = []
    seen = False
    for rec in existing:
        if str(rec.get("date") or "") != day:
            kept.append(rec)
            continue
        if not seen:
            kept.append(_prefer_official_shadow(rec, row))
            seen = True
    if not seen:
        kept.append(row)
    tmp = SHADOW_HISTORY_PATH.with_suffix(".jsonl.tmp")
    tmp.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kept),
        encoding="utf-8",
    )
    tmp.replace(SHADOW_HISTORY_PATH)


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _bare(sym: str) -> str:
    s = str(sym or "")
    for p in ("sh", "sz", "bj", "SH", "SZ", "BJ"):
        s = s.replace(p, "")
    return s[-6:] if len(s) >= 6 else s


def _warm_live_fund(symbols: list[str]) -> None:
    try:
        from live_fund_flow import batch_fund_flow

        t0 = time.time()
        res = batch_fund_flow(symbols)
        ok = sum(1 for v in res.values() if v.get("found") is True)
        log(f"live_fund_flow warm: {ok}/{len(symbols)} ok, {time.time()-t0:.1f}s")
    except Exception as e:
        log(f"live_fund_flow warm skip: {e}")


def _merge_ths_into_items(items: list[dict]) -> list[dict]:
    try:
        from live_fund_flow import batch_fund_flow

        syms = [it.get("symbol") for it in items if it.get("symbol")]
        ths = batch_fund_flow(syms) or {}
    except Exception:
        return items
    out = []
    for it in items:
        nr = dict(it)
        sym = nr.get("symbol") or ""
        d = ths.get(sym) or ths.get(_bare(sym)) or {}
        if d:
            if d.get("main_net") is not None:
                nr["live_main_net"] = float(d.get("main_net") or 0)
            # 分层资金流（东财 ulist 正确语义，2026-08-18 修复后）
            for _src, _dst in (
                ("super_large_net", "live_super_large_net"),
                ("large_net", "live_large_net"),
                ("mid_net", "live_mid_net"),
                ("small_net", "live_small_net"),
            ):
                if d.get(_src) is not None:
                    nr[_dst] = float(d.get(_src) or 0)
            if d.get("active_buy_ratio") is not None:
                nr["live_abr"] = float(d.get("active_buy_ratio") or 0.5)
            if d.get("change_pct") is not None:
                nr["live_change_pct"] = d.get("change_pct")
            nr["live_fund_source"] = "ths_instant"
        out.append(nr)
    return out


def select_top_by_inflow(gated: list[dict], top_n: int = LIVE_TOP_N) -> list[dict]:
    """跟资金门：优先 money_flow_pass，再按主动买占比 / 主力净流入。"""

    def abr(r: dict) -> float:
        for k in ("active_buy_ratio", "live_abr"):
            try:
                return float(r.get(k) or 0)
            except (TypeError, ValueError):
                pass
        return 0.0

    def inflow_key(r: dict) -> float:
        for k in ("live_main_net", "main_net", "main_net_3d"):
            try:
                v = float(r.get(k) or 0)
            except (TypeError, ValueError):
                v = 0.0
            if abs(v) > 1e-6:
                return v
        return 0.0

    passed = [r for r in gated if r.get("money_flow_pass") is True]
    pool = passed if passed else list(gated)
    ranked = sorted(
        pool,
        key=lambda r: (abr(r), inflow_key(r), float(r.get("score") or 0)),
        reverse=True,
    )
    return ranked[:top_n]


def select_top_by_score(gated: list[dict], top_n: int = LIVE_TOP_N) -> list[dict]:
    """与网页今日推荐同序：money_flow_pass 优先，再按 score 降序。

    price_quantile_250 二次重排（book_gate 附加字段）：
      score * (1 + (q250-0.5)*STRENGTH)，±5% 微调排序，不改变模型主分数。
    """

    def score_of(r: dict) -> float:
        try:
            base = float(r.get("score") or r.get("ml_score") or r.get("lgb_score") or 0)
        except (TypeError, ValueError):
            return 0.0
        if not BOOK_RERANK_QUANTILE:
            return base
        try:
            q = float(r.get("book_price_quantile_250") or 0)
        except (TypeError, ValueError):
            q = 0.0
        if not (0.0 <= q <= 1.0):
            q = 0.5
        return base * (1.0 + (q - 0.5) * BOOK_RERANK_STRENGTH)

    passed = [r for r in gated if r.get("money_flow_pass") is True]
    pool = passed if passed else list(gated)
    return sorted(pool, key=score_of, reverse=True)[:top_n]


def _resolve_position_exposure(recs: dict) -> float:
    """recommend 缺 position_exposure 时不得当作 nuclear=0（09:35 scanner 曾漏写该字段）。"""
    raw = recs.get("position_exposure")
    if raw is not None and raw != "":
        try:
            return float(raw)
        except (TypeError, ValueError):
            pass
    try:
        from market_env_gate import load_or_build_env, position_exposure
        from permission_gate import enrich_env_with_permission

        env = load_or_build_env(force=False)
        if env.get("exposure_mode") != "permission_v1":
            enrich_env_with_permission(env, asof=env.get("asof"))
        flags = env.get("flags") or {}
        expo = float(
            env.get("position_exposure", position_exposure(flags, env.get("permission")))
        )
        log(f"expo 缺失 → 从市场环境解析为 {expo}")
        return expo
    except Exception as e:
        log(f"expo 缺失且环境门失败 → 默认 1.0 ({e})")
        return 1.0


def main() -> int:
    if not REC_PATH.exists():
        log(f"missing {REC_PATH}")
        return 1

    try:
        import subprocess

        r = subprocess.run(
            [
                sys.executable,
                "-u",
                str(ROOT / "scripts/data_readiness_gate.py"),
                "--repair",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=50 * 60,
        )
        if r.stdout:
            print(r.stdout[-3000:], flush=True)
        if r.returncode != 0:
            log("data_readiness 仍有问题（已写预警，继续选股；请看 output/data_alerts.json）")
        else:
            log("data_readiness OK")
    except Exception as e:
        log(f"data_readiness 监测异常（继续选股）: {e}")

    # 数据真实性三件套：信号冲突 / 数据质量 / 伪信号（均只读，不阻断）
    try:
        from signal_conflict_detector import detect_conflicts

        conflict = detect_conflicts()
        if conflict.get("n_conflicts"):
            log(f"⚠️ 板块信号冲突 {conflict['n_conflicts']} 个（研报 vs 资金主线 vs 竞价）→ 矛盾板块自动降权")
        else:
            log("信号冲突检测: 无冲突")
    except Exception as e:
        log(f"信号冲突检测跳过: {e}")

    try:
        from data_quality_audit import run_audit

        audit = run_audit()
        if audit.get("verdict") == "ATTENTION":
            bad = [f.get("check") for f in audit.get("findings") or [] if not f.get("ok")]
            log(f"⚠️ 数据质量审计发现 {len(bad)} 项: {bad}")
        else:
            log("数据质量审计: OK")
    except Exception as e:
        log(f"数据质量审计跳过: {e}")

    try:
        from pseudo_signal_detector import run_audit

        psa = run_audit()
        if psa.get("verdict") == "ATTENTION":
            bad = [f.get("check") for f in psa.get("findings") or [] if not f.get("ok")]
            log(f"⚠️ 伪信号检测发现 {len(bad)} 项: {bad}")
        else:
            log("伪信号检测: OK")
    except Exception as e:
        log(f"伪信号检测跳过: {e}")

    recs = json.loads(REC_PATH.read_text(encoding="utf-8"))
    items = list(recs.get("recommendations") or [])
    expo = _resolve_position_exposure(recs)
    pool_n = int(recs.get("recommend_pool_n") or len(items) or 10)
    log(f"pool loaded n={len(items)} expo={expo} pool_n={pool_n}")

    if expo <= 0:
        picks = {
            "asof": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "position_exposure": expo,
            "trade_top_n": 0,
            "picks": [],
            "empty_reason": "position_exposure_zero",
            "mode": MODE_NAME,
            "rank_by": None,
        }
        PICKS_PATH.write_text(json.dumps(picks, ensure_ascii=False, indent=2), encoding="utf-8")
        log("nuclear expo=0 → 不选股")
        return 0

    if not items:
        log("empty pool")
        picks = {
            "asof": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "position_exposure": expo,
            "trade_top_n": 0,
            "picks": [],
            "empty_reason": "empty_pool",
            "mode": MODE_NAME,
        }
        PICKS_PATH.write_text(json.dumps(picks, ensure_ascii=False, indent=2), encoding="utf-8")
        return 1

    pool = items[: max(pool_n, LIVE_TOP_N)]
    # ── ST/退市风险警示硬过滤（2026-08-25 事故：*ST威领被 Track B 买入）──
    # 从源头剔除 ST/*ST/退市股，防止 tail 回填与资金门漏网。
    _st_before = len(pool)
    _st_pool = [it for it in pool if str(it.get("name") or "").upper().find("ST") >= 0
                or str(it.get("name") or "").startswith("退")
                or "退市" in str(it.get("name") or "")]
    if _st_pool:
        pool = [it for it in pool if it not in _st_pool]
        log(
            f"⚠️ ST/退市硬过滤剔除 {len(_st_pool)} 只: "
            + ", ".join(f"{it.get('name')}({_bare(it.get('symbol'))})" for it in _st_pool[:10])
        )
    pool_snapshot = [
        {
            "symbol": it.get("symbol"),
            "name": it.get("name"),
            "score": it.get("score"),
            "rank_in_pool": i + 1,
            "overnight_bonus": it.get("overnight_bonus"),
        }
        for i, it in enumerate(pool)
    ]
    syms = [it.get("symbol") for it in pool if it.get("symbol")]
    _warm_live_fund(syms)
    pool = _merge_ths_into_items(pool)

    from money_flow_gate import apply_money_flow_gate

    # 签名自检（2026-08-24 部署漂移防护）：本脚本按新签名调用，若 money_flow_gate.py
    # 是旧版会 TypeError 崩在 09:35 链路中段 → QMT 拉 fullpool_live 404。
    # 启动即失败并给出明确提示，避免重演 08-24 早盘事故。
    try:
        import inspect

        _sig = inspect.signature(apply_money_flow_gate)
        _need = {"min_change_pct", "require_above_vwap"}
        _missing = _need - set(_sig.parameters)
        if _missing:
            raise SystemExit(
                f"money_flow_gate 版本不兼容，缺少参数: {sorted(_missing)}。"
                f"请部署与 morning_live_fund_select 配套的新版 money_flow_gate.py。"
            )
    except SystemExit:
        raise
    except Exception as _se:
        log(f"⚠️ 资金门签名自检异常（继续执行）: {_se}")

    # fund 模式：与 Top10 一致，软失败不进候选（默认不 include soft fails）
    if RANK_MODE == "fund":
        os.environ["MONEY_GATE_INCLUDE_SOFT_FAILS"] = os.environ.get(
            "MONEY_GATE_INCLUDE_SOFT_FAILS", "0"
        )
        # 研报门控统一软加权：avoid 不硬剔、prefer 加分、竞价/资金主线硬加权
        if not os.environ.get("RESEARCH_GATE_MODE"):
            os.environ["RESEARCH_GATE_MODE"] = "soft_hybrid"
    else:
        os.environ["MONEY_GATE_INCLUDE_SOFT_FAILS"] = os.environ.get(
            "MONEY_GATE_INCLUDE_SOFT_FAILS", "1"
        )
        # model 模式（生产默认）同样走 soft_hybrid：avoid 软降权、prefer 加分、竞价/主线硬加权
        if not os.environ.get("RESEARCH_GATE_MODE"):
            os.environ["RESEARCH_GATE_MODE"] = "soft_hybrid"
    log(
        f"▶ 实时资金门重跑 pool={len(pool)} "
        f"(soft_demote={os.environ['MONEY_GATE_INCLUDE_SOFT_FAILS']} "
        f"rank={RANK_MODE} research={os.environ.get('RESEARCH_GATE_MODE', 'hybrid')}) ..."
    )
    # ── 外围环境门（A50 + CNH → market_tone）──────────────────────
    # 09:30 cron 已落盘 output/market_tone.json；这里读取并按 risk_off 收紧资金门
    # （只提高「当日非上涨」门槛 min_change_pct，不改打分、不硬剔板块；缺失 → neutral 不阻断）。
    market_tone_meta = {"enabled": False, "tone": "neutral"}
    _min_change_pct = 0.0
    try:
        from market_tone import load as load_market_tone

        _mt = load_market_tone()
        market_tone_meta = {
            "enabled": bool(_mt.get("enabled")),
            "tone": _mt.get("tone") or "neutral",
            "score": _mt.get("score"),
            "reasons": _mt.get("reasons"),
            "gate": _mt.get("gate"),
            "asof": _mt.get("asof"),
        }
        _min_change_pct = float((_mt.get("gate") or {}).get("min_change_pct") or 0.0)
        log(
            f"外围环境门: tone={market_tone_meta['tone']} "
            f"score={_mt.get('score')} min_change_pct={_min_change_pct} "
            f"({', '.join(_mt.get('reasons') or ['no_reason'])})"
        )
    except Exception as e:
        log(f"外围环境门读取失败（按 neutral 处理）: {e}")

    gated = apply_money_flow_gate(
        pool,
        top_n=None,
        hard_main_net_5d=True,
        min_change_pct=_min_change_pct,
        require_above_vwap=True,
    )
    log(f"资金门后: {len(gated)} pass={sum(1 for x in gated if x.get('money_flow_pass') is True)}")

    fund_drop = []
    gated_codes = {_bare(x.get("symbol")) for x in gated}
    for it in pool:
        code = _bare(it.get("symbol"))
        if code not in gated_codes:
            fund_drop.append(
                {
                    "symbol": it.get("symbol"),
                    "name": it.get("name"),
                    "score": it.get("score"),
                    "reason": "money_fund_hard_fail",
                    "detail": it.get("money_warning") or it.get("drop_reason"),
                }
            )

    research_meta = {}
    research_drops = []
    try:
        from research_sector_gate import apply_research_sector_gate, load_bias

        bias = load_bias()
        before = len(gated)
        gated = apply_research_sector_gate(gated, bias=bias)
        meta = {}
        if gated and isinstance(gated[0].get("_research_gate_meta"), dict):
            meta = gated[0].pop("_research_gate_meta", {}) or {}
        for row in gated:
            row.pop("_research_drop_log", None)
        research_drops = list(meta.get("dropped") or [])
        research_meta = {
            "enabled": True,
            "mode": os.environ.get("RESEARCH_GATE_MODE", "soft_hybrid"),
            "bias_date": (bias or {}).get("date"),
            "bias_session": (bias or {}).get("session"),
            "prefer": (bias or {}).get("prefer") or [],
            "avoid": (bias or {}).get("avoid") or [],
            "before": before,
            "after": len(gated),
            "prefer_hits": meta.get("prefer_hits"),
            "avoid_drop": meta.get("avoid_drop"),
            "soft_avoid": meta.get("soft_avoid"),
            "auction_hits": meta.get("auction_hits"),
            "bypass_hits": meta.get("bypass_hits"),
            "conflict_hits": meta.get("conflict_hits"),
            "narrowed": meta.get("narrowed"),
            "prefer_boost": meta.get("prefer_boost"),
            "note": "收盘研报=多日资金结构趋势；外盘隔夜=次日映射优势（权重更大）",
        }
        log(
            f"研报门控后: {len(gated)} "
            f"(bias={research_meta.get('bias_date')}/{research_meta.get('bias_session')} "
            f"prefer_hits={research_meta.get('prefer_hits')} "
            f"avoid_drop={research_meta.get('avoid_drop')})"
        )
    except Exception as e:
        research_meta = {"enabled": False, "error": str(e)}
        log(f"研报门控跳过: {e}")

    gated = _merge_ths_into_items(gated)
    hithink_meta = {"enabled": False}
    try:
        from hithink_p2_side import apply_hithink_p2_side

        gated, hithink_meta = apply_hithink_p2_side(gated, log=log)
    except Exception as e:
        hithink_meta = {"enabled": False, "error": str(e)[:200]}
        log(f"同花顺P2旁支跳过: {e}")

    # ── 资金指纹板块方向软加分（2026-08-25） ─────────────────────────
    # 来源: scripts/sector_fingerprint_report.py（05:00 管线后运行，企业微信晨报）
    # 保守模式：仅当「行业资金动量失效」(rankic_5d_flow_t1 近20日均值<0) 时启用。
    # 指纹 H+5 领涨行业 → score*=(1+boost)；其余 → score*=(1-penalty)；绝不硬剔。
    # 动量有效日完全跳过，不影响选股。
    fp_meta = {"enabled": False, "mode": "inactive", "reason": "momentum_healthy"}
    try:
        _fp_path = ROOT / "output" / "sector_fingerprint_daily.json"
        if _fp_path.exists():
            _fp = json.loads(_fp_path.read_text(encoding="utf-8"))
            _fp_mom = _fp.get("momentum") or {}
            if _fp_mom.get("fail") is True:
                _fp_h5 = ((_fp.get("sector_prediction") or {}).get("H+5") or {}).get("sectors") or []
                _fp_top = set(_fp_h5[:6])
                if _fp_top:
                    try:
                        _fp_boost = float(os.environ.get("SECTOR_FP_BOOST", "0.05") or 0.05)
                    except (TypeError, ValueError):
                        _fp_boost = 0.05
                    try:
                        _fp_pen = float(os.environ.get("SECTOR_FP_PENALTY", "0.02") or 0.02)
                    except (TypeError, ValueError):
                        _fp_pen = 0.02
                    fp_hit = 0
                    fp_miss = 0
                    for it in gated:
                        _lbls = str(it.get("industry_l1") or it.get("industry") or it.get("sector") or "").strip()
                        if not _lbls:
                            continue
                        if _lbls in _fp_top:
                            fp_hit += 1
                            _sb = float(it.get("score") or 0)
                            it["score_before_sector_fp"] = round(_sb, 4)
                            it["score"] = round(_sb * (1.0 + _fp_boost), 4)
                            it["sector_fp_boost"] = round(_fp_boost, 4)
                            it["sector_fp_hit"] = _lbls
                        else:
                            fp_miss += 1
                            _sb = float(it.get("score") or 0)
                            it["score_before_sector_fp"] = round(_sb, 4)
                            it["score"] = round(_sb * (1.0 - _fp_pen), 4)
                            it["sector_fp_penalty"] = round(_fp_pen, 4)
                            it["sector_fp_miss"] = _lbls
                    fp_meta = {
                        "enabled": True,
                        "mode": "soft_active",
                        "asof": _fp.get("asof"),
                        "rankic_5d_flow_t1": _fp_mom.get("rankic_5d_flow_t1"),
                        "h5_top": sorted(_fp_top),
                        "boost": _fp_boost,
                        "penalty": _fp_pen,
                        "hit": fp_hit,
                        "miss": fp_miss,
                        "n": len(gated),
                    }
                    log(
                        f"资金指纹软加分[soft_active]: h5_top={sorted(_fp_top)} "
                        f"boost={_fp_boost} penalty={_fp_pen} hit={fp_hit} miss={fp_miss} n={len(gated)}"
                    )
            else:
                fp_meta = {
                    "enabled": True,
                    "mode": "inactive",
                    "reason": "momentum_healthy",
                    "asof": _fp.get("asof"),
                    "rankic_5d_flow_t1": _fp_mom.get("rankic_5d_flow_t1"),
                }
                log(
                    f"资金指纹软加分跳过（动量有效 rankic={_fp_mom.get('rankic_5d_flow_t1')}）"
                )
    except Exception as _fpe:
        fp_meta = {"enabled": False, "mode": "error", "error": str(_fpe)[:200]}
        log(f"资金指纹软加分跳过: {_fpe}")

    # ── 量价因子 V1/V2 扣分 + F1 影子（2026-09-04 WB 完整研究报告）──
    # F1 权重默认 0（只记日志）；V1/V2 对 gated 扣分，V1 默认可硬否决。
    vp_meta = {"enabled": False}
    if VP_FACTOR_ENABLE:
        try:
            from vp_factor_shadow import annotate_and_penalize

            gated, vp_meta = annotate_and_penalize(gated)
            log(
                f"量价因子: weak={((vp_meta.get('regime') or {}).get('weak'))} "
                f"f1={vp_meta.get('n_f1')} v1={vp_meta.get('n_v1')} "
                f"v2={vp_meta.get('n_v2')} f2={vp_meta.get('n_f2')} "
                f"v1_drop={vp_meta.get('v1_dropped')} f1_w={vp_meta.get('f1_weight')}"
            )
        except Exception as e:
            vp_meta = {"enabled": False, "error": str(e)[:200]}
            log(f"量价因子跳过（不影响生产主链）: {e}")

    # ── 板块资金双层软层（2026-08-25）CapitalPulse 实时跟资金 + 前日 EOD 延续 ──
    # A) 今日板块净流入 → 正向加分（跟今天的钱）
    # B) 前一日 EOD 持续主线 → 沿用加分；前日一日游/脉冲 → 降分
    sq_meta = {"enabled": False, "mode": "off"}
    try:
        from sector_flow_quality import apply_sector_quality_soft

        gated, sq_meta = apply_sector_quality_soft(gated, log=log)
    except Exception as _sqe:
        sq_meta = {"enabled": False, "mode": "error", "error": str(_sqe)[:200]}
        log(f"板块quality软层跳过: {_sqe}")

    if RANK_MODE == "fund":
        chosen = select_top_by_inflow(gated, top_n=LIVE_TOP_N)
        rank_by = "money_flow_pass+abr+live_main_net"
    else:
        chosen = select_top_by_score(gated, top_n=LIVE_TOP_N)
        rank_by = "money_flow_pass+score"

    chosen_codes = {_bare(x.get("symbol")) for x in chosen}
    not_top = []
    for it in gated:
        code = _bare(it.get("symbol"))
        if code not in chosen_codes:
            not_top.append(
                {
                    "symbol": it.get("symbol"),
                    "name": it.get("name"),
                    "score": it.get("score"),
                    "research_tier": it.get("research_tier"),
                    "reason": "survived_but_not_topN",
                    "money_soft_demote": bool(it.get("money_soft_demote")),
                }
            )

    live_ranked = select_top_by_score(gated, top_n=max(len(gated), LIVE_TOP_N))
    code_keep = {_bare(x.get("symbol")) for x in live_ranked}
    tail = [it for it in pool if _bare(it.get("symbol")) not in code_keep]
    new_recs = live_ranked + tail

    for it in new_recs:
        it["position_exposure"] = expo
        it["morning_live_ranked"] = True
    # 候选池排名: Top2 为最终推荐(1-2), 其余候选池按 live_ranked 顺序标记 3..N
    chosen_codes2 = {_bare(x.get("symbol")) for x in chosen}
    cand = live_ranked[:PICKS_CANDIDATE_N] if expo > 0 else []
    _cand_rank = 0
    for it in cand:
        code = _bare(it.get("symbol"))
        if code in chosen_codes2:
            it["morning_pick_rank"] = next(
                (i + 1 for i, x in enumerate(chosen) if _bare(x.get("symbol")) == code), 1
            )
        else:
            _cand_rank += 1
            it["morning_pick_rank"] = LIVE_TOP_N + _cand_rank

    recs["recommendations"] = new_recs[: max(pool_n, len(chosen))]
    recs["position_exposure"] = expo
    recs["recommend_top_n"] = LIVE_TOP_N if expo > 0 else 0
    recs["recommend_pool_n"] = pool_n
    recs["candidate_top_n"] = len(cand)
    recs["asof"] = datetime.now().strftime("%Y-%m-%d")
    recs["morning_live_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    recs["morning_live_mode"] = MODE_NAME
    recs["sector_fp_meta"] = fp_meta
    recs["sector_quality_meta"] = sq_meta
    recs["protocol"] = recs.get("protocol") or "live_momentum_full_universe"
    REC_PATH.write_text(json.dumps(recs, ensure_ascii=False, indent=2), encoding="utf-8")

    pick_rows = []
    for r in cand:
        pick_rows.append(
            {
                "symbol": r.get("symbol"),
                "name": r.get("name"),
                "score": r.get("score"),
                "research_tier": r.get("research_tier"),
                "research_prefer_hit": r.get("research_prefer_hit"),
                "main_net": r.get("main_net"),
                "live_main_net": r.get("live_main_net"),
                "active_buy_ratio": r.get("active_buy_ratio") or r.get("live_abr"),
                "money_phase_label": r.get("money_phase_label"),
                "buy_price": r.get("buy_price") or r.get("price"),
                "target_price": r.get("target_price"),
                "stop_price": r.get("stop_price"),
                "position_exposure": expo,
                "overnight_bonus": r.get("overnight_bonus"),
                "morning_pick_rank": r.get("morning_pick_rank"),
                "hithink_hot_rank": r.get("hithink_hot_rank"),
                "hithink_limit_up": r.get("hithink_limit_up"),
                "hithink_auction_pct": r.get("hithink_auction_pct"),
                "hithink_side_note": r.get("hithink_side_note"),
                "hithink_side_mult": r.get("hithink_side_mult"),
            }
        )

    # 收集检测器结果摘要（若已运行）
    _quality_meta = {}
    try:
        if (OUT_PATH := ROOT / "output" / "signal_conflicts.json").exists():
            sc = json.loads(OUT_PATH.read_text(encoding="utf-8"))
            _quality_meta["signal_conflicts"] = {
                "n": sc.get("n_conflicts", 0),
                "top": [c.get("sector") for c in (sc.get("conflicts") or [])[:5]],
            }
        if (qa_path := ROOT / "output" / "data_quality_audit.json").exists():
            qa = json.loads(qa_path.read_text(encoding="utf-8"))
            _quality_meta["data_quality"] = qa.get("verdict")
        if (ps_path := ROOT / "output" / "pseudo_signal_audit.json").exists():
            ps = json.loads(ps_path.read_text(encoding="utf-8"))
            _quality_meta["pseudo_signal"] = ps.get("verdict")
    except Exception:
        pass

    # Wind 四线环境（昨日已知，只读）：失败不影响生产
    _wind_env_meta: dict = {"ok": False, "reason": "shadow_off"}
    if WIND_REGIME_SHADOW:
        try:
            from wind_regime_shadow import load_env as _wind_load_env

            _wind_env_meta = _wind_load_env(
                datetime.now().strftime("%Y-%m-%d")
            )
        except Exception as e:
            _wind_env_meta = {"ok": False, "reason": f"err:{e}"}

    picks = {
        "asof": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "position_exposure": expo,
        "trade_top_n": LIVE_TOP_N,
        "picks": pick_rows,
        "pool_size": len(pool),
        "gated_size": len(gated),
        "empty_reason": None if pick_rows else "no_survivor_after_gates",
        "mode": MODE_NAME,
        "rank_by": rank_by,
        "research_gate": research_meta,
        "hithink_p2_side": hithink_meta,
        "market_tone": market_tone_meta,
        "market_env": _wind_env_meta,
        "data_quality": _quality_meta,
        "vp_factors": {
            k: v for k, v in (vp_meta or {}).items() if k != "_feats"
        },
    }
    PICKS_PATH.write_text(json.dumps(picks, ensure_ascii=False, indent=2), encoding="utf-8")

    elim = {
        "asof": picks["asof"],
        "pool": pool_snapshot,
        "picks": [
            {"symbol": p.get("symbol"), "name": p.get("name"), "score": p.get("score")}
            for p in pick_rows
        ],
        "eliminated": fund_drop + research_drops + not_top,
        "summary": {
            "pool_n": len(pool),
            "fund_hard_drop": len(fund_drop),
            "research_drop": len(research_drops),
            "survived_not_top": len(not_top),
            "chosen": len(pick_rows),
        },
        "how_to_read": {
            "money_fund_hard_fail": "资金/估值硬淘（深流出、无参与、PE）",
            "research_avoid": "命中盘前研报 avoid 板块",
            "not_in_prefer_narrow": "有 prefer 命中时被缩池挤出",
            "survived_but_not_topN": "过门后分数未进买入 TopN",
            "soft_fail_demote": "资金软门未过，已降权仍可参与排序",
        },
    }
    ELIM_PATH.write_text(json.dumps(elim, ensure_ascii=False, indent=2), encoding="utf-8")

    log(
        f"✅ morning picks Top{LIVE_TOP_N} [{RANK_MODE}/{rank_by}]: "
        + ", ".join(
            f"{p.get('name') or p.get('symbol')}(score={p.get('score')},tier={p.get('research_tier')})"
            for p in pick_rows
        )
    )
    log(
        f"淘汰清单: fund_hard={len(fund_drop)} research={len(research_drops)} "
        f"not_top={len(not_top)} → {ELIM_PATH}"
    )

    # 影子并行试运行（RD 晋升加速路径 A）：生产 Top2 已写入后，再对同池用候选模型重打分
    # 仅当 SHADOW_MODEL_DIR 设置才激活；任何异常都不影响生产（已 try 包裹）
    if SHADOW_MODEL_DIR:
        try:
            _shadow_rerank(gated, pool_n, expo, pick_rows)
        except Exception as e:
            log(f"shadow 旁路异常（不影响生产）: {e}")
    if FUND_BONUS_SHADOW:
        try:
            from fund_bonus_shadow import write_shadow

            p = write_shadow(gated, pick_rows)
            if p:
                log(f"fund-bonus shadow appended → {p} (production picks unchanged)")
        except Exception as e:
            log(f"fund-bonus shadow skip（不影响生产）: {e}")
    if MARKET_REGIME_SHADOW:
        try:
            from market_regime_shadow import write_shadow as write_regime_shadow

            p = write_regime_shadow(gated, pick_rows)
            if p:
                log(f"market-regime shadow appended → {p} (production picks unchanged)")
        except Exception as e:
            log(f"market-regime shadow skip（不影响生产）: {e}")
    if SECTOR_QUALITY_SHADOW:
        try:
            from sector_quality_shadow import write_shadow

            p = write_shadow(gated, pick_rows, sq_meta)
            if p:
                log(f"sector-quality shadow appended → {p} (prod=quality on, baseline=no adjust)")
        except Exception as e:
            log(f"sector-quality shadow skip（不影响生产）: {e}")
    if MARKET_FLOW_CONDITION_SHADOW:
        try:
            from market_flow_condition_shadow import write_shadow as write_mfc_shadow

            p = write_mfc_shadow(gated, pick_rows)
            if p:
                log(f"market-flow-condition shadow appended → {p} (production unchanged)")
        except Exception as e:
            log(f"market-flow-condition shadow skip（不影响生产）: {e}")
    if WIND_REGIME_SHADOW:
        try:
            from wind_regime_shadow import write_shadow as write_wind_shadow

            p = write_wind_shadow(gated, pick_rows)
            if p:
                log(f"wind-regime shadow appended → {p} (production unchanged)")
        except Exception as e:
            log(f"wind-regime shadow skip（不影响生产）: {e}")
    if WEAK_SCORE_SHADOW:
        try:
            from weak_score_shadow import write_shadow as write_weak_shadow

            p = write_weak_shadow(gated, pick_rows)
            if p:
                log(f"weak-score shadow appended → {p} (production unchanged)")
        except Exception as e:
            log(f"weak-score shadow skip（不影响生产）: {e}")
    if LIVE_TONE_SHADOW:
        try:
            from live_tone_shadow import write_shadow as write_tone_shadow

            p = write_tone_shadow(gated, pick_rows, market_tone_meta)
            if p:
                log(f"live-tone shadow appended → {p} (production unchanged)")
        except Exception as e:
            log(f"live-tone shadow skip（不影响生产）: {e}")
    if VP_FACTOR_SHADOW:
        try:
            from vp_factor_shadow import write_shadow as write_vp_shadow

            p = write_vp_shadow(gated, pick_rows, vp_meta if isinstance(vp_meta, dict) else None)
            if p:
                log(f"vp-factor shadow appended → {p} (F1 weight=0, production picks unchanged)")
        except Exception as e:
            log(f"vp-factor shadow skip（不影响生产）: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
