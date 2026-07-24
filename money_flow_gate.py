"""
AlphaPilot V16+ 实时资金门控 + 多日趋势过滤 + 基本面过滤

V16+ 新特性：
- 新增「诱空陷阱 🪤」分类：价格下跌但主力暗中吸筹的洗盘信号
- 新增「右侧潜伏 🎯」分类：吸筹完成、刚启动、即将拉升的起爆点
- 已有：吸筹末期 🔔、拉升 🚀、诱多嫌疑 ⚠️、出货 ⚠️、回调 📉
"""
import json
import math
import os
from pathlib import Path

from enriched_data import get_quotes_batch, get_mootdx_finance_fundamentals
from config import OUTPUT_DIR


def _pe_ttm_hard_enabled() -> bool:
    """PE 硬阀总开关。默认关闭——估值交给客户前端筛选，不再系统硬淘。

    若需恢复旧行为：ENABLE_PE_TTM_HARD=1 且 PE_TTM_MAX=30。
    """
    v = os.environ.get("ENABLE_PE_TTM_HARD", "0").strip().lower()
    return v in ("1", "true", "yes", "on")


def _max_pe_ttm_default() -> float | None:
    """估值硬阀上限（仅当 ENABLE_PE_TTM_HARD 开启时生效）。

      ENABLE_PE_TTM_HARD=0   默认：不硬淘（客户自选 PE≤30 / PE>30）
      ENABLE_PE_TTM_HARD=1 + PE_TTM_MAX=30  恢复系统硬阀
      PE_TTM_MAX=0 或 -1     即使总开关开也关闭硬阀
    """
    if not _pe_ttm_hard_enabled():
        return None
    try:
        v = float(os.environ.get("PE_TTM_MAX", "30") or 30)
    except (TypeError, ValueError):
        return 30.0
    if v <= 0:
        return None
    return v


def classify_pe_bucket(pe_ttm) -> str:
    """客户筛选用：le_30 / gt_30 / na（缺失或≤0）。"""
    if pe_ttm is None:
        return "na"
    try:
        p = float(pe_ttm)
    except (TypeError, ValueError):
        return "na"
    if p <= 0:
        return "na"
    if p <= 30.0:
        return "le_30"
    return "gt_30"


