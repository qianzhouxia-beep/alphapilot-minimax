#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AlphaPilot V2.5 训练脚本 (A/B 版)
=====================================================================
目的: 干净地隔离"最优 MA/MACD/RSI 技术块"对全模型的边际贡献。
方法: 用同一份特征计算, 训练两个模型做对照:
  - V25_base: 基础(动态工程特征) + 派生(8) + 筹码峰(6)   [不含技术块]
  - V25_opt : V25_base + 寻优得到的最优技术块(MA+MACD, 弃RSI)
两者唯一区别 = 是否含最优技术块 -> AUC 差即为技术块的边际增益。

修复 (2026-07-18):
  - 训练时把资金流 / 融资融券 / 业绩预告 / 基本面真正传入 build_full_features_v2
  - 启动前打印各数据通道覆盖率；过低时警告（不静默填零）
  - 筹码数据从 chip_data_all.json 手动合并
  - 基础特征列排除原始 OHLCV/date/symbol(避免泄漏/冗余)
"""
import os, sys, json, time, warnings, gc
import numpy as np, pandas as pd
import xgboost as xgb
from pathlib import Path
from datetime import datetime

warnings.filterwarnings("ignore")
ROOT = Path(os.environ.get("ALPHAPILOT_ROOT") or "/home/ubuntu/alphapilot")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from data_fetcher import get_stock_list
import features_v2 as ft
from auto_factor_engine import derive_factors
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import TimeSeriesSplit

# 默认生产 models/；研发车间经 ALPHAPILOT_MODEL_DIR / --model-dir 写到候选目录
MODEL_DIR = Path(os.environ.get("ALPHAPILOT_MODEL_DIR") or (ROOT / "models"))
N_MODELS = 3
N_BOOST_ROUND = 300
EARLY_STOPPING = 50
FORWARD_DAYS = 1
THRESHOLD = 0.03

DERIVED_COLS = ['volume_price', 'vol_turnover', 'money_flow_vol',
                'momentum_accel', 'trend_strength', 'conv_div', 'price_dev', 'bull_confirmation']
CHIP_FACTORS = ['z_chip_concentration', 'chip_penetration_3d', 'avg_cost_shift_10d',
                'chip_profit_trend', 'chip_distribution_width', 'chip_distribution_shape']
RAW = ['date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'outstanding_share', 'turnover', 'symbol']

# V3 通道特征：用于覆盖率统计（不依赖是否进入最终 base_cols）
FLOW_COLS = ["main_net_today", "main_net_5d", "main_net_10d"]
MARGIN_COLS = ["margin_balance", "margin_buy"]
EVENT_COLS = ["has_forecast", "yjyg_max_change_pct"]

MACD_PAIRS = [(6, 13), (8, 17), (12, 26)]


def load_json_safe(path, default=None):
    """加载 JSON；尾部截断时尝试修复到最后一个完整对象。"""
    if default is None:
        default = {}
    p = Path(path)
    if not p.exists():
        return default
    raw = p.read_text(encoding="utf-8", errors="ignore")
    if not raw.strip():
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # fund_flow_history 偶发尾部截断
        i = raw.rfind("},")
        if i > 0:
            try:
                return json.loads(raw[: i + 1] + "}")
            except json.JSONDecodeError:
                pass
        print(f"  ⚠️ JSON 损坏，跳过: {path}")
        return default


def bare_code(sym) -> str:
    s = str(sym).strip()
    if "." in s:
        s = s.split(".")[0]
    return s.zfill(6)[-6:]


def load_best_params():
    d = json.load(open("models/best_tech_params.json"))
    p = dict(d["best_params"])
    if "macd_pair" in p:
        p["macd_f"], p["macd_s"] = MACD_PAIRS[p["macd_pair"]]
    if p.get("use_rsi", False):
        p.setdefault("rsi1", 6)
        p.setdefault("rsi2", 12)
        p.setdefault("rsi3", 24)
    return p


BEST = load_best_params()

CHIP = {}
for chip_path in ("chip_data_all.json", "data/chip_data_all.json"):
    if os.path.exists(chip_path):
        try:
            CHIP = load_json_safe(chip_path, {})
            break
        except Exception:
            CHIP = {}


def load_v3_side_data():
    """加载 V3 侧车数据：资金流 / 两融 / 业绩预告 / 基本面。"""
    fund_flow = load_json_safe("data/fund_flow_history.json", {})
    # 统一 key 为 6 位代码
    fund_flow = {bare_code(k): v for k, v in fund_flow.items() if isinstance(v, dict)}

    margin = load_json_safe("data/margin_data.json", {})
    margin = {bare_code(k): v for k, v in margin.items() if isinstance(v, dict)}

    event = load_json_safe("data/event_forecast.json", {})
    event = {bare_code(k): v for k, v in event.items() if isinstance(v, dict)}

    fundamentals = {}
    for fp in ("fundamental_data.json", "data/fundamental_data.json"):
        if os.path.exists(fp):
            fundamentals = load_json_safe(fp, {})
            fundamentals = {bare_code(k): v for k, v in fundamentals.items() if isinstance(v, dict)}
            break

    lhb_hist = load_json_safe("data/lhb_history.json", {})
    lhb_hist = {bare_code(k): v for k, v in lhb_hist.items() if isinstance(v, dict)}

    return fund_flow, margin, event, fundamentals, lhb_hist


def apply_lhb_dates(feats: pd.DataFrame, lhb_rec: dict | None) -> pd.DataFrame:
    """按日对齐龙虎榜：仅在上榜日期置 has_lhb / buy_inst_count。"""
    if feats is None or not lhb_rec or "date" not in feats.columns:
        return feats
    dates_map = lhb_rec.get("dates") or {}
    if not dates_map:
        return feats
    feats = feats.copy()
    dser = feats["date"].astype(str).str[:10]
    feats["has_lhb"] = dser.map(lambda d: 1.0 if d in dates_map else 0.0).astype(float)
    feats["buy_inst_count"] = dser.map(lambda d: float(dates_map.get(d, 0) or 0)).astype(float)
    return feats


def report_data_coverage(symbols, fund_flow, margin, event, fundamentals, lhb_hist=None):
    """训练前打印通道覆盖率，避免再 silent 全零训练。"""
    n = len(symbols) or 1
    flow_hits = sum(1 for s in symbols if bare_code(s) in fund_flow and len(fund_flow[bare_code(s)]) > 0)
    depths = [len(fund_flow[bare_code(s)]) for s in symbols if bare_code(s) in fund_flow and fund_flow[bare_code(s)]]
    margin_hits = sum(1 for s in symbols if bare_code(s) in margin)
    event_hits = sum(1 for s in symbols if bare_code(s) in event)
    fund_hits = sum(1 for s in symbols if bare_code(s) in fundamentals)
    chip_hits = sum(1 for s in symbols if bare_code(s) in CHIP or s in CHIP)
    lhb_hits = sum(1 for s in symbols if bare_code(s) in (lhb_hist or {}))

    mean_depth = float(np.mean(depths)) if depths else 0.0
    med_depth = float(np.median(depths)) if depths else 0.0

    print("\n=== V3 数据通道覆盖率（相对股票池）===")
    print(f"  资金流   : {flow_hits}/{len(symbols)} ({flow_hits/n:.1%}) | 深度 mean={mean_depth:.1f} med={med_depth:.1f} 天")
    print(f"  融资融券 : {margin_hits}/{len(symbols)} ({margin_hits/n:.1%})")
    print(f"  业绩预告 : {event_hits}/{len(symbols)} ({event_hits/n:.1%})")
    print(f"  基本面   : {fund_hits}/{len(symbols)} ({fund_hits/n:.1%})")
    print(f"  筹码快照 : {chip_hits}/{len(symbols)} ({chip_hits/n:.1%})")
    print(f"  龙虎榜   : {lhb_hits}/{len(symbols)} ({lhb_hits/n:.1%})")

    warnings_out = []
    if flow_hits / n < 0.5:
        warnings_out.append("资金流覆盖 <50%")
    if mean_depth < 40:
        warnings_out.append(f"资金流深度偏短 (mean={mean_depth:.0f}天，建议≥60)")
    if margin_hits / n < 0.3:
        warnings_out.append("融资融券覆盖 <30%（深市可能缺失）")
    if event_hits == 0:
        warnings_out.append("业绩预告为空 — 请先跑 python3 pull_margin_event_data.py")
    if fund_hits / n < 0.05:
        warnings_out.append("基本面几乎为空（当前可继续，但基本面维无效）")
    if chip_hits / n < 0.5:
        warnings_out.append("筹码覆盖 <50%")
    if lhb_hits / n < 0.01:
        warnings_out.append("龙虎榜历史很少 — buy_inst_count/has_lhb 可能仍弱")

    if warnings_out:
        print("  ⚠️ 数据警告:")
        for w in warnings_out:
            print(f"     - {w}")
    else:
        print("  ✅ 通道覆盖可接受，开始特征构建")

    return {
        "fund_flow_coverage": round(flow_hits / n, 4),
        "fund_flow_mean_depth": round(mean_depth, 2),
        "fund_flow_median_depth": round(med_depth, 2),
        "margin_coverage": round(margin_hits / n, 4),
        "event_coverage": round(event_hits / n, 4),
        "fundamental_coverage": round(fund_hits / n, 4),
        "chip_coverage": round(chip_hits / n, 4),
        "lhb_coverage": round(lhb_hits / n, 4),
        "warnings": warnings_out,
    }


def merge_chip(feats, sym):
    """合并筹码快照。

    历史只有截面快照、没有日频筹码序列时：用 close/avgCost 构造随价格变化的
    盈亏与偏移，避免整列常量导致 XGB 永不分裂。
    """
    code = bare_code(sym)
    c = CHIP.get(code) or CHIP.get(sym)
    if not c:
        return feats
    if isinstance(c, list):
        c = c[-1]
    feats = feats.copy()
    conc90 = float(c.get("chipConcentration90", 0) or 0)
    conc70 = float(c.get("chipConcentration70", 0) or 0)
    snap_profit = float(c.get("chipProfitRate", 0) or 0)
    avg_cost = float(c.get("chipAvgCost", 0) or 0)
    feats["chip_concentration"] = conc90
    feats["chip_concentration_70"] = conc70
    if avg_cost > 1e-6 and "close" in feats.columns:
        bias = feats["close"].astype(float) / avg_cost - 1.0
        feats["chip_profit_rate"] = bias
        feats["chip_penetration"] = bias.clip(lower=0.0)
        feats["avg_cost_shift_5d"] = bias.diff(5).fillna(0.0)
    else:
        feats["chip_profit_rate"] = snap_profit
        feats["chip_penetration"] = max(snap_profit, 0.0)
        feats["avg_cost_shift_5d"] = 0.0
    return feats


def rsi_series(close, n):
    d = close.diff()
    gain = d.clip(lower=0)
    loss = (-d).clip(lower=0)
    ag = gain.rolling(n, min_periods=n).mean()
    al = loss.rolling(n, min_periods=n).mean()
    return 100 - 100 / (1 + (ag / (al + 1e-10)))


def compute_optimized_tech(df):
    df = df.sort_values("date").copy()
    close = df["close"]
    p = BEST
    if p.get("use_ma", True):
        ms, ml, mv = p["ma_s"], p["ma_l"], p["ma_vl"]
        ma_s = close.rolling(ms, min_periods=ms).mean()
        ma_l = close.rolling(ml, min_periods=ml).mean()
        ma_vl = close.rolling(mv, min_periods=mv).mean()
        df["opt_ma_price_above_long"] = (close > ma_l).astype(float)
        df["opt_ma_short_above_long"] = (ma_s > ma_l).astype(float)
        df["opt_ma_mid_above_vlong"] = (ma_l > ma_vl).astype(float)
        df["opt_ma_long_slope"] = ma_l.pct_change(5)
        df["opt_ma_dist_long"] = (close - ma_l) / ma_l
    if p.get("use_macd", True):
        f, s, sig = p["macd_f"], p["macd_s"], p["macd_sig"]
        ef = close.ewm(span=f, adjust=False).mean()
        es = close.ewm(span=s, adjust=False).mean()
        dif = ef - es
        dea = dif.ewm(span=sig, adjust=False).mean()
        hist = (dif - dea) * 2
        df["opt_macd_dif"] = dif
        df["opt_macd_hist"] = hist
        df["opt_macd_hist_slope"] = hist.diff(3)
        df["opt_macd_dif_pos"] = (dif > 0).astype(float)
        df["opt_macd_zero_above5"] = (dif > 0).rolling(5).sum() / 5.0
    if p.get("use_rsi", True):
        df["opt_rsi1"] = rsi_series(close, p["rsi1"])
        df["opt_rsi2"] = rsi_series(close, p["rsi2"])
        df["opt_rsi3"] = rsi_series(close, p["rsi3"])
        df["opt_rsi_oversold"] = (df["opt_rsi1"] < 30).rolling(3).max().fillna(0)
        df["opt_rsi_overbought"] = (df["opt_rsi1"] > 70).rolling(3).max().fillna(0)
        df["opt_rsi_cross"] = (df["opt_rsi1"] > df["opt_rsi2"]).astype(float)
    return df


def tech_col_names():
    p = BEST
    cols = []
    if p.get("use_ma", True):
        cols += ["opt_ma_price_above_long", "opt_ma_short_above_long", "opt_ma_mid_above_vlong",
                 "opt_ma_long_slope", "opt_ma_dist_long"]
    if p.get("use_macd", True):
        cols += ["opt_macd_dif", "opt_macd_hist", "opt_macd_hist_slope",
                 "opt_macd_dif_pos", "opt_macd_zero_above5"]
    if p.get("use_rsi", True):
        cols += ["opt_rsi1", "opt_rsi2", "opt_rsi3", "opt_rsi_oversold",
                 "opt_rsi_overbought", "opt_rsi_cross"]
    return cols


def compute_chip_factors(df):
    """筹码派生因子。

    集中度快照在个股时序上是常量，时间 z-score≈0；改为保留截面水平信号，
    并用 close/成本 序列驱动 penetration / shift / profit_trend。
    """
    df = df.copy()
    if len(df) < 20:
        for c in CHIP_FACTORS:
            df[c] = 0.0
        return df
    if "chip_concentration" in df.columns:
        conc = df["chip_concentration"].astype(float)
        # 截面水平（常量时序仍可跨票分裂）；再叠一层相对 20 日波动的稳健缩放
        df["z_chip_concentration"] = (conc / 20.0).fillna(0.0)
    else:
        df["z_chip_concentration"] = 0.0
    if "chip_penetration" in df.columns:
        df["chip_penetration_3d"] = (
            df["chip_penetration"].astype(float).rolling(3, min_periods=1).mean().fillna(0)
        )
    else:
        df["chip_penetration_3d"] = 0.0
    if "avg_cost_shift_5d" in df.columns:
        df["avg_cost_shift_10d"] = (
            df["avg_cost_shift_5d"].astype(float).rolling(2, min_periods=1).sum().fillna(0)
        )
    else:
        df["avg_cost_shift_10d"] = 0.0
    if "chip_profit_rate" in df.columns:
        df["chip_profit_trend"] = df["chip_profit_rate"].astype(float).diff(3).fillna(0)
    else:
        df["chip_profit_trend"] = 0.0
    if "chip_concentration" in df.columns:
        df["chip_distribution_width"] = df["chip_concentration"].astype(float).fillna(0)
    else:
        df["chip_distribution_width"] = 0.0
    if "chip_concentration" in df.columns and "chip_concentration_70" in df.columns:
        df["chip_distribution_shape"] = (
            df["chip_concentration"].astype(float)
            / (df["chip_concentration_70"].astype(float) + 1e-8)
        ).fillna(1.0)
    else:
        df["chip_distribution_shape"] = 1.0
    return df


def train_ensemble(X, y, name):
    tscv = TimeSeriesSplit(n_splits=N_MODELS)
    aucs = []
    params = {
        "max_depth": 4, "learning_rate": 0.05, "subsample": 0.6, "colsample_bytree": 0.6,
        "min_child_weight": 5, "tree_method": "hist", "seed": 42,
        "scale_pos_weight": 8.0, "eval_metric": "auc", "objective": "binary:logistic",
    }
    MODEL_DIR.mkdir(exist_ok=True)
    feats = list(X.columns)
    for i, (tr, va) in enumerate(tscv.split(X.values)):
        X_tr, X_val = X.values[tr], X.values[va]
        y_tr, y_val = y[tr], y[va]
        dtrain = xgb.DMatrix(X_tr, label=y_tr, feature_names=feats)
        dval = xgb.DMatrix(X_val, label=y_val, feature_names=feats)
        p = params.copy()
        p["seed"] = 42 + i * 100
        model = xgb.train(
            p, dtrain, num_boost_round=N_BOOST_ROUND,
            evals=[(dtrain, "train"), (dval, "val")],
            early_stopping_rounds=EARLY_STOPPING, verbose_eval=False,
        )
        pred = model.predict(dval)
        auc = roc_auc_score(y_val, pred)
        aucs.append(auc)
        model.save_model(str(MODEL_DIR / f"{name}_ensemble_{i+1}.ubj"))
        print(f"  [{name}] Model {i+1}/{N_MODELS} AUC={auc:.4f} 树={model.best_iteration+1}")
        del dtrain, dval, model, pred, X_tr, X_val, y_tr, y_val
        gc.collect()
    return float(np.mean(aucs)), aucs, feats


def nonzero_rate(df, cols):
    present = [c for c in cols if c in df.columns]
    if not present:
        return 0.0
    arr = df[present].to_numpy(dtype=float)
    return float(np.mean(np.abs(arr) > 1e-12))


def _load_extra_factors(path: str | None):
    """加载研发车间归一化因子表；失败则空。"""
    if not path:
        return None, []
    p = Path(path)
    if not p.exists():
        print(f"  ⚠️ extra-factors 不存在: {p}")
        return None, []
    sys.path.insert(0, str(ROOT))
    from rd_workshop.normalize_factors import load_and_normalize

    df = load_and_normalize(p)
    cols = [c for c in df.columns if c not in ("date", "symbol")]
    print(f"  额外因子: {len(cols)} 列 | rows={len(df)} | from {p}")
    return df, cols


def main():
    import argparse

    ap = argparse.ArgumentParser(description="Train V2.5 (production default; workshop via --model-dir)")
    ap.add_argument(
        "--model-dir",
        default="",
        help="output model dir (default: models/ or ALPHAPILOT_MODEL_DIR)",
    )
    ap.add_argument(
        "--extra-factors",
        default="",
        help="RD-Workshop normalized factor parquet/csv (date,symbol,rd_*)",
    )
    ap.add_argument(
        "--opt-only",
        action="store_true",
        help="only train v25_opt (skip base A/B; for candidate runs)",
    )
    ap.add_argument(
        "--max-stocks",
        type=int,
        default=0,
        help="limit stocks for smoke tests (0=all)",
    )
    args = ap.parse_args()

    global MODEL_DIR
    if args.model_dir:
        MODEL_DIR = Path(args.model_dir)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    # best_tech_params 仍从生产 models/ 读（只读 Data Support）
    prod_models = ROOT / "models"
    if not (MODEL_DIR / "best_tech_params.json").exists() and (prod_models / "best_tech_params.json").exists():
        import shutil

        shutil.copy2(prod_models / "best_tech_params.json", MODEL_DIR / "best_tech_params.json")

    extra_df, extra_cols = _load_extra_factors(args.extra_factors or os.environ.get("ALPHAPILOT_EXTRA_FACTORS"))

    print("=== AlphaPilot V2.5 A/B 训练 (V3 全特征接线版) ===")
    print(f"MODEL_DIR={MODEL_DIR}")
    print(f"最优技术参数: {json.dumps(BEST, ensure_ascii=False)}")
    t0 = time.time()

    fund_flow, margin, event, fundamentals, lhb_hist = load_v3_side_data()

    stocks = get_stock_list()
    symbols = stocks["symbol"].tolist()
    if args.max_stocks and args.max_stocks > 0:
        symbols = symbols[: args.max_stocks]
        print(f"⚠️ smoke: max-stocks={args.max_stocks}")
    print(f"全市场: {len(symbols)} 只 | 筹码快照: {len(CHIP)} 只 | 龙虎榜: {len(lhb_hist)} 只")
    coverage = report_data_coverage(symbols, fund_flow, margin, event, fundamentals, lhb_hist)

    kline_cache = {}
    kf = Path("data/kline_cache/kline_all.parquet")
    if kf.exists():
        kdf = pd.read_parquet(kf)
        for sym, sdf in kdf.groupby("symbol"):
            sdf = sdf.sort_values("date").reset_index(drop=True)
            if len(sdf) >= 120:
                kline_cache[bare_code(sym)] = sdf
                kline_cache[sym] = sdf
        print(f"K线缓存: {len(kline_cache)} 条索引")

    base_cols = None
    tech_cols = tech_col_names()
    rows_base, rows_opt, labels = [], [], []
    skipped = 0
    hit = {"fund_flow": 0, "margin": 0, "event": 0, "fundamental": 0, "used": 0}
    flow_nz, margin_nz, event_nz = [], [], []

    for si, sym in enumerate(symbols):
        try:
            code = bare_code(sym)
            kl = kline_cache.get(code)
            if kl is None:
                kl = kline_cache.get(sym)
            if kl is None or len(kl) < 120:
                skipped += 1
                continue
            kl = kl.copy()
            kl["date"] = kl["date"].astype(str)
            kl = kl.tail(180).reset_index(drop=True)

            fh = fund_flow.get(code)
            md = margin.get(code)
            ev = event.get(code)
            fu = fundamentals.get(code)

            if fh:
                hit["fund_flow"] += 1
            if md:
                hit["margin"] += 1
            if ev:
                hit["event"] += 1
            if fu:
                hit["fundamental"] += 1

            # ★ 关键修复：把 V3 侧车数据传入特征管线
            feats = ft.build_full_features_v2(
                kl,
                fundamentals=fu,
                fund_hist=fh,
                margin_data=md,
                event_data=ev,
                has_forecast=bool(ev and ev.get("has_forecast")),
                yjyg_max_change=float((ev or {}).get("yjyg_max_change", 0) or 0),
            )
            if feats is None or len(feats) < 30:
                skipped += 1
                continue
            feats = apply_lhb_dates(feats, lhb_hist.get(code))
            feats = merge_chip(feats, code)

            if base_cols is None:
                base_cols = [c for c in feats.columns if c not in RAW]
                print(f"动态基础特征维度: {len(base_cols)}")
                for c in FLOW_COLS + MARGIN_COLS + EVENT_COLS + CHIP_FACTORS:
                    mark = "✓" if c in base_cols or c in CHIP_FACTORS else "✗"
                    # CHIP_FACTORS 在 compute_chip_factors 后才出现
                    print(f"  [{mark}] {c}")

            flow_nz.append(nonzero_rate(feats, FLOW_COLS))
            margin_nz.append(nonzero_rate(feats, MARGIN_COLS))
            event_nz.append(nonzero_rate(feats, EVENT_COLS))

            feats = compute_optimized_tech(feats)
            derived = derive_factors(feats)
            full = pd.concat([feats, derived], axis=1)
            full = full.loc[:, ~full.columns.duplicated()]
            full = compute_chip_factors(full)
            if extra_cols:
                from rd_workshop.normalize_factors import merge_extra_factors

                full = merge_extra_factors(full, code, extra_df, extra_cols)
            # 固定列集：缺列补 0，避免不同股票列数不一致导致 vstack 失败
            needed = list(dict.fromkeys(base_cols + DERIVED_COLS + CHIP_FACTORS + tech_cols + extra_cols))
            for c in needed:
                if c not in full.columns:
                    full[c] = 0.0
                else:
                    full[c] = full[c].fillna(0)
            future_ret = full["close"].shift(-FORWARD_DAYS) / full["close"] - 1
            full["label"] = (future_ret > THRESHOLD).astype(float)
            full = full.replace([np.inf, -np.inf], np.nan)
            base_set = list(dict.fromkeys(base_cols + DERIVED_COLS + CHIP_FACTORS))
            opt_set = list(dict.fromkeys(base_cols + DERIVED_COLS + CHIP_FACTORS + tech_cols + extra_cols))
            vb = full.dropna(subset=["label"] + base_set)
            vo = full.dropna(subset=["label"] + opt_set)
            if len(vb) < 10 or len(vo) < 10:
                skipped += 1
                continue
            rows_base.append(vb[base_set].astype(float))
            rows_opt.append(vo[opt_set].astype(float))
            labels.append(vo["label"].values)
            hit["used"] += 1
        except Exception:
            skipped += 1
            continue
        del kl, feats, derived, full, vb, vo, future_ret, base_set, opt_set
        if (si + 1) % 300 == 0:
            print(
                f"  处理 {si+1}/{len(symbols)} | 样本 {sum(len(l) for l in labels)} | "
                f"跳过 {skipped} | 资金流命中 {hit['fund_flow']} | 两融 {hit['margin']} | 预告 {hit['event']}"
            )
        gc.collect()

    if not rows_base:
        print('❌ 无有效样本')
        sys.exit(1)

    used = max(hit["used"], 1)
    print("\n=== 实际进入训练的通道命中 ===")
    print(f"  使用股票: {hit['used']} | 资金流 {hit['fund_flow']/used:.1%} | "
          f"两融 {hit['margin']/used:.1%} | 预告 {hit['event']/used:.1%} | 基本面 {hit['fundamental']/used:.1%}")
    print(f"  特征非零率(股票均值): 资金流 {np.mean(flow_nz):.1%} | "
          f"两融 {np.mean(margin_nz):.1%} | 预告 {np.mean(event_nz):.1%}")

    y = np.concatenate(labels, axis=0)
    X_base = pd.DataFrame(np.vstack([r.values for r in rows_base]), columns=rows_base[0].columns)
    X_opt = pd.DataFrame(np.vstack([r.values for r in rows_opt]), columns=rows_opt[0].columns)
    print(f"\n总样本: {len(y)} | 正例: {y.mean():.2%}")
    print(f"V25_base 特征: {X_base.shape[1]}维 | V25_opt 特征: {X_opt.shape[1]}维 "
          f"(技术块 +{X_opt.shape[1]-X_base.shape[1]})")

    print("\n🚀 训练 V25_base (不含技术块) ..." if not args.opt_only else "\n⏭ 跳过 V25_base (--opt-only)")
    if args.opt_only:
        auc_b, aucs_b, fb = 0.0, [], list(X_base.columns)
    else:
        auc_b, aucs_b, fb = train_ensemble(X_base, y, "v25_base")
    print("\n🚀 训练 V25_opt (含最优技术块" + ("+RD因子" if extra_cols else "") + ") ...")
    auc_o, aucs_o, fo = train_ensemble(X_opt, y, "v25_opt")
    print(f"\n{'='*55}")
    print(f"V25_base AUC = {auc_b:.4f}")
    print(f"V25_opt  AUC = {auc_o:.4f}")
    print(f"技术块边际增益 = {auc_o - auc_b:+.4f}")
    print(f"{'='*55}")

    # 候选跑：把归一化因子表拷进 MODEL_DIR，供 scorer / OOS 只读
    extra_factors_rel = None
    if extra_df is not None and extra_cols:
        dest = MODEL_DIR / "extra_factors.parquet"
        extra_df.to_parquet(dest, index=False)
        extra_factors_rel = str(dest)

    meta = {
        "version": "v25",
        "trained_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "best_tech_params": BEST,
        "model_dir": str(MODEL_DIR),
        "workshop_candidate": str(MODEL_DIR.resolve()) != str((ROOT / "models").resolve()),
        "extra_factor_columns": extra_cols,
        "extra_factors_path": extra_factors_rel,
        "ab_test": {
            "v25_base_auc": round(auc_b, 4),
            "v25_base_model_aucs": [round(a, 4) for a in aucs_b],
            "v25_opt_auc": round(auc_o, 4),
            "v25_opt_model_aucs": [round(a, 4) for a in aucs_o],
            "tech_block_marginal_gain": round(auc_o - auc_b, 4),
            "v25_base_dim": int(X_base.shape[1]),
            "v25_opt_dim": int(X_opt.shape[1]),
            "opt_only": bool(args.opt_only),
        },
        "features": {
            "base_count": len(base_cols),
            "base_columns": base_cols,
            "derived": DERIVED_COLS,
            "chip_factors": CHIP_FACTORS,
            "tech_optimized": tech_cols,
            "extra_rd_factors": extra_cols,
            "v3_wired": True,
            "flow_cols": FLOW_COLS,
            "margin_cols": MARGIN_COLS,
            "event_cols": EVENT_COLS,
        },
        "data_coverage": coverage,
        "train_hits": {
            "used_stocks": hit["used"],
            "fund_flow_hit_rate": round(hit["fund_flow"] / used, 4),
            "margin_hit_rate": round(hit["margin"] / used, 4),
            "event_hit_rate": round(hit["event"] / used, 4),
            "fundamental_hit_rate": round(hit["fundamental"] / used, 4),
            "flow_nonzero_mean": round(float(np.mean(flow_nz)), 4) if flow_nz else 0.0,
            "margin_nonzero_mean": round(float(np.mean(margin_nz)), 4) if margin_nz else 0.0,
            "event_nonzero_mean": round(float(np.mean(event_nz)), 4) if event_nz else 0.0,
        },
        "training": {
            "n_samples": int(len(y)),
            "positive_rate": float(y.mean()),
            "forward_days": FORWARD_DAYS,
            "threshold": THRESHOLD,
        },
        "model_config": {
            "n_models": N_MODELS,
            "num_boost_round": N_BOOST_ROUND,
            "early_stopping": EARLY_STOPPING,
            "scale_pos_weight": 8.0,
        },
        "note": (
            "V2.5 A/B + V3 wiring: build_full_features_v2 now receives "
            "fund_hist/margin_data/event_data/fundamentals. "
            "OOS IC gate still required before production switch. "
            "Workshop candidates must NOT overwrite production models/ without Human Review."
        ),
        "promotion": {
            "auto_install_forbidden": True,
            "requires": ["backtest_validation", "human_review", "compare_production_model"],
        },
    }
    (MODEL_DIR / "v25_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(f"✅ 元数据: {MODEL_DIR / 'v25_meta.json'} | 总耗时 {int(time.time()-t0)}s")


if __name__ == "__main__":
    main()
