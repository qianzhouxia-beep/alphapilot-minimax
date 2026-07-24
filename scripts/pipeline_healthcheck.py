#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全管线体检：模块可导入、数据文件、VM2.5打分、各门控烟测。"""
from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(os.environ.get("ALPHAPILOT_ROOT", "/home/ubuntu/alphapilot"))
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

OK, WARN, FAIL = [], [], []


def ok(msg):
    OK.append(msg)
    print(f"  ✅ {msg}", flush=True)


def warn(msg):
    WARN.append(msg)
    print(f"  ⚠️ {msg}", flush=True)


def fail(msg):
    FAIL.append(msg)
    print(f"  ❌ {msg}", flush=True)


def check_files():
    print("\n== 数据/模型文件 ==", flush=True)
    required = {
        "models/v25_meta.json": True,
        "models/v25_opt_ensemble_1.ubj": True,
        "models/v25_opt_ensemble_2.ubj": True,
        "models/v25_opt_ensemble_3.ubj": True,
        "data/fund_flow_history.json": True,
        "data/stock_industry_map.json": True,
        "data/stock_concept_map.json": True,
        "data/sector_flow_today.json": False,
        "data/concept_flow_today.json": False,
        "data/chip_data_all.json": False,
        "chip_data_all.json": False,
        "models/best_tech_params.json": False,
    }
    for rel, must in required.items():
        p = ROOT / rel
        if p.exists() and p.stat().st_size > 10:
            ok(f"{rel} ({p.stat().st_size} bytes)")
        elif must:
            fail(f"missing required {rel}")
        else:
            warn(f"optional missing {rel}")


def check_imports():
    print("\n== 模块导入 ==", flush=True)
    mods = [
        "vm25_scorer",
        "ml_screener",
        "money_flow_gate",
        "market_env_gate",
        "sector_rotation_gate",
        "soft_intraday_gate",
        "features_v2",
    ]
    for m in mods:
        try:
            __import__(m)
            ok(f"import {m}")
        except Exception as e:
            fail(f"import {m}: {e}")


def check_v25_wire():
    print("\n== VM2.5 接线 ==", flush=True)
    try:
        from ml_screener import MLScreener

        s = MLScreener()
        if not s.load_model(version="v25"):
            fail("load_model(v25) returned False")
            return
        if s.model_version != "v25":
            fail(f"model_version={s.model_version} expected v25")
        else:
            ok(f"MLScreener v25 loaded models={len(s.models)}")
        rec = (ROOT / "recommend.py").read_text(encoding="utf-8", errors="replace")
        if 'load_model(version="v25")' in rec or "load_model(version='v25')" in rec:
            ok("recommend.py requests v25")
        else:
            fail("recommend.py still not on v25")
    except Exception as e:
        fail(f"v25 wire: {e}")
        traceback.print_exc()


def check_score_sample():
    print("\n== VM2.5 样例打分 ==", flush=True)
    try:
        import pandas as pd
        from vm25_scorer import VM25Scorer

        scorer = VM25Scorer(prefer="opt")
        if not scorer.load():
            fail("VM25Scorer.load failed")
            return
        ok(f"VM25Scorer feats={len(scorer.feature_names)}")

        kpath = ROOT / "data/kline_cache/kline_all.parquet"
        if not kpath.exists():
            kpath = ROOT / "kline_all.parquet"
        if not kpath.exists():
            warn("no kline parquet; skip sample score")
            return
        df = pd.read_parquet(kpath)
        df["symbol"] = df["symbol"].astype(str).str.replace(r"^(sh|sz|bj)", "", regex=True).str[-6:]
        sym = "600519" if (df["symbol"] == "600519").any() else str(df["symbol"].iloc[0])
        g = df[df["symbol"] == sym].sort_values("date").tail(120)
        r = scorer.score(g, sym, sector_heat=0.5)
        if "error" in r:
            fail(f"score {sym}: {r}")
        else:
            ok(f"score {sym}={r.get('score')} proba={r.get('lgb_score', r.get('proba'))}")
    except Exception as e:
        fail(f"sample score: {e}")
        traceback.print_exc()


