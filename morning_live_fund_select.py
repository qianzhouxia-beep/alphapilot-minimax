#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""09:35 盘中：对推荐池刷实时资金门 →（可选）研报软加权 → 按资金门结果取 Top2。

默认 MORNING_RANK_MODE=fund（跟资金门，与网页 Top10 机会同口径）：
  只从 money_flow_pass=True 里按主动买/主力净流入排序取 Top2。

Env:
  MORNING_RANK_MODE=fund|model   默认 fund
  RESEARCH_GATE_MODE            fund 模式下若未设置则用 prefer_soft（avoid 不硬剔）
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
RANK_MODE = os.environ.get("MORNING_RANK_MODE", "fund").strip().lower() or "fund"
MODE_NAME = (
    "morning_live_fund_top2" if RANK_MODE == "fund" else "morning_live_model_top2"
)


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
    """prefer 优先，再按模型 score。"""

    def sort_key(r: dict):
        prefer = 0 if r.get("research_tier") == "prefer" else 1
        try:
            sc = float(r.get("score") or r.get("ml_score") or r.get("lgb_score") or 0)
        except (TypeError, ValueError):
            sc = 0.0
        return (prefer, -sc)

    return sorted(gated, key=sort_key)[:top_n]


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

    recs = json.loads(REC_PATH.read_text(encoding="utf-8"))
    items = list(recs.get("recommendations") or [])
    expo = float(recs.get("position_exposure") or 0.0)
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

    # fund 模式：与 Top10 一致，软失败不进候选（默认不 include soft fails）
    if RANK_MODE == "fund":
        os.environ["MONEY_GATE_INCLUDE_SOFT_FAILS"] = os.environ.get(
            "MONEY_GATE_INCLUDE_SOFT_FAILS", "0"
        )
        # avoid 硬剔会把池子挤进「研报 prefer」冷票；跟资金门时改为软加分
        if not os.environ.get("RESEARCH_GATE_MODE"):
            os.environ["RESEARCH_GATE_MODE"] = "prefer_soft"
    else:
        os.environ["MONEY_GATE_INCLUDE_SOFT_FAILS"] = os.environ.get(
            "MONEY_GATE_INCLUDE_SOFT_FAILS", "1"
        )
    log(
        f"▶ 实时资金门重跑 pool={len(pool)} "
        f"(soft_demote={os.environ['MONEY_GATE_INCLUDE_SOFT_FAILS']} "
        f"rank={RANK_MODE} research={os.environ.get('RESEARCH_GATE_MODE', 'hybrid')}) ..."
    )
    gated = apply_money_flow_gate(pool, top_n=None, hard_main_net_5d=True)
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
            "bias_date": (bias or {}).get("date"),
            "bias_session": (bias or {}).get("session"),
            "prefer": (bias or {}).get("prefer") or [],
            "avoid": (bias or {}).get("avoid") or [],
            "before": before,
            "after": len(gated),
            "prefer_hits": meta.get("prefer_hits"),
            "avoid_drop": meta.get("avoid_drop"),
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
    if RANK_MODE == "fund":
        chosen = select_top_by_inflow(gated, top_n=LIVE_TOP_N)
        rank_by = "money_flow_pass+abr+live_main_net"
    else:
        chosen = select_top_by_score(gated, top_n=LIVE_TOP_N)
        rank_by = "prefer_then_score"

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
    for i, it in enumerate(chosen):
        it["morning_pick_rank"] = i + 1

    recs["recommendations"] = new_recs[: max(pool_n, len(chosen))]
    recs["recommend_top_n"] = LIVE_TOP_N if expo > 0 else 0
    recs["recommend_pool_n"] = pool_n
    recs["morning_live_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    recs["morning_live_mode"] = MODE_NAME
    REC_PATH.write_text(json.dumps(recs, ensure_ascii=False, indent=2), encoding="utf-8")

    pick_rows = []
    for r in chosen:
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
            }
        )

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
