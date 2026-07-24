"""Paper Trading 信号更新 — 09:36 消费盘中选股结果

协议：
1. 优先读 output/morning_live_picks.json（09:35 资金门 + 模型分 Top2）
2. 若今日尚无 picks，则对 daily_recommend 池现场跑一遍 morning 逻辑
3. expo<=0 → 不买；否则买入模型分前 N 只
4. 仓位分配：KELLY_ENABLE=1 时用 Kelly + 风险预算；否则等权
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "/home/ubuntu/alphapilot")

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
    asof = str(picks.get("asof") or "")
    today = datetime.now().strftime("%Y-%m-%d")
    return asof.startswith(today) and picks.get("mode") in VALID_PICK_MODES


def _ensure_morning_picks() -> dict:
    if PICKS_PATH.exists():
        try:
            picks = json.loads(PICKS_PATH.read_text(encoding="utf-8"))
            if _picks_fresh(picks):
                return picks
        except Exception:
            pass
    # 现场补跑 09:35 逻辑
    print("⚠️ morning_live_picks 非今日或缺失 → 现场重跑 morning_live_fund_select")
    try:
        import morning_live_fund_select as mls

        mls.main()
        return json.loads(PICKS_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"morning select failed: {e}")
        # 回退：用 recommend 池按模型分取 Top2
        d = json.loads(REC_PATH.read_text(encoding="utf-8"))
        expo = float(d.get("position_exposure") or 0)
        items = list(d.get("recommendations") or [])
        items.sort(
            key=lambda x: float(x.get("score") or x.get("ml_score") or 0),
            reverse=True,
        )
        top = items[:DEFAULT_TOP_N] if expo > 0 else []
        return {
            "asof": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "position_exposure": expo,
            "trade_top_n": len(top),
            "picks": top,
            "mode": "morning_live_model_top2",
            "rank_by": "score",
            "empty_reason": None if top else "fallback_empty",
        }


def main():
    picks = _ensure_morning_picks()
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
    top = top[:top_n]

    # 排除列表过滤（不交易、不计入统计）
    _excluded = _load_exclude_symbols()
    if _excluded:
        _before = len(top)
        top = [r for r in top if str(r.get("symbol", "")).zfill(6) not in _excluded]
        if len(top) < _before:
            print("  [排除] 过滤掉 {} 只黑名单股票, 剩余 {} 只备选".format(_before - len(top), len(top)))
            # 池子不够时从 recommend 补位
            if len(top) < max(top_n, 1) and _excluded:
                try:
                    d = json.loads(REC_PATH.read_text(encoding="utf-8"))
                    all_items = list(d.get("recommendations") or [])
                    held_syms = {str(r.get("symbol", "")).zfill(6) for r in top}
                    for r in all_items:
                        sym = str(r.get("symbol", "")).zfill(6)
                        if sym not in held_syms and sym not in _excluded:
                            top.append(r)
                            if len(top) >= top_n:
                                break
                except Exception:
                    pass
            top = top[:top_n]

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
        "exit": "E2 hard-stop -10% close-confirm; peel if float>0; T+2 force with 1d fund-extend",
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
                    "target_price": target if target > buy_price else round(buy_price * 1.08, 2),
                    "stop_price": stop if 0 < stop < buy_price else round(buy_price * 0.94, 2),
                    "quantity": 0,
                    "strategy_id": STRAT_ID,
                    "position_exposure": expo,
                    "protocol": picks.get("mode") or "morning_live_model_top2",
                    "main_net": main_net,
                    "reason": reason,
                }
            )

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
