"""v2 策略并行系统: paper_trading_signals_v2.py
- 与原 v19_daily 完全独立: 独立策略ID v19_daily_v2、独立信号、独立资金池
- 叠加升级1(波动率门控) + 升级4(情绪周期门控)
- 原系统 paper_trading_signals.py 保持不动
- 输出: morning_live_picks_v2.json -> 写入 paper_trading.json 的 v19_daily_v2 策略
"""
import json, os, sys
from datetime import datetime
from pathlib import Path

ROOT = Path("/home/ubuntu/alphapilot")
os.chdir(ROOT)

PT_PATH = ROOT / "data" / "paper_trading.json"
PICKS_V2_PATH = ROOT / "output" / "morning_live_picks_v2.json"
STRAT_ID_V2 = "v19_daily_v2"
DEFAULT_TOP_N = 2

# 升级开关
VOL_GATE_ON = os.environ.get("V2_VOL_GATE", "1") == "1"
SENTIMENT_GATE_ON = os.environ.get("V2_SENTIMENT_GATE", "1") == "1"
VOL_GATE_MAX = float(os.environ.get("V2_VOL_GATE_MAX", "3.5"))
IVU_GATE_ON = os.environ.get("V2_IVU_GATE", "1") == "1"
OPEN_GAP_ON = os.environ.get("V2_OPEN_GAP", "1") == "1"
OPEN_GAP_MAX = 1.0


def log(msg):
    print(f"[v2] {msg}", flush=True)


def load_source_picks():
    """读取 daily_recommend(36只) 作为候选源 (比 morning_live_picks 的Top2大得多,
    让多因子打分有过滤空间)"""
    src = ROOT / "output" / "daily_recommend.json"
    if not src.exists():
        log("源推荐不存在: daily_recommend.json")
        return None
    d = json.loads(src.read_text(encoding="utf-8"))
    recs = d.get("recommendations", []) or []
    # 取前 36 只候选 (按 score 降序)
    recs = sorted(recs, key=lambda r: -float(r.get("score", 0) or 0))[:36]
    return {"picks": recs, "mode": "v2_multifactor_pool"}


def sentiment_gate():
    """升级4: 情绪周期门控. 返回 (allowed, stage)"""
    if not SENTIMENT_GATE_ON:
        return True, "off"
    try:
        sys.path.insert(0, str(ROOT))
        import market_sentiment
        r = market_sentiment.main()
        return r["trade_allowed"], r["stage"]
    except Exception as e:
        log(f"情绪门控异常(放行): {e}")
        return True, "error"


def vol_gate_filter(picks):
    """升级1: 波动率门控过滤"""
    if not VOL_GATE_ON or not picks:
        return picks, 0
    try:
        sys.path.insert(0, str(ROOT))
        from vol_gate import get_vol20
        kept, blocked = [], []
        for r in picks:
            sym = str(r.get("symbol", "")).zfill(6)
            vol = get_vol20(sym)
            if vol is None or vol <= VOL_GATE_MAX:
                kept.append(r)
            else:
                blocked.append((sym, vol))
        if blocked:
            log(f"vol_gate 拦截 {len(blocked)} 只高波动: " +
                ", ".join(f"{s}({v:.1f}%)" for s, v in blocked[:6]))
        return kept, len(blocked)
    except Exception as e:
        log(f"vol_gate 异常(放行): {e}")
        return picks, 0


def hard_filter_picks(picks):
    """三类事实性硬删除: ST / 亏损股 / 利空 (唯一允许一票否决)"""
    try:
        from hard_filter import hard_filter as hf
        items = [(str(r.get("symbol", "")).zfill(6), r.get("name", "")) for r in picks]
        keep_items, detail = hf(items)
        kept = [p for p in picks if (str(p.get("symbol", "")).zfill(6), p.get("name", "")) in
                set((s, n) for s, n in keep_items)]
        blocked = len(picks) - len(kept)
        if blocked:
            log(f"hard_filter 硬删除 {blocked} 只: ST={len(detail['st'])} 亏损={len(detail['loss'])} 利空={len(detail['news'])}")
        return kept
    except Exception as e:
        log(f"hard_filter 异常(放行): {e}")
        return picks


def score_open_gap(picks):
    """多因子打分 (替代原 open_gap 硬门控)
    基于184万样本验证: 低开+涨停史+大额成交 → 高分; 高开5%+无支撑 → 低分
    软权重叠加到原 score, 不硬拦截
    """
    if not OPEN_GAP_ON or not picks:
        return picks
    try:
        from multifactor_score import batch_score
        return batch_score(picks)
    except Exception as e:
        log(f"multifactor 打分异常(原样返回): {e}")
        return picks