def check_fund_hard():
    print("\n== 资金硬门控 ==", flush=True)
    try:
        import inspect
        from money_flow_gate import apply_money_flow_gate

        sig = inspect.signature(apply_money_flow_gate)
        if "hard_main_net_5d" not in sig.parameters:
            fail("apply_money_flow_gate missing hard_main_net_5d")
        else:
            ok("hard_main_net_5d param present")
        src = (ROOT / "money_flow_gate.py").read_text(encoding="utf-8", errors="replace")
        if "import os" in src and "import json" in src:
            ok("money_flow_gate has os/json imports")
        else:
            fail("money_flow_gate missing os/json imports")
        # synthetic hard drop
        demo = [{"symbol": "600000", "score": 0.7, "name": "demo"}]
        # if fund hist has this code with negative 5d, should drop
        fh = ROOT / "data/fund_flow_history.json"
        if fh.exists():
            hist = json.loads(fh.read_text(encoding="utf-8"))
            # pick a code with enough negative history if any
            neg = None
            for code, days in list(hist.items())[:2000]:
                if not isinstance(days, dict) or len(days) < 5:
                    continue
                ds = sorted(days.keys())[-5:]
                s = sum(float(days[d]) for d in ds)
                if s <= 0:
                    neg = code
                    break
            if neg:
                out = apply_money_flow_gate(
                    [{"symbol": neg, "score": 0.8, "name": "neg"}],
                    hard_main_net_5d=True,
                    check_fundamentals=False,
                    top_n=None,
                )
                if any(x.get("symbol") == neg for x in out):
                    # may still pass if quotes path weird — check fund_hard
                    warn(f"hard gate sample {neg} still in out n={len(out)} (quotes/fundamentals may override soft pass)")
                else:
                    ok(f"hard gate dropped sample {neg}")
            else:
                warn("no negative 5d sample found in first 2000 codes")
        else:
            warn("no fund_flow_history for hard gate sample")
    except Exception as e:
        fail(f"fund hard: {e}")
        traceback.print_exc()


def check_market_env():
    print("\n== 大盘环境门控 ==", flush=True)
    try:
        from market_env_gate import (
            apply_market_env_gate,
            build_market_env,
            position_exposure,
            TECH_INDUSTRY_L1,
        )

        env = build_market_env(lmt=30)
        flags = env.get("flags") or {}
        expo = float(env.get("position_exposure", position_exposure(flags)))
        ok(f"env flags={flags} exposure={expo}")
        demo = [
            {"symbol": "300750", "score": 0.7, "name": "宁德"},
            {"symbol": "688981", "score": 0.68, "name": "中芯"},
            {"symbol": "600519", "score": 0.65, "name": "茅台", "industry_l1": "食品饮料"},
        ]
        imap = {}
        ip = ROOT / "data/stock_industry_map.json"
        if ip.exists():
            imap = json.loads(ip.read_text(encoding="utf-8"))
        out = apply_market_env_gate(demo, env=env, hard_filter=True, industry_map=imap)
        ok(f"market_env kept {len(out)}/{len(demo)}; TECH_L1={len(TECH_INDUSTRY_L1)}")
    except Exception as e:
        fail(f"market_env: {e}")
        traceback.print_exc()


def check_sector_dual():
    print("\n== 行业×概念 dual ==", flush=True)
    try:
        from sector_rotation_gate import apply_sector_rotation_gate, build_snapshot

        snap = build_snapshot()
        n_ind = len((snap.get("classes") or {}).get("allow", []))
        n_deny = len((snap.get("classes") or {}).get("deny", []))
        n_ca = len((snap.get("concept_classes") or {}).get("allow", []))
        ok(f"snapshot industry allow={n_ind} deny={n_deny} concept_allow={n_ca}")
        demo = [
            {"symbol": "600519", "score": 0.7, "name": "茅台"},
            {"symbol": "300750", "score": 0.69, "name": "宁德"},
        ]
        out = apply_sector_rotation_gate(demo, snap=snap, mode="dual")
        ok(f"dual gate kept {len(out)}/{len(demo)}")
    except Exception as e:
        fail(f"sector dual: {e}")
        traceback.print_exc()


def check_pipeline_flags():
    print("\n== 管线策略开关 ==", flush=True)
    src = (ROOT / "alphapilot_pipeline_v3.py").read_text(encoding="utf-8", errors="replace")
    if "ENABLE_SOFT_INTRADAY" in src:
        ok("soft_intraday gated by ENABLE_SOFT_INTRADAY")
    else:
        fail("soft_intraday still always-on")
    if "不回退全量推荐" in src or "保持严格金叉" in src:
        ok("GC empty fallback disabled")
    else:
        fail("GC empty still falls back to unfiltered")
    if "s2_bonus" in src or "s2_applied_in_money_gate" in src:
        ok("S2 field alignment present in pipeline")
    else:
        warn("pipeline S2 may still only read s2_score")


def main():
    print(f"ROOT={ROOT}", flush=True)
    check_files()
    check_imports()
    check_v25_wire()
    check_score_sample()
    check_fund_hard()
    check_market_env()
    check_sector_dual()
    check_pipeline_flags()

    report = {
        "root": str(ROOT),
        "ok": OK,
        "warn": WARN,
        "fail": FAIL,
        "pass": len(FAIL) == 0,
    }
    out = ROOT / "output" / "pipeline_healthcheck.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n======== SUMMARY ========", flush=True)
    print(f"OK={len(OK)} WARN={len(WARN)} FAIL={len(FAIL)}", flush=True)
    print(f"saved {out}", flush=True)
    if FAIL:
        print("HEALTHCHECK_FAIL", flush=True)
        return 1
    print("HEALTHCHECK_PASS", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