def apply_money_flow_gate(
    recs: list,
    min_active_buy: float = 0.52,
    min_turnover: float = 2.0,
    max_turnover: float = 35.0,
    min_vol_ratio: float = 0.8,
    max_drop_pct: float = -5.0,
    top_n: int = None,
    check_fundamentals: bool = True,
    hard_main_net_5d: bool = True,
    max_pe_ttm: float | None = None,
) -> list:
    """对推荐列表施加资金门控 + 多日趋势过滤 + 加权

    估值：默认不硬淘（ENABLE_PE_TTM_HARD=0）。始终写入 pe_ttm / pe_bucket
    供前端「PE≤30 / PE>30」客户自选。仅当硬阀开启时才按 max_pe_ttm 出局。
    """
    if not recs:
        return recs
    if max_pe_ttm is None:
        max_pe_ttm = _max_pe_ttm_default()
    pe_gate_on = max_pe_ttm is not None and float(max_pe_ttm) > 0
    if not pe_gate_on:
        print("  money_flow_gate pe_ttm hard: OFF (客户自选 PE≤30/PE>30)", flush=True)
    syms = [r.get("symbol") for r in recs if r.get("symbol")]

    # 1. 实时资金流
    try:
        quotes = get_quotes_batch(syms)
    except Exception:
        quotes = {}

    # 1.5 资金流历史（多日累计检查）
    fund_hist = {}
    _fhp = "data/fund_flow_history.json"
    if os.path.exists(_fhp):
        try:
            fund_hist = json.load(open(_fhp))
        except Exception:
            pass

    # 1.6 Wind 候选覆盖（当日/近5日主力净流入 + PE）— B′ 替换层
    wind_flow = {}
    _wfp = "data/wind_candidate_flow.json"
    if os.path.exists(_wfp):
        try:
            _wraw = json.load(open(_wfp, encoding="utf-8"))
            wind_flow = _wraw.get("items") or {}
            if wind_flow:
                print(
                    f"  money_flow_gate wind overlay: n={len(wind_flow)} asof={_wraw.get('asof')}",
                    flush=True,
                )
        except Exception:
            wind_flow = {}

    # 2. 基本面
    fundamentals = {}
    if check_fundamentals:
        try:
            from enriched_data import batch_mootdx_finance
            funds = batch_mootdx_finance(syms)
            for s, f in funds.items():
                fundamentals[s] = f
        except Exception:
            pass

    out = []
    for r in recs:
        sym = r.get("symbol")
        q = quotes.get(sym)
        feats = r.get("features", {})

        # ── 资金信号（今日） ──
        pe_ttm = None
        if q:
            abr = q.get("active_buy_ratio", 0.5)
            to = q.get("turnover", 0.0) or 0.0
            vr = q.get("volume_ratio", 1.0) or 1.0
            r["active_buy_ratio"] = round(abr, 4)
            r["turnover"] = round(to, 2)
            r["volume_ratio"] = round(vr, 2)
            circ = q.get("circ_mv")
            if circ is None:
                circ = q.get("total_mv")
            if circ is not None:
                try:
                    r["circ_mv"] = round(float(circ), 2)
                except (TypeError, ValueError):
                    pass
            money_pass = (abr >= min_active_buy) and (min_turnover <= to <= max_turnover) and (vr >= min_vol_ratio)
            chg = q.get("change_pct", 0) or 0
            r["change_pct"] = round(chg, 2)
            if chg < max_drop_pct:
                money_pass = False
                r["drop_reason"] = f"当日跌幅 {round(chg,1)}% 超过阈值"
            raw_pe = q.get("pe_ttm", q.get("pe"))
            if raw_pe is not None:
                try:
                    pe_ttm = float(raw_pe)
                except (TypeError, ValueError):
                    pe_ttm = None
            # Wind PE 优先（腾讯亏损股常空）
            _wc0 = (sym or "")[-6:]
            _w0 = wind_flow.get(_wc0) if isinstance(wind_flow, dict) else None
            if isinstance(_w0, dict) and _w0.get("pe_ttm") is not None:
                try:
                    pe_ttm = float(_w0["pe_ttm"])
                    r["pe_source"] = "wind"
                except (TypeError, ValueError):
                    pass
        else:
            money_pass = None
            abr = float(r.get("active_buy_ratio") or 0.5)
            to = float(r.get("turnover") or 0.0)
            vr = float(r.get("volume_ratio") or 1.0)
            chg = float(r.get("change_pct") or 0)
            raw_pe = r.get("pe_ttm", r.get("pe"))
            if raw_pe is not None:
                try:
                    pe_ttm = float(raw_pe)
                except (TypeError, ValueError):
                    pe_ttm = None

        if pe_ttm is not None:
            r["pe_ttm"] = round(pe_ttm, 2)
            r["pe"] = r["pe_ttm"]
        r["pe_bucket"] = classify_pe_bucket(pe_ttm)

        # ── 多日趋势信号 ──
        ret_5d = feats.get("ret_5d", 0) or 0
        ret_3d = feats.get("ret_3d", 0) or 0
        vol_shrink = feats.get("vol_shrink_days", 0) or 0
        consecutive = feats.get("consecutive_up", 0) or 0
        atr_trend = feats.get("atr_trend", 1.0) or 1.0
        price_vs_low = feats.get("price_vs_5d_low", 1.05) or 1.05
        ma_dir = feats.get("ma_direction", 1.0) or 1.0

        # 过热过滤
        overheat_penalty = 0
        if ret_5d > 0.30:
            overheat_penalty = -0.3
            r["overheat_warning"] = f"5日涨幅 {ret_5d*100:.1f}%（短期过热）"
        elif ret_5d > 0.20:
            overheat_penalty = -0.1
            r["overheat_warning"] = f"5日涨幅 {ret_5d*100:.1f}%（偏高）"

        # 缩量蓄力加分
        accumulation_bonus = 0
        if vol_shrink >= 3 and atr_trend < 0.9 and price_vs_low < 1.05:
            accumulation_bonus = 0.15
            r["accumulation_signal"] = "缩量蓄力"
        elif vol_shrink >= 2:
            accumulation_bonus = 0.05

        # 新低警告
        if price_vs_low < 1.01 and chg < 0:
            r["new_low_warning"] = "接近5日新低"

        # ── V16+ 资金阶段判断（含诱空陷阱+右侧潜伏）──
        phase_key, phase_label, phase_emoji = classify_money_phase_v16(
            abr, chg, vr, to, ret_5d, vol_shrink, atr_trend, price_vs_low
        )
        r["money_phase"] = phase_key
        r["money_phase_label"] = f"{phase_emoji} {phase_label}"

        # ── 多日资金：3日锋面 + 5日骨架（+10日参考）──
        sym_code = (sym or "")[-6:]
        r["main_net_3d"] = 0.0
        r["main_net_5d"] = 0.0
        r["main_net_10d"] = 0.0
        r["fund_pos_days_5"] = 0
        fund_soft_bonus = 0.0
        # Wind 当日净流入优先写入
        _witem = wind_flow.get(sym_code) if isinstance(wind_flow, dict) else None
        if isinstance(_witem, dict):
            if _witem.get("main_net_today") is not None:
                try:
                    r["main_net"] = float(_witem["main_net_today"])
                    r["main_net_source"] = "wind"
                except (TypeError, ValueError):
                    pass
            if _witem.get("main_net_5d") is not None:
                try:
                    r["main_net_5d"] = float(_witem["main_net_5d"])
                    r["main_net_5d_source"] = "wind"
                except (TypeError, ValueError):
                    pass
            for _wk, _rk in (
                ("inst_net", "wind_inst_net"),
                ("large_net", "wind_large_net"),
                ("mid_net", "wind_mid_net"),
                ("retail_net", "wind_retail_net"),
            ):
                if _witem.get(_wk) is not None:
                    try:
                        r[_rk] = float(_witem[_wk])
                    except (TypeError, ValueError):
                        pass
            if pe_ttm is None and _witem.get("pe_ttm") is not None:
                try:
                    pe_ttm = float(_witem["pe_ttm"])
                    r["pe_source"] = "wind"
                except (TypeError, ValueError):
                    pass
            # 盘中精度软分：机构净流入加分，散户单边流入略扣（仅标注 bonus，后面并入 fund_soft）
            try:
                inst = float(_witem.get("inst_net") or 0)
                retail = float(_witem.get("retail_net") or 0)
                main = float(_witem.get("main_net_today") or 0)
                if inst > 0 and main > 0:
                    fund_soft_bonus += 0.02
                    r["wind_tier_bias"] = "inst_in"
                elif retail > 0 and main < 0 and inst <= 0:
                    fund_soft_bonus -= 0.02
                    r["wind_tier_bias"] = "retail_chase"
            except (TypeError, ValueError):
                pass
        if sym_code in fund_hist:
            _hist = fund_hist[sym_code]
            _dates = sorted(_hist.keys(), reverse=True)
            _nets3 = [float(_hist[d]) for d in _dates[:3] if d in _hist]
            _nets5 = [float(_hist[d]) for d in _dates[:5] if d in _hist]
            _nets10 = [float(_hist[d]) for d in _dates[:10] if d in _hist]
            if len(_nets3) >= 2:
                r["main_net_3d"] = round(sum(_nets3), 2)
            if len(_nets5) >= 3:
                # 若已有 Wind 近5日合计，保留 Wind；否则用历史求和
                if r.get("main_net_5d_source") != "wind":
                    r["main_net_5d"] = round(sum(_nets5), 2)
                r["fund_pos_days_5"] = sum(1 for x in _nets5 if x > 0)
            if len(_nets10) >= 5:
                r["main_net_10d"] = round(sum(_nets10), 2)
            _today_net = float(r.get("main_net", 0) or 0)
            if _today_net > 0 and r["main_net_5d"] < 0:
                r["money_warning"] = "当日流入但5日累计净流出"
            elif _today_net > 0 and r["main_net_10d"] < 0:
                r["money_warning"] = "当日流入但10日累计净流出"

            # 软加分：3日锋面 + 5日骨架 + 正流入天数
            s3 = float(r["main_net_3d"] or 0)
            s5 = float(r["main_net_5d"] or 0)
            pos5 = int(r["fund_pos_days_5"] or 0)
            fund_soft_bonus = (
                math.tanh(s3 / 5e7) * 0.04
                + math.tanh(s5 / 1e8) * 0.06
                + min(pos5, 5) * 0.01
            )
            if s3 > 0 and s5 > 0:
                fund_soft_bonus += 0.02  # 锋面+骨架同向
            fund_soft_bonus = round(max(-0.05, min(0.15, fund_soft_bonus)), 4)
            r["fund_soft_bonus"] = fund_soft_bonus

        # 弱硬底线：仅「3日与5日均为负、且近5日零流入日」才硬淘汰（无参与）
        # 深额流出（5日 < -1亿）也硬淘。其余交给软加分排序。
        r["fund_hard_fail"] = False
        if hard_main_net_5d and sym_code in fund_hist and len(
            [d for d in sorted(fund_hist[sym_code].keys(), reverse=True)[:5] if d in fund_hist[sym_code]]
        ) >= 3:
            s3 = float(r.get("main_net_3d", 0) or 0)
            s5 = float(r.get("main_net_5d", 0) or 0)
            pos5 = int(r.get("fund_pos_days_5", 0) or 0)
            dead = s3 <= 0 and s5 <= 0 and pos5 == 0
            deep_out = s5 < -1e8
            if dead or deep_out:
                r["fund_hard_fail"] = True
                why = "deep_outflow_5d" if deep_out else "no_participation_3d5d"
                r["money_warning"] = ((r.get("money_warning") or "") + f"|hard:{why}").lstrip("|")
            r["fund_gate_mode"] = "weak_hard_plus_soft"

        # ── 基本面 ──
        fin = fundamentals.get(sym)
        if fin:
            r["net_profit"] = float(fin.get("net_profit", 0))
            r["eps"] = float(fin.get("eps", 0))
            r["roe"] = round(float(fin.get("roe", 0)) * 100, 2)
            r["revenue"] = float(fin.get("revenue", 0))
            r["industry_code"] = int(fin.get("industry_code", 0))
            fund_pass = (r["net_profit"] > 0) and (r["eps"] > 0)
        else:
            fund_pass = None

        # ── 估值：默认只打标；硬阀开启时才出局 ──
        r["pe_hard_fail"] = False
        r["pe_gate_pass"] = None
        r["pe_fail_reason"] = None
        if pe_ttm is not None:
            if pe_ttm > 0 and pe_ttm <= 30:
                r["pe_gate_pass"] = True  # 信息态：落在常见估值带
            elif pe_ttm > 30:
                r["pe_gate_pass"] = False
            # pe<=0 → pe_gate_pass 保持 None（na）
        if pe_ttm is not None and pe_gate_on:
            if pe_ttm <= 0:
                r["pe_hard_fail"] = True
                r["pe_gate_pass"] = False
                r["pe_fail_reason"] = "pe_le_0"
                r["money_warning"] = (
                    (r.get("money_warning") or "") + f"|hard:pe_ttm_nonpositive({pe_ttm:.1f})"
                ).lstrip("|")
                fund_pass = False
            elif pe_ttm > float(max_pe_ttm):
                r["pe_hard_fail"] = True
                r["pe_gate_pass"] = False
                r["pe_fail_reason"] = "pe_gt_max"
                r["money_warning"] = (
                    (r.get("money_warning") or "")
                    + f"|hard:pe_ttm>{max_pe_ttm:g}({pe_ttm:.1f})"
                ).lstrip("|")
                fund_pass = False
            else:
                r["pe_gate_pass"] = True
        r["fundamental_pass"] = fund_pass

        # ── 综合门控 ──
        if money_pass is True and fund_pass is not False:
            overall_pass = True
        elif money_pass is None and fund_pass is True:
            overall_pass = True
        elif money_pass is True and fund_pass is None:
            overall_pass = True
        elif money_pass is None and fund_pass is None:
            overall_pass = None
        else:
            overall_pass = False
        if r.get("pe_hard_fail"):
            overall_pass = False
        r["money_flow_pass"] = overall_pass

        # ── 价量异常 / 骗线识别 ──
        anom = detect_price_volume_anomalies(r)
        anomaly_penalty = float(anom.get("penalty") or 0)

        # ── 最终分数 ──
        base = float(r.get("score", 0) or 0)
        flow_boost = 0.7 + 0.3 * max(0.0, min(1.0, abr))
        r["score_raw"] = round(base, 4)
        r["score"] = round(
            base * flow_boost
            + accumulation_bonus
            + overheat_penalty
            + fund_soft_bonus
            + anomaly_penalty,
            4,
        )
        r["score"] = max(0.01, r["score"])
        out.append(r)

    # ── S2 规则加权层（后门控，不出局只加分）──
    for r in out:
        feats = r.get("features", {})
        chg = r.get("change_pct", 0) or 0
        vr = r.get("volume_ratio", 0) or 0
        # 均线多头：优先用趋势首选写入的 flags / features
        tf = r.get("trend_flags") or {}
        if tf.get("ma_bullish_stack") is not None:
            ma_bullish = bool(tf.get("ma_bullish_stack"))
        else:
            ma_bullish = bool(
                float(feats.get("ma5_gt_ma20") or 0) > 0
                and float(feats.get("ma20_gt_ma60") or 0) > 0
                and float(feats.get("price_above_ma60") or 0) > 0
            )
        s2 = s2_weight_score(
            change_pct=chg,
            volume_ratio=vr,
            turnover=float(r.get("turnover") or 0),
            circ_mv=float(r.get("circ_mv") or r.get("total_mv") or 0),
            ma_bullish=ma_bullish,
            close_strength=feats.get("ret_range", 0.5) or 0.5,
            above_vwap=chg >= 0,  # 简化：涨幅为正即为站上均价
            volatility_20d=feats.get("atr_pct", 0.02) or 0.02,
            chip_penetration=feats.get("chip_penetration", 0) or 0,
        )
        r["s2_bonus"] = s2
        r["s2_score"] = s2  # alias for pipeline apply_s2_weight
        r["s2_applied_in_money_gate"] = True
        r["score"] = round(r.get("score", 0) + s2, 4)
    
    # 弱硬底线 + PE-TTM 估值硬阀出局
    fund_dropped = [r for r in out if r.get("fund_hard_fail")]
    pe_dropped = [r for r in out if r.get("pe_hard_fail")]
    pe_gt = [r for r in pe_dropped if r.get("pe_fail_reason") == "pe_gt_max"]
    pe_le0 = [r for r in pe_dropped if r.get("pe_fail_reason") == "pe_le_0"]
    # 独有：仅因 PE>max 出局（未同时踩资金弱硬底）
    pe_gt_only = [
        r for r in pe_gt if not r.get("fund_hard_fail")
    ]
    out = [r for r in out if not r.get("fund_hard_fail") and not r.get("pe_hard_fail")]
    if fund_dropped:
        print(
            f"  money_flow_gate weak_hard drop {len(fund_dropped)} "
            f"(no_participation or deep_outflow_5d)",
            flush=True,
        )
    if pe_dropped:
        print(
            f"  money_flow_gate pe_ttm hard drop {len(pe_dropped)} "
            f"(pe<=0:{len(pe_le0)} pe>{max_pe_ttm:g}:{len(pe_gt)} "
            f"pe>{max_pe_ttm:g}_only:{len(pe_gt_only)})",
            flush=True,
        )
    # 落盘审计，便于网页/人工查看 PE 阀杀了谁
    try:
        audit = {
            "pe_gate_on": pe_gate_on,
            "max_pe_ttm": max_pe_ttm,
            "n_pe_dropped": len(pe_dropped),
            "n_pe_le_0": len(pe_le0),
            "n_pe_gt_max": len(pe_gt),
            "n_pe_gt_max_only": len(pe_gt_only),
            "pe_gt_max_only": [
                {
                    "symbol": r.get("symbol"),
                    "name": r.get("name"),
                    "pe_ttm": r.get("pe_ttm") or r.get("pe"),
                    "score": r.get("score"),
                    "selection_arm": r.get("selection_arm"),
                    "money_phase_label": r.get("money_phase_label"),
                }
                for r in sorted(
                    pe_gt_only,
                    key=lambda x: -float(x.get("pe_ttm") or x.get("pe") or 0),
                )
            ],
            "pe_le_0": [
                {
                    "symbol": r.get("symbol"),
                    "name": r.get("name"),
                    "pe_ttm": r.get("pe_ttm") or r.get("pe"),
                    "score": r.get("score"),
                }
                for r in pe_le0
            ],
        }
        out_dir = Path(OUTPUT_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "money_gate_pe_audit.json").write_text(
            json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        print(f"  money_flow_gate pe audit skip: {e}", flush=True)
    # 重排
    passed_list = [r for r in out if r.get("money_flow_pass") is True]
    failed_list = [r for r in out if r.get("money_flow_pass") is not True]
    passed_list.sort(key=lambda x: x.get("score", 0), reverse=True)
    failed_list.sort(key=lambda x: x.get("score", 0), reverse=True)

    if top_n:
        if len(passed_list) >= max(3, top_n // 2):
            result = passed_list[:top_n]
        else:
            result = (passed_list + failed_list)[:top_n]
    else:
        # 生产默认：硬资金已删；其余未通过软门的票不再混入主列表
        # include_soft_fails=1：软门失败降权保留（晨间选股用），仅硬淘出局
        include_soft = os.environ.get("MONEY_GATE_INCLUDE_SOFT_FAILS", "").strip() in (
            "1",
            "true",
            "yes",
        )
        if include_soft:
            for r in failed_list:
                if r.get("money_flow_pass") is not True:
                    try:
                        r["score"] = round(float(r.get("score") or 0) * 0.88, 4)
                    except (TypeError, ValueError):
                        pass
                    r["money_soft_demote"] = True
                    r["drop_reason"] = (r.get("drop_reason") or "") + "|soft_fail_demote"
            result = passed_list + failed_list
            result.sort(key=lambda x: x.get("score", 0), reverse=True)
        else:
            result = passed_list if passed_list else failed_list
    return result


def categorize_by_phase(
    recs: list,
    min_active_buy: float = 0.52,
    min_turnover: float = 2.0,
    max_turnover: float = 35.0,
    min_vol_ratio: float = 0.8,
    max_drop_pct: float = -5.0,
    check_fundamentals: bool = True,
) -> dict:
    """对推荐列表施加资金门控并按资金阶段分组

    Returns:
        {
            "categories": {
                "bear_trap": [ {stock}, ... ],        # 🪤 诱空陷阱
                "rightside_ambush": [ {stock}, ... ],  # 🎯 右侧潜伏
                "accumulation_end": [ {stock}, ... ],  # 🔔 吸筹末期
                "markup": [ {stock}, ... ],            # 🚀 拉升
                "accumulation": [ {stock}, ... ],      # 📥 吸筹
                "suspicious": [ {stock}, ... ],        # ⚠️ 诱多嫌疑
                "distribution": [ {stock}, ... ],      # ⚠️ 出货
                "pullback": [ {stock}, ... ],          # 📉 回调
                "sideways": [ {stock}, ... ],          # ➡️ 震荡
            },
            "stats": { ... }
        }
    """
    gated = apply_money_flow_gate(
        recs,
        min_active_buy=min_active_buy,
        min_turnover=min_turnover,
        max_turnover=max_turnover,
        min_vol_ratio=min_vol_ratio,
        max_drop_pct=max_drop_pct,
        top_n=None,
        check_fundamentals=check_fundamentals,
    )

    categories = {
        "bear_trap": [],        # 🪤 诱空陷阱
        "rightside_ambush": [], # 🎯 右侧潜伏
        "accumulation_end": [], # 🔔 吸筹末期
        "markup": [],           # 🚀 拉升
        "accumulation": [],     # 📥 吸筹
        "suspicious": [],       # ⚠️ 诱多嫌疑
        "distribution": [],     # ⚠️ 出货
        "pullback": [],         # 📉 回调
        "sideways": [],         # ➡️ 震荡
    }

    for item in gated:
        phase = item.get("money_phase", "sideways")
        if phase in categories:
            categories[phase].append(item)

    # 每类按分数排序
    for k in categories:
        categories[k].sort(key=lambda x: x.get("score_raw", 0) or x.get("score", 0), reverse=True)

    return categories


# ════════════════════════════════════════════════════════════════
# V16+ 主力资金阶段判断（含诱空陷阱 + 右侧潜伏）
# ════════════════════════════════════════════════════════════════

def classify_money_phase_v16(
    active_buy_ratio: float,
    change_pct: float,
    vol_ratio: float,
    turnover: float,
    ret_5d: float = 0,
    vol_shrink_days: int = 0,
    atr_trend: float = 1.0,
    price_vs_low: float = 1.05,
) -> tuple:
    """V16+ 主力资金阶段判断

    新增分类：
    - 🪤 诱空陷阱：价格下跌但主力暗中吸筹（洗盘信号）
    - 🎯 右侧潜伏：吸筹完成、刚启动、即将拉升（起爆点）

    Returns:
        (phase_key, phase_label, phase_emoji)
    """
    abr = active_buy_ratio if active_buy_ratio else 0.5
    chg = change_pct if change_pct else 0
    vr = vol_ratio if vol_ratio and vol_ratio > 0 else 1.0

    # ── 出货 ⚠️：放量下跌 + 资金流出 ──
    if abr < 0.45 and chg < -2.0 and vr > 1.2:
        return ("distribution", "出货", "⚠️")

    # ── 回调 📉：资金流出 + 阴跌 ──
    if abr < 0.48 and chg < -1.0:
        return ("pullback", "回调", "📉")

    # ── 诱空陷阱 🪤：主力压价洗盘，实际在吸筹 ──
    # 价格下跌但主动性买盘却很高
    # 量不大（不是真恐慌），价位接近低点
    if abr >= 0.52 and chg < 0 and vr <= 1.2 and price_vs_low < 1.05:
        return ("bear_trap", "诱空陷阱", "🪤")

    # ── 吸筹末期 🔔：缩量蓄力 + 主动买 ──
    if vol_shrink_days >= 3 and abr >= 0.52 and atr_trend < 0.95:
        return ("accumulation_end", "吸筹末期", "🔔")

    # ── 右侧潜伏 🎯：刚启动的起爆点 ──
    # 吸筹完成，股价刚刚转涨，量能开始恢复
    # ATR开始扩张（波动率回归），缩量天数已清零
    if abr >= 0.52 and chg >= 0 and chg <= 2.5 and vr >= 0.8 and vr <= 2.0 and atr_trend >= 0.95 and vol_shrink_days <= 2:
        return ("rightside_ambush", "右侧潜伏", "🎯")

    # ── 吸筹 📥：主动买强 + 不涨/微涨 ──
    if abr >= 0.52 and chg < 2.0:
        return ("accumulation", "吸筹", "📥")

    # ── 拉升 🚀：主动买强 + 放量大涨 ──
    if (abr >= 0.55 and chg > 3.0 and vr > 1.5) or (abr >= 0.52 and chg >= 2.0):
        return ("markup", "拉升", "🚀")

    # ── 诱多嫌疑 ⚠️：高位缩量 + 涨幅大 ──
    if ret_5d > 0.15 and vol_shrink_days >= 2 and chg > 0:
        return ("suspicious", "诱多嫌疑", "⚠️")

    # ── 震荡 ➡️ ──
    return ("sideways", "震荡", "➡️")


def detect_price_volume_anomalies(item: dict) -> dict:
    """价量异常 / 骗线识别 → 返回 flags + penalty。

    依赖 item 上已有的盘口/特征字段（无 K 线时做弱检测）。
    """
    flags: dict = {}
    penalty = 0.0
    try:
        abr = float(item.get("active_buy_ratio") or 0.5)
    except (TypeError, ValueError):
        abr = 0.5
    try:
        chg = float(item.get("change_pct") or 0)
    except (TypeError, ValueError):
        chg = 0.0
    try:
        vr = float(item.get("volume_ratio") or 1.0)
    except (TypeError, ValueError):
        vr = 1.0
    try:
        main_net = float(item.get("main_net") or item.get("live_main_net") or 0)
    except (TypeError, ValueError):
        main_net = 0.0
    feats = item.get("features") or {}
    try:
        ret_5d = float(feats.get("ret_5d") or 0)
    except (TypeError, ValueError):
        ret_5d = 0.0
    try:
        vol_shrink = int(feats.get("vol_shrink_days") or 0)
    except (TypeError, ValueError):
        vol_shrink = 0

    # 1) 对倒放量：量比高但几乎不涨 + 主动买弱
    if vr > 3.0 and abs(chg) < 1.0 and abr < 0.50:
        flags["wash_trade"] = True
        penalty -= 0.08

    # 2) 价量背离：近5日大涨但量能萎缩
    if ret_5d > 0.12 and vr < 0.7 and vol_shrink >= 2:
        flags["divergence"] = True
        penalty -= 0.06

    # 3) 拉升出货嫌疑：大涨但主力净流出
    if chg >= 5.0 and main_net < -1e6 and abr < 0.50:
        flags["pump_dump"] = True
        penalty -= 0.10

    # 4) 诱多：高位缩量阳线
    if ret_5d > 0.18 and vol_shrink >= 2 and chg > 0 and vr < 0.9:
        flags["bull_trap"] = True
        penalty -= 0.05

    if flags:
        item["anomaly_flags"] = flags
        item["anomaly_penalty"] = round(penalty, 4)
    return {"flags": flags, "penalty": round(penalty, 4)}


# ════════════════════════════════════════════════════════════════
# S2 规则加权层（后门控，不出局只加分）— 参数可配置
# ════════════════════════════════════════════════════════════════

_S2_PARAMS_CACHE: dict | None = None


def load_s2_params(arm: str | None = None) -> dict:
    """加载 S2 参数。S2_ARM=B 时读 config/s2_params_B.json。"""
    global _S2_PARAMS_CACHE
    env_arm = (arm or os.environ.get("S2_ARM", "A") or "A").strip().upper()
    if _S2_PARAMS_CACHE and _S2_PARAMS_CACHE.get("_arm") == env_arm:
        return _S2_PARAMS_CACHE

    root = Path(__file__).resolve().parent
    if env_arm and env_arm != "A":
        path = root / "config" / f"s2_params_{env_arm}.json"
    else:
        path = root / "config" / "s2_params.json"
    if not path.exists():
        path = root / "config" / "s2_params.json"

    default = {
        "_arm": env_arm,
        "s2_rules": {
            "change_pct": {"type": "range", "range": [3.0, 5.0], "bonus": 0.05},
            "volume_ratio": {"type": "gt", "threshold": 1.5, "bonus": 0.05},
            "turnover": {"type": "range", "range": [5.0, 10.0], "bonus": 0.04},
            "circ_mv": {"type": "range", "range": [50.0, 200.0], "bonus": 0.04},
            "ma_bullish": {"type": "bool", "bonus": 0.10},
            "close_strength": {"type": "range", "range": [0.0, 0.05], "bonus": 0.05},
            "above_vwap": {"type": "bool", "bonus": 0.05},
            "volatility_20d": {"type": "gt", "threshold": 0.02, "bonus": 0.03},
            "chip_penetration": {"type": "gt", "threshold": 0.05, "bonus": 0.02},
        },
    }
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["_arm"] = env_arm
        _S2_PARAMS_CACHE = raw
        return raw
    except Exception:
        _S2_PARAMS_CACHE = default
        return default


def s2_weight_score(
    change_pct: float = 0,
    volume_ratio: float = 0,
    turnover: float = 0,
    circ_mv: float = 0,
    ma_bullish: bool = False,
    close_strength: float = 1.0,
    above_vwap: bool = False,
    volatility_20d: float = 0,
    chip_penetration: float = 0,
) -> float:
    """计算 S2 规则加分（配置驱动，默认约 0~0.4）。"""
    params = load_s2_params()
    rules = params.get("s2_rules") or {}
    values = {
        "change_pct": change_pct,
        "volume_ratio": volume_ratio,
        "turnover": turnover,
        "circ_mv": circ_mv,
        "ma_bullish": ma_bullish,
        "close_strength": close_strength,
        "above_vwap": above_vwap,
        "volatility_20d": volatility_20d,
        "chip_penetration": chip_penetration,
    }
    score = 0.0
    for name, cfg in rules.items():
        if not isinstance(cfg, dict):
            continue
        val = values.get(name)
        bonus = float(cfg.get("bonus") or 0)
        rtype = cfg.get("type") or "gt"
        if rtype == "bool":
            if bool(val):
                score += bonus
        elif rtype == "range":
            rng = cfg.get("range") or [0, 0]
            try:
                lo, hi = float(rng[0]), float(rng[1])
                if val is not None and lo <= float(val) <= hi:
                    score += bonus
            except (TypeError, ValueError, IndexError):
                pass
        elif rtype == "gt":
            try:
                if val is not None and float(val) > float(cfg.get("threshold") or 0):
                    score += bonus
            except (TypeError, ValueError):
                pass
    return round(score, 4)