def get_v2_strategy(pt):
    """获取/创建 v19_daily_v2 策略"""
    for s in pt.get("strategies", []):
        if s.get("id") == STRAT_ID_V2:
            return s
    strat = {
        "id": STRAT_ID_V2, "name": "日频精选V2(升级版)",
        "status": "active", "allocated": 500000.0, "used": 0.0,
        "signals": [], "positions": [],
        "meta": {"upgrades": ["hard_filter", "vol_gate", "multifactor_score+q1_filter", "sentiment_gate"], "version": "v2.4",
                 "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")},
    }
    pt.setdefault("strategies", []).append(strat)
    return strat


def write_signals(pt, strat, picks, asof):
    """写入买入信号到 v2 策略"""
    signals = []
    for r in picks[:DEFAULT_TOP_N]:
        sym = str(r.get("symbol", "")).zfill(6)
        signals.append({
            "symbol": sym, "name": r.get("name", ""),
            "action": "buy", "price": float(r.get("buy_price") or r.get("price") or 0),
            "score": float(r.get("score", 0) or 0),
            "strategy_id": STRAT_ID_V2,
            "asof": asof, "status": "pending",
            "entry_mode": "low_pending",
            "meta": {"v2": True, "upgrades": ["vol_gate", "sentiment_gate"]},
        })
    strat["signals"] = signals
    return signals


def main():
    now = datetime.now()
    asof = now.strftime("%Y-%m-%d %H:%M")

    # 1. 情绪门控
    sent_allowed, stage = sentiment_gate()
    log(f"情绪阶段: {stage} | 开仓许可: {sent_allowed}")
    if not sent_allowed:
        log(f"情绪门控拦截: 阶段={stage}, 今日不开新仓 (保留原系统运行)")
        # 仍写入空信号 + 记录原因
        pt = json.loads(PT_PATH.read_text(encoding="utf-8"))
        strat = get_v2_strategy(pt)
        strat["signals"] = []
        strat["meta"]["last_gate"] = {"stage": stage, "allowed": False,
                                       "reason": "sentiment gate", "at": asof}
        PT_PATH.write_text(json.dumps(pt, ensure_ascii=False, indent=2), encoding="utf-8")
        PICKS_V2_PATH.write_text(json.dumps(
            {"asof": asof, "stage": stage, "trade_allowed": False,
             "picks": [], "reason": "sentiment gate blocked"}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        return

    # 2. 加载候选
    src = load_source_picks()
    if not src:
        return
    picks = src.get("picks", [])

    # 3. 波动率门控
    picks, n_blocked = vol_gate_filter(picks)
    log(f"vol_gate 后候选: {len(picks)} 只 (拦截 {n_blocked})")

    # 硬删除: ST / 亏损 / 利空 (事实性负面, 唯一一票否决)
    picks = hard_filter_picks(picks)
    log(f"hard_filter 后候选: {len(picks)} 只")

    # 升级2: 多因子打分 (低开加分/高开减分/涨停史/成交额)
    picks = score_open_gap(picks)
    log(f"多因子打分完成: {len(picks)} 只")

    # 过滤 Q1 差组: 多因子总分 < 阈值 → 不买 (回测: Q1差组3天达标率仅20%, 期望-4%)
    # 总分 = 原score + 多因子调整; 用调整项(_score_adj)判断质量
    _before_f = len(picks)
    picks = [p for p in picks if float(p.get("_score_adj", 0) or 0) >= -0.05]
    _dropped = _before_f - len(picks)
    if _dropped:
        log(f"Q1差组过滤: 剔除 {_dropped} 只低分股 (3天达标率<25%必亏组)")

    # 按调整后分数排序取 Top2
    picks = sorted(picks, key=lambda p: -float(p.get("score", 0) or 0))[:DEFAULT_TOP_N]
    log(f"最终候选 Top{len(picks)}")

    # 4. 写入 v2 策略信号
    pt = json.loads(PT_PATH.read_text(encoding="utf-8"))
    strat = get_v2_strategy(pt)
    signals = write_signals(pt, strat, picks, asof)
    strat["meta"]["last_gate"] = {"stage": stage, "allowed": True,
                                   "n_picks": len(picks), "at": asof}
    PT_PATH.write_text(json.dumps(pt, ensure_ascii=False, indent=2), encoding="utf-8")
    PICKS_V2_PATH.write_text(json.dumps(
        {"asof": asof, "stage": stage, "trade_allowed": True,
         "picks": picks[:DEFAULT_TOP_N], "n_blocked": n_blocked},
        ensure_ascii=False, indent=2), encoding="utf-8")

    log(f"✅ v2 信号已写入: {len(signals)} 条 -> {STRAT_ID_V2}")
    for s in signals:
        log(f"  {s['symbol']} {s['name']} score={s['score']:.4f}")


if __name__ == "__main__":
    main()
