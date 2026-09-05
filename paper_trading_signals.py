"""Paper Trading 信号更新 — 09:36 消费盘中选股结果

协议（生产）：
1. 09:35 live_momentum 全市场重选 → daily_recommend
2. morning_live_fund_select（默认 MORNING_RANK_MODE=model）→ morning_live_picks Top2
   与网页「今日推荐」同序：资金门后按 score
3. 本脚本优先读今日且 mode=model 的 picks；fund 旧臂或过期则重跑
4. expo<=0 → 不买；否则买入 TopN
5. 仓位：KELLY_ENABLE=1 时 Kelly；否则等权
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "/home/ubuntu/alphapilot")

from fusion_scorer import fusion_rerank

ROOT = Path("/home/ubuntu/alphapilot")
REC_PATH = ROOT / "output/daily_recommend.json"
PICKS_PATH = ROOT / "output/morning_live_picks.json"
PT_PATH = ROOT / "data/paper_trading.json"
DEFAULT_TOP_N = 2
STRAT_ID = "v19_daily"
STRAT_NAME = "日频精选"
VALID_PICK_MODES = frozenset(
    {"morning_live_model_top2", "morning_live_fund_top2"}
)

# ── V2 升级门控整合（2026-08-05 合并：原 v19_daily_v2 的四道升级因子并入 v19_daily）──
MERGE_V2_GATES = os.environ.get("MERGE_V2_GATES", "1").strip().lower() not in (
    "0", "false", "no", "off",
)
V2_VOL_GATE_MAX = float(os.environ.get("V2_VOL_GATE_MAX", "3.5"))
V2_OPEN_GAP_ON = os.environ.get("V2_OPEN_GAP", "1") == "1"


def _v2_sentiment_gate():
    """升级4: 情绪周期门控。返回 (allowed, stage)，异常放行。"""
    try:
        import market_sentiment
        r = market_sentiment.main()
        return r["trade_allowed"], r["stage"]
    except Exception as e:
        print(f"  情绪门控异常(放行): {e}")
        return True, "error"


def _v2_vol_gate(picks):
    """升级1: 波动率门控。返回 (kept, n_blocked)，异常放行。"""
    if not picks:
        return picks, 0
    try:
        from vol_gate import get_vol20
        kept, blocked = [], []
        for r in picks:
            sym = str(r.get("symbol", "")).zfill(6)
            vol = get_vol20(sym)
            if vol is None or vol <= V2_VOL_GATE_MAX:
                kept.append(r)
            else:
                blocked.append((sym, vol))
        if blocked:
            print("  vol_gate 拦截 {} 只高波动: {}".format(
                len(blocked), ", ".join(f"{s}({v:.1f}%)" for s, v in blocked[:6])))
        return kept, len(blocked)
    except Exception as e:
        print(f"  vol_gate 异常(放行): {e}")
        return picks, 0


def _v2_hard_filter(picks):
    """升级2: 事实性硬删除 (ST/亏损/利空)。返回过滤后的候选。"""
    try:
        from hard_filter import hard_filter as hf
        items = [(str(r.get("symbol", "")).zfill(6), r.get("name", "")) for r in picks]
        keep_items, detail = hf(items)
        keep_set = set((s, n) for s, n in keep_items)
        kept = [p for p in picks if (str(p.get("symbol", "")).zfill(6), p.get("name", "")) in keep_set]
        blocked = len(picks) - len(kept)
        if blocked:
            print("  hard_filter 硬删除 {} 只: ST={} 亏损={} 利空={}".format(
                blocked, len(detail["st"]), len(detail["loss"]), len(detail["news"])))
        return kept
    except Exception as e:
        print(f"  hard_filter 异常(放行): {e}")
        return picks


def _v2_multifactor(picks):
    """升级3: 多因子打分 + Q1 差组过滤。返回过滤后的候选。"""
    if not V2_OPEN_GAP_ON or not picks:
        return picks
    try:
        from multifactor_score import batch_score
        picks = batch_score(picks)
    except Exception as e:
        print(f"  multifactor 打分异常(原样返回): {e}")
        return picks
    _before = len(picks)
    picks = [p for p in picks if float(p.get("_score_adj", 0) or 0) >= -0.05]
    _dropped = _before - len(picks)
    if _dropped:
        print(f"  Q1差组过滤: 剔除 {_dropped} 只低分股")
    return picks


def apply_v2_gates(top, expo, top_n):
    """合并后的统一门控链: 情绪 → 波动率 → 硬过滤 → 多因子/Q1。
    返回过滤后的候选池(不做排名截取, 由主链 fusion_rerank + TopN 收尾)。
    情绪拦截/空仓时返回空列表。"""
    if not MERGE_V2_GATES or expo <= 0 or top_n <= 0:
        return top
    # 1. 情绪周期门控（全局面控）
    sent_allowed, stage = _v2_sentiment_gate()
    print(f"  情绪门控: stage={stage} allowed={sent_allowed}")
    if not sent_allowed:
        print("  ⚠️ 情绪门控拦截: 今日不开新仓")
        return []
    # 2. 候选池扩展: 原 picks + daily_recommend 前36只（给门控留过滤空间）
    pool = list(top)
    try:
        d = json.loads(REC_PATH.read_text(encoding="utf-8"))
        recs = sorted(d.get("recommendations") or [], key=lambda r: -float(r.get("score", 0) or 0))[:36]
        seen = {r.get("symbol") for r in pool}
        pool += [r for r in recs if r.get("symbol") not in seen]
    except Exception:
        pass
    # 3. 波动率门控
    pool, n_blocked = _v2_vol_gate(pool)
    if n_blocked:
        print(f"  波动率门控: 拦截 {n_blocked} 只, 剩余 {len(pool)}")
    # 4. 硬过滤
    pool = _v2_hard_filter(pool)
    # 5. 多因子打分 + Q1 过滤
    pool = _v2_multifactor(pool)
    return pool


EXCLUDE_PATH = ROOT / "config/exclude_symbols.json"


def _load_exclude_symbols() -> set[str]:
    """读取排除列表（模拟盘不交易的股票）。"""
    try:
        if EXCLUDE_PATH.exists():
            data = json.loads(EXCLUDE_PATH.read_text(encoding="utf-8"))
            syms = data.get("symbols") or []
            names = data.get("names") or []
            if syms:
                print("  [排除] {} 只股票被排除出模拟盘: {}".format(
                    len(syms), ", ".join(names or syms)))
            return set(str(s).zfill(6) for s in syms)
    except Exception as e:
        print("  [排除] 读取排除列表失败: {}".format(e))
    return set()


def ensure_daily_strategy(pt: dict) -> dict:
    for s in pt.get("strategies") or []:
        if s.get("id") == STRAT_ID:
            s["name"] = STRAT_NAME
            s["status"] = s.get("status") or "active"
            s.setdefault("allocated", 500000)
            s.setdefault("used", 0)
            s.setdefault("positions", [])
            s.setdefault("signals", [])
            return s
    s = {
        "id": STRAT_ID,
        "name": STRAT_NAME,
        "status": "active",
        "allocated": 500000,
        "used": 0,
        "positions": [],
        "signals": [],
    }
    pt.setdefault("strategies", []).insert(0, s)
    return s


def _picks_fresh(picks: dict) -> bool:
    """今日 + 生产 model 臂才视为新鲜（拒绝过期 fund Top2 / 误空仓）。"""
    asof = str(picks.get("asof") or "")
    today = datetime.now().strftime("%Y-%m-%d")
    mode = str(picks.get("mode") or "")
    if not asof.startswith(today):
        return False
    if mode == "morning_live_fund_top2" and os.environ.get("ALLOW_FUND_PICKS", "").strip() in (
        "1",
        "true",
        "yes",
    ):
        return True
    if mode != "morning_live_model_top2":
        return False
    n = len(picks.get("picks") or [])
    if n > 0:
        return True
    # 仅真核武空仓视为有效空结果；其它空文件强制重跑
    try:
        expo = float(
            picks.get("position_exposure")
            if picks.get("position_exposure") is not None
            else 1.0
        )
    except (TypeError, ValueError):
        expo = 1.0
    return expo <= 0 and picks.get("empty_reason") == "position_exposure_zero"


def _ensure_morning_picks() -> dict:
    # 强制生产默认与今日推荐同口径
    os.environ.setdefault("MORNING_RANK_MODE", "model")
    if PICKS_PATH.exists():
        try:
            picks = json.loads(PICKS_PATH.read_text(encoding="utf-8"))
            if _picks_fresh(picks):
                return picks
            print(
                "⚠️ morning_live_picks 过期或非 model 臂 "
                f"(asof={picks.get('asof')} mode={picks.get('mode')}) → 重跑"
            )
        except Exception:
            pass
    # 现场补跑 09:35 逻辑（score Top2）
    print("⚠️ morning_live_picks 非今日/缺失 → 现场重跑 morning_live_fund_select (model)")
    try:
        import morning_live_fund_select as mls

        mls.main()
        return json.loads(PICKS_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"morning select failed: {e}")
        # 回退：用 recommend 池按模型分取 Top2
        d = json.loads(REC_PATH.read_text(encoding="utf-8"))
        expo = float(
            d.get("position_exposure") if d.get("position_exposure") is not None else 1.0
        )
        items = list(d.get("recommendations") or [])
        try:
            from money_flow_gate import apply_money_flow_gate

            # 签名自检（2026-08-24）：旧版 money_flow_gate 会静默降级，加日志便于发现漂移。
            import inspect

            _need = {"min_change_pct", "require_above_vwap"}
            if not _need.issubset(set(inspect.signature(apply_money_flow_gate).parameters)):
                print("[paper_trading_signals] ⚠️ money_flow_gate 版本旧，资金门将静默降级", flush=True)
            items = apply_money_flow_gate(items, top_n=None, min_change_pct=0.0, require_above_vwap=True)
            passed = [x for x in items if x.get("money_flow_pass") is True]
            if passed:
                items = passed
        except Exception:
            pass
        items.sort(
            key=lambda x: float(x.get("score") or x.get("ml_score") or 0),
            reverse=True,
        )
        cand_n = int(os.environ.get("PICKS_CANDIDATE_N", "10"))
        top = items[:cand_n] if expo > 0 else []
        return {
            "asof": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "position_exposure": expo,
            "trade_top_n": DEFAULT_TOP_N if expo > 0 else 0,
            "candidate_top_n": len(top),
            "picks": top,
            "mode": "morning_live_model_top2",
            "rank_by": "score",
            "empty_reason": None if top else "fallback_empty",
        }


def main():
    picks = _ensure_morning_picks()

    # ── P3 交易前数据新鲜度闸门 ──
    _skip_freshness_gate = os.environ.get("BYPASS_FRESHNESS_GATE", "0").strip().lower() in (
        "1", "true", "yes", "on"
    )
    _block_reason = None
    # 检查 1: health_alarm.json
    _health = ROOT / "output/health_alarm.json"
    if not _skip_freshness_gate and _health.exists():
        try:
            _ha = json.loads(_health.read_text(encoding="utf-8"))
            if not _ha.get("healthy", True):
                _block_reason = f"P3 gate: {_ha.get('summary', 'health check failed')}"
                print(f"\n{'='*70}\n🚫 P3 闸门: 管线健康检查异常 — {_ha.get('summary')}\n详情: {_health}{'='*70}")
        except Exception:
            pass
    # 检查 2: daily_recommend.json 新鲜度
    if not _skip_freshness_gate and _block_reason is None and REC_PATH.exists():
        try:
            _rec = json.loads(REC_PATH.read_text(encoding="utf-8"))
            _asof = str(_rec.get("run_at") or _rec.get("generated_at") or "")[:10]
            _today = datetime.now().strftime("%Y-%m-%d")
            if _asof != _today and _asof != "":
                _n = len(_rec.get("recommendations", []))
                _block_reason = f"P3 gate: daily_recommend asof={_asof} != today ({_today}), candidates={_n}"
                print(f"\n{'='*70}\n🚫 P3 闸门: daily_recommend 过期 (asof={_asof}) 仅 {_n} 只候选\n{'='*70}")
        except Exception:
            pass
    # 检查 3: morning_live_picks.json 新鲜度
    if not _skip_freshness_gate and _block_reason is None and PICKS_PATH.exists():
        try:
            _pk = json.loads(PICKS_PATH.read_text(encoding="utf-8"))
            _asof = str(_pk.get("asof") or "")[:10]
            if _asof != datetime.now().strftime("%Y-%m-%d"):
                _block_reason = f"P3 gate: morning_live_picks asof={_asof} != today"
                print(f"\n{'='*70}\n🚫 P3 闸门: morning_live_picks 过期 (asof={_asof})\n{'='*70}")
        except Exception:
            pass
    if _block_reason:
        print(f"\n🚫 阻断交易: {_block_reason}")
        print("设置 BYPASS_FRESHNESS_GATE=1 可跳过此检查\n")
        pt = json.loads(PT_PATH.read_text(encoding="utf-8")) if PT_PATH.exists() else {}
        pt["p3_gate_blocked"] = True
        pt["p3_gate_reason"] = _block_reason
        PT_PATH.write_text(json.dumps(pt, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    # 若存在数据预警，醒目打印（不阻断）
    alert_path = ROOT / "output/data_alerts.json"
    if alert_path.exists():
        try:
            al = json.loads(alert_path.read_text(encoding="utf-8"))
            if al.get("status") and al.get("status") != "ok":
                print("=" * 70)
                print(f"⚠️ 数据预警 [{al.get('status')}]: {al.get('message')}")
                for it in (al.get("issues") or [])[:8]:
                    print(f"  - [{it.get('severity')}] {it.get('key')}: {it.get('reason')}")
                print(f"详情: {alert_path}")
                print("=" * 70)
        except Exception:
            pass

    expo = float(picks.get("position_exposure") or 0.0)
    top = list(picks.get("picks") or [])
    top_n = int(picks.get("trade_top_n") or (DEFAULT_TOP_N if expo > 0 else 0))

    # ── V2 升级门控统一整合（情绪/波动率/硬过滤/多因子/Q1）──
    top = apply_v2_gates(top, expo, top_n)
    if top:
        print(f"  V2 门控链完成: 候选池 {len(top)} 只")
    if not top:
        top = []

    # ── Phase 2-3: 三路融合评分 + 按融合分重排 ──
    try:
        before = len(top)
        top = fusion_rerank(top)
        if top and top[0].get("_fusion_weight") is not None:
            print(
                "  融合排序完成: {} 只, top1 _fusion_weight={:.4f}".format(
                    len(top), top[0]["_fusion_weight"]
                )
            )
    except Exception as exc:
        print(f"  ⚠️ fusion_rerank 异常 (skip): {exc}")

    # 候选池大小: 先到先得需要完整候选池(默认10), 不再硬截断到 top_n
    candidate_n = int(picks.get("candidate_top_n") or max(top_n, DEFAULT_TOP_N))
    if len(top) > candidate_n:
        top = top[:candidate_n]
    print(f"  候选池: {len(top)} 只 (先到先得, 每日最多买 {top_n})")

    # 排除列表过滤（不交易、不计入统计）
    _excluded = _load_exclude_symbols()
    if _excluded:
        _before = len(top)
        top = [r for r in top if str(r.get("symbol", "")).zfill(6) not in _excluded]
        if len(top) < _before:
            print("  [排除] 过滤掉 {} 只黑名单股票, 剩余 {} 只备选".format(_before - len(top), len(top)))
            # 池子不够时从 recommend 补位
            if len(top) < candidate_n and _excluded:
                try:
                    d = json.loads(REC_PATH.read_text(encoding="utf-8"))
                    all_items = list(d.get("recommendations") or [])
                    held_syms = {str(r.get("symbol", "")).zfill(6) for r in top}
                    for r in all_items:
                        sym = str(r.get("symbol", "")).zfill(6)
                        if sym not in held_syms and sym not in _excluded:
                            top.append(r)
                            if len(top) >= candidate_n:
                                break
                except Exception:
                    pass
            top = top[:candidate_n]

    # ── 在线增量学习：每日更新 Kelly 模型 ──
    _kelly_hist_stats = None
    try:
        from kelly_learner import KellyLearner
        _kl = KellyLearner()
        _kl.train()  # 在线重训 LR
        _kelly_hist_stats = _kl.get_hist_stats()
        _ml_ready = _kelly_hist_stats.get("ml_ready", False)
        print(
            "  KellyLearner 在线重训完成: {} trades, ml_ready={}".format(
                _kelly_hist_stats.get("n_trades", 0), _ml_ready
            )
        )
    except ImportError:
        _kelly_hist_stats = None
        print("  KellyLearner 未安装（skip 在线学习）")
    except Exception as e:
        _kelly_hist_stats = None
        print(f"  KellyLearner 异常 (fallback 静态): {e}")

    # ── Kelly + 风险预算仓位分配 ──
    # 预加载 pt (正常路径下尚未赋值, 需读取账户现金供 Kelly 使用)
    try:
        pt = json.loads(PT_PATH.read_text(encoding="utf-8")) if PT_PATH.exists() else {}
    except Exception:
        pt = {}
    try:
        from kelly_sizing import apply_kelly, calibrate_from_backtest, KELLY_ENABLE

        if KELLY_ENABLE:
            equity = float(pt.get("account", {}).get("cash", 0)) if "account" in (pt or {}) else 0
            if equity <= 0:
                equity = float(pt.get("initial_capital") or 1_000_000)
            # 校准统计（首次或文件过期时重跑）
            if _kelly_hist_stats is not None and _kelly_hist_stats.get("n_trades", 0) >= 30:
                _hist = _kelly_hist_stats
                print(
                    "  KellyLearner 在线 hist_stats 已启用 ({} trades)".format(
                        _kelly_hist_stats.get("n_trades", 0)
                    )
                )
            else:
                _hist = calibrate_from_backtest()
                print("  KellyLearner 样本不足，使用回测静态校准")
            # 加载日K波动率（需有 kline_all.parquet）
            _kdf = None
            try:
                import pandas as pd

                _kp = ROOT / "data/kline_cache/kline_all.parquet"
                if _kp.exists():
                    _kdf = pd.read_parquet(_kp, columns=["symbol", "date", "close"])
            except Exception:
                pass
            top = apply_kelly(top, equity, _kdf, _hist)
            # 从 apply_kelly 回写 entry_score_pct / entry_vol
            for r in top:
                if "entry_score_pct" not in r:
                    r["entry_score_pct"] = r.get("_pct") or 0.5
                if "entry_vol" not in r:
                    r["entry_vol"] = r.get("_vol") or 0.3
            print(f"  Kelly 仓位分配已启用, {len(top)} 只, 数据源=KellyLearner" if _ml_ready else f"  Kelly 仓位分配已启用, {len(top)} 只, 数据源=静态回测")
            for i, r in enumerate(top):
                print(
                    "    #{} {} entry_weight={:.0%} kelly_frac={:.1%} vol={}".format(
                        i + 1,
                        r.get("symbol"),
                        float(r.get("entry_weight") or 0),
                        float(r.get("kelly_frac") or 0),
                        r.get("_vol", "?"),
                    )
                )
        else:
            # 等权（默认）
            w = 1.0 / max(len(top), 1)
            for r in top:
                r["entry_weight"] = round(w, 4)
                r["kelly_enabled"] = False
    except ImportError:
        w = 1.0 / max(len(top), 1)
        for r in top:
            r["entry_weight"] = round(w, 4)
    except Exception as e:
        print(f"  Kelly 分配异常 (fallback 等权): {e}")
        w = 1.0 / max(len(top), 1)
        for r in top:
            r["entry_weight"] = round(w, 4)

    # 同步读 recommend 元数据
    env_flags = {}
    pool_n = 10
    try:
        d = json.loads(REC_PATH.read_text(encoding="utf-8"))
        env_flags = d.get("market_env_flags") or {}
        pool_n = int(d.get("recommend_pool_n") or 10)
        if picks.get("position_exposure") is None:
            expo = float(d.get("position_exposure") or 0)
    except Exception:
        pass

    print("=" * 70)
    print(
        "模型 Top{} | {} | mode={}".format(
            top_n, datetime.now().strftime("%Y-%m-%d %H:%M"), picks.get("mode")
        )
    )
    print("position_exposure={:.2f} | pool_n={} | asof={}".format(expo, pool_n, picks.get("asof")))
    if env_flags:
        print("market_env: {}".format(env_flags))
    print("=" * 70)
    print("{:<4} {:<10} {:<8} {:<14} {:<12}".format("排名", "股票", "评分", "主力净额", "阶段"))
    print("-" * 70)
    for i, r in enumerate(top):
        main_net = int(r.get("live_main_net") or r.get("main_net") or 0)
        net_s = "+{}万".format(main_net // 10000) if main_net > 0 else "{}万".format(main_net // 10000)
        print(
            "  #{} {} {:.4f}  {:<14} {}".format(
                i + 1,
                r.get("symbol"),
                float(r.get("score", 0) or 0),
                net_s,
                r.get("money_phase_label", r.get("money_phase", "")),
            )
        )

    pt = json.loads(PT_PATH.read_text(encoding="utf-8")) if PT_PATH.exists() else {}
    pt["position_exposure"] = expo
    pt["recommend_top_n"] = top_n
    pt["recommend_pool_n"] = pool_n
    pt["market_env_flags"] = env_flags
    pt["morning_live_mode"] = picks.get("mode")
    pt["morning_live_asof"] = picks.get("asof")
    pt["protocol"] = {
        "name": picks.get("mode") or "morning_live_model_top2",
        "entry": (
            "gap_soft: <=1.5% open w=1; 1.5-3% limit prev*1.01 w=0.7; "
            "3-5% limit prev*1.02 w=linear 0.5→0; >=5%/limit-up skip; "
            "09:35 money gate → model score Top2"
        ),
        "entry_mode": "gap_soft",
        "sizing": (
            "默认等权（KELLY_ENABLE=0）；"
            "KELLY_ENABLE=1 时 Half-Kelly + 波动率调整 + 行业集中度约束"
        ),
        "exit": "Plan C: 分级止损-3%*3min减半/-5%全卖; 止盈+5%减半/+10%全卖; T+1强平14:50",
        "top_n": top_n,
        "pool_n": pool_n,
        "cost_rt": None,  # 动态成本，见 cost_model
        "cost_model": "dynamic",
        "strategy_id": STRAT_ID,
        "rank_by": picks.get("rank_by") or "score",
        "kelly_enabled": os.environ.get("KELLY_ENABLE", "0").strip().lower()
        in ("1", "true", "yes", "on"),
    }
    try:
        from cost_model import estimate_trade_cost

        # 用首只标的估一版展示成本（真实下单时按票重算）
        sample_sym = (top[0].get("symbol") if top else "600519") or "600519"
        pt["protocol"]["cost_estimate"] = estimate_trade_cost(sample_sym, 100000)
        pt["protocol"]["cost_rt"] = pt["protocol"]["cost_estimate"]["total"]
    except Exception:
        pt["protocol"]["cost_rt"] = 0.0015

    # ── 方案 C 出场策略（2026-08-03 对齐跟踪止盈，与 trade_executor/qmt_model_plan_c 一致）──
    pt["exit_policy"] = {
        "mode": "plan_C_trailing_tp",
        "ladder_stop": "[[-0.03, 0.5]] consecutive 3min → sell half",
        "stop_hard": "-0.05 → full clear",
        "open_protection": "-0.07 during 09:35-09:45",
        "limit_down": "-0.095 → immediate full clear",
        "ladder_tp": "trailing TP: arm at +0.03 (record peak, do not sell); peel half on 1.5% pullback from peak (max 2 halves, 3rd → full clear); new high required after each half before next cut",
        "book_a8a4_boost": "if yesterday high-position volume+RSI>=80 (A8) or high-position big bear >6% (A4) → sell half immediately when trailing armed (skip pullback wait)",
        "trail_arm": 0.03,
        "peel_pullback": 0.015,
        "hard_stop_pct": -0.05,
        "t1_force": "held>=1 day at 14:50; limit-up (bid1/vol>3x) extends to next 09:35",
        "c_atr_adaptive": False,
        "check_intraday": True,
    }

    strat = ensure_daily_strategy(pt)
    strat["signals"] = []

    # 人工确认闸门：默认开启。出票写入 pending_review，不自动发买入信号。
    require_approval = os.environ.get("REQUIRE_ORDER_APPROVAL", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )
    created_tickets = []
    try:
        from order_tickets import create_tickets_from_picks, list_tickets, sync_approved_to_paper_signals

        created_tickets = create_tickets_from_picks(
            top,
            user_id="owner",
            source=picks.get("mode") or "morning_live",
            asof=picks.get("asof"),
            position_exposure=expo,
        )
        pending = list_tickets(user_id="owner", status="pending_review", today_only=True)
        print(
            f"\n人工确认闸门: created={len(created_tickets)} pending_today={len(pending)} "
            f"require_approval={require_approval}"
        )
        pt["approval_gate"] = {
            "enabled": require_approval,
            "pending_n": len(pending),
            "created_n": len(created_tickets),
            "asof": picks.get("asof"),
            "note": "确认后才会写入买入信号并进入执行器",
        }
    except Exception as e:
        print(f"order_tickets 写入失败: {e}")
        require_approval = False

    if expo <= 0 or top_n <= 0 or picks.get("empty_reason") == "position_exposure_zero":
        print("\n⚠️ position_exposure=0 → 今日不发买入信号（nuclear 空仓）")
        pt["empty_reason"] = "position_exposure_zero"
    elif not top:
        print("\n⚠️ 盘中资金重排后无候选")
        pt["empty_reason"] = picks.get("empty_reason") or "no_morning_picks"
    elif require_approval:
        pt["empty_reason"] = "awaiting_human_approval"
        print(
            "\n⏸️ 等待人工过目确认（网页「今日待确认」）。"
            "确认前不自动买入。可用 API /api/v1/cn/live-orders/approve"
        )
        # 若已有今日已确认未成交，仍同步 signals
        try:
            from order_tickets import sync_approved_to_paper_signals

            synced = sync_approved_to_paper_signals(user_id="owner", pt_path=PT_PATH)
            if synced:
                print(f"  已同步 {len(synced)} 条已确认买单到 signals")
                # reload strat signals
                for s in pt.get("strategies") or []:
                    if s.get("id") == STRAT_ID:
                        strat = s
                        break
        except Exception as e:
            print(f"  sync approved skip: {e}")
    else:
        pt["empty_reason"] = None
        held = {p.get("symbol") for p in strat.get("positions", [])}
        # ── 为 Kelly 增强特征预载 kline + 趋势 ──
        _kelly_kdf = None
        _kelly_trend_cache: dict[str, dict] = {}
        try:
            from trend_prefer_boost import _load_kline, calc_trend_flags, _bare as _tb
            _kelly_kdf = _load_kline()
        except Exception:
            pass
        for r in top:
            sym = r.get("symbol") or ""
            if not sym or sym in held:
                continue
            buy_price = float(r.get("buy_price") or r.get("price") or 0)
            if buy_price <= 0:
                continue
            target = float(r.get("target_price") or 0)
            stop = float(r.get("stop_price") or 0)
            score = float(r.get("score", 0) or 0)
            main_net = int(r.get("live_main_net") or r.get("main_net") or 0)
            phase = r.get("money_phase", "sideways")
            # ── 计算增强特征 ──
            # gap_pct: 用推荐价 vs kline 昨收估算
            entry_gap_pct = 0.0
            if _kelly_kdf is not None:
                try:
                    code = _tb(sym)
                    g = _kelly_kdf[_kelly_kdf["symbol"] == code]
                    if not g.empty:
                        prev_close = float(g["close"].iloc[-1])
                        if prev_close > 0:
                            entry_gap_pct = (buy_price - prev_close) / prev_close
                except Exception:
                    pass
            # money_phase: 从 label 映射到 phase code
            phase_label = str(r.get("money_phase_label", "")).strip().lower()
            if not phase_label:
                entry_money_phase = phase
            else:
                # label → phase 逆向映射
                _rev_map = {
                    "诱空陷阱": "bear_trap", "诱空": "bear_trap",
                    "吸筹": "accumulation", "吸筹末期": "accumulation_end",
                    "震荡": "sideways", "震荡洗盘": "sideways",
                    "右侧潜伏": "rightside_ambush", "右侧": "rightside_ambush",
                    "拉升": "markup", "主升": "markup", "强拉升": "markup_strong",
                    "回调": "pullback", "回踩": "pullback",
                    "出货": "distribution", "诱多嫌疑": "suspicious",
                    "诱多": "suspicious",
                }
                entry_money_phase = _rev_map.get(phase_label, phase)
            # channel_reject: 利用趋势标志
            entry_channel_reject = int(r.get("channel_reject") or 0)
            if entry_channel_reject == 0 and _kelly_kdf is not None:
                try:
                    code = _tb(sym)
                    g = _kelly_kdf[_kelly_kdf["symbol"] == code]
                    if not g.empty:
                        flags = calc_trend_flags(g)
                        if flags and flags.get("channel_reject", False):
                            entry_channel_reject = 1
                except Exception:
                    pass
            entry_sector_heat = float(r.get("sector_heat") or r.get("theme_heat", 0.5))
            entry_main_net = main_net

            # ── Kelly 胜率反哺：8 维预测 → 置信度加权 ──
            _kelly_wr = 0.5
            _kelly_cv = 1.0
            try:
                _kelly_wr = _kl.predict_win_rate(
                    score_pct=float(r.get("entry_score_pct") or r.get("_pct") or 0.5),
                    vol=float(r.get("entry_vol") or r.get("_vol") or 0.3),
                    expo=int(expo * 100),
                    gap_pct=entry_gap_pct,
                    money_phase=entry_money_phase,
                    channel_reject=entry_channel_reject,
                    sector_heat=entry_sector_heat,
                    main_net=entry_main_net,
                )
                _kelly_cv = min(_kelly_wr / 0.5, 2.0) if _kelly_wr > 0 else 0.5
            except Exception:
                pass
            # 置信度回写到 r，影响 entry_weight
            old_w = float(r.get("entry_weight") or 0.7)
            r["kelly_win_rate"] = round(_kelly_wr, 4)
            r["kelly_conviction"] = round(_kelly_cv, 4)
            r["entry_weight"] = round(min(old_w * _kelly_cv, 0.95), 4)
            reason = "model Top{} VM2.5={:.4f} {} 主力净{:+d}万 expo={:.0%}".format(
                r.get("morning_pick_rank") or "",
                score,
                r.get("money_phase_label", phase),
                main_net // 10000,
                expo,
            )
            strat["signals"].append(
                {
                    "symbol": sym,
                    "name": r.get("name", ""),
                    "score": score,
                    "money_phase": phase,
                    "action": "buy",
                    "price": buy_price,
                    "target_price": target if target > buy_price else round(buy_price * 1.10, 2),
                    "stop_price": stop if 0 < stop < buy_price else round(buy_price * 0.95, 2),
                    "quantity": 0,
                    "strategy_id": STRAT_ID,
                    "position_exposure": expo,
                    "protocol": picks.get("mode") or "morning_live_model_top2",
                    "main_net": main_net,
                    "reason": reason,
                    "entry_mode": "wait_dyn_confirm",
                    "morning_pick_rank": r.get("morning_pick_rank"),
                    "entry_score_pct": r.get("entry_score_pct") or r.get("_pct") or 0.5,
                    "entry_vol": r.get("entry_vol") or r.get("_vol") or 0.3,
                    "entry_gap_pct": entry_gap_pct,
                    "entry_money_phase": entry_money_phase,
                    "entry_channel_reject": entry_channel_reject,
                    "entry_sector_heat": entry_sector_heat,
                    "entry_main_net": entry_main_net,
                    "kelly_win_rate": r.get("kelly_win_rate", 0.5),
                    "kelly_conviction": r.get("kelly_conviction", 1.0),
                }
            )

    # ── Kelly 反哺摘要 ──
    try:
        _conv_list = [s.get("kelly_conviction", 1.0) for s in (strat.get("signals") or []) if s.get("kelly_conviction")]
        if _conv_list:
            avg_conv = sum(_conv_list) / len(_conv_list)
            print(
                "  Kelly 胜率反哺: {} 只, 平均置信度={:.2f}, entry_weight已调整".format(
                    len(_conv_list), avg_conv
                )
            )
    except Exception as exc:
        print(f"  Kelly 反哺摘要异常 (skip): {exc}")

    pt["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    PT_PATH.write_text(json.dumps(pt, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        "\n✅ Paper 信号已更新 | 买入信号 {} 条 | expo={:.2f} | mode={} | approval={}".format(
            len(strat.get("signals") or []),
            expo,
            picks.get("mode"),
            "ON" if require_approval else "OFF",
        )
    )
    pos = strat.get("positions", [])
    if pos:
        print("\n当前持仓:")
        for p in pos:
            print(
                "  {} {} x{}  cost={} cur={} pnl={:+.2f}% days={}".format(
                    p.get("symbol"),
                    p.get("name", ""),
                    p.get("quantity", 0),
                    p.get("buy_price", 0),
                    p.get("current_price", 0),
                    float(p.get("pnl_pct", 0) or 0),
                    p.get("trading_days_held", p.get("days_held", 0)),
                )
            )


if __name__ == "__main__":
    main()
