#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# VM2.5 scorer aligned with train_v25 V3 feature wiring.
from __future__ import annotations
import json, os
from pathlib import Path
import numpy as np
import pandas as pd
import xgboost as xgb

ROOT = Path(os.environ.get("ALPHAPILOT_ROOT") or "/home/ubuntu/alphapilot")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
import features_v2 as ft
from auto_factor_engine import derive_factors

MACD_PAIRS = [(6, 13), (8, 17), (12, 26)]


def _model_dir() -> Path:
    """生产默认 models/；候选经 ALPHAPILOT_MODEL_DIR 指向车间目录。"""
    return Path(os.environ.get("ALPHAPILOT_MODEL_DIR") or (ROOT / "models"))

def _bare(sym):
    s = str(sym).strip()
    if "." in s:
        s = s.split(".")[0]
    return s.zfill(6)[-6:]

def _load_json(path, default=None):
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
        i = raw.rfind("},")
        if i > 0:
            try:
                return json.loads(raw[: i + 1] + "}")
            except Exception:
                pass
        return default

class VM25Scorer:
    def __init__(self, prefer="opt"):
        self.models = []
        self.feature_names = []
        self.meta = {}
        self.prefer = prefer
        self.fund_flow = {}
        self.margin = {}
        self.event = {}
        self.fundamentals = {}
        self.chip = {}
        self.lhb_hist = {}
        self.best = {}
        self._side_loaded = False
        self.extra_factors = None
        self.extra_factor_cols = []

    def load(self) -> bool:
        mdir = _model_dir()
        self.meta = _load_json(mdir / "v25_meta.json", {})
        prefixes = ["v25_opt", "v25_base"] if self.prefer == "opt" else ["v25_base", "v25_opt"]
        for pref in prefixes:
            models = []
            for i in range(1, 4):
                p = mdir / f"{pref}_ensemble_{i}.ubj"
                if p.exists():
                    m = xgb.Booster()
                    m.load_model(str(p))
                    models.append(m)
            if len(models) >= 2:
                self.models = models
                self.feature_names = list(models[0].feature_names or [])
                print(f"  VM2.5 loaded: {pref} x{len(models)} feats={len(self.feature_names)} dir={mdir}")
                self._load_side()
                self._load_best_params()
                self._load_extra_factors()
                return True
        print(f"  VM2.5 model missing under {mdir} — run train_v25.py first")
        return False

    def _load_side(self):
        if self._side_loaded:
            return
        ff = _load_json(ROOT / "data" / "fund_flow_history.json", {})
        self.fund_flow = {_bare(k): v for k, v in ff.items() if isinstance(v, dict)}
        mg = _load_json(ROOT / "data" / "margin_data.json", {})
        self.margin = {_bare(k): v for k, v in mg.items() if isinstance(v, dict)}
        ev = _load_json(ROOT / "data" / "event_forecast.json", {})
        self.event = {_bare(k): v for k, v in ev.items() if isinstance(v, dict)}
        for fp in (ROOT / "fundamental_data.json", ROOT / "data" / "fundamental_data.json"):
            if fp.exists():
                fu = _load_json(fp, {})
                self.fundamentals = {_bare(k): v for k, v in fu.items() if isinstance(v, dict)}
                break
        for cp in (ROOT / "chip_data_all.json", ROOT / "data" / "chip_data_all.json"):
            if cp.exists():
                self.chip = _load_json(cp, {})
                break
        lh = _load_json(ROOT / "data" / "lhb_history.json", {})
        self.lhb_hist = {_bare(k): v for k, v in lh.items() if isinstance(v, dict)}
        self._side_loaded = True

    def _load_best_params(self):
        # 优先候选目录，回落到生产 models（只读 Data Support）
        for p in (_model_dir() / "best_tech_params.json", ROOT / "models" / "best_tech_params.json"):
            d = _load_json(p, {})
            if d:
                break
        else:
            d = {}
        bp = dict(d.get("best_params", {}))
        if "macd_pair" in bp:
            bp["macd_f"], bp["macd_s"] = MACD_PAIRS[bp["macd_pair"]]
        if not bp:
            bp = {"use_ma": True, "use_macd": True, "use_rsi": False, "ma_s": 5, "ma_l": 30, "ma_vl": 60, "macd_pair": 0, "macd_sig": 5, "macd_f": 6, "macd_s": 13}
        self.best = bp

    def _load_extra_factors(self):
        self.extra_factors = None
        self.extra_factor_cols = list(self.meta.get("extra_factor_columns") or [])
        path = (
            os.environ.get("ALPHAPILOT_EXTRA_FACTORS")
            or self.meta.get("extra_factors_path")
            or ""
        )
        if not path and (_model_dir() / "extra_factors.parquet").exists():
            path = str(_model_dir() / "extra_factors.parquet")
        if not path:
            return
        try:
            from rd_workshop.normalize_factors import load_and_normalize

            df = load_and_normalize(Path(path))
            cols = [c for c in df.columns if c not in ("date", "symbol")]
            if self.extra_factor_cols:
                cols = [c for c in self.extra_factor_cols if c in cols] or cols
            self.extra_factors = df
            self.extra_factor_cols = cols
            print(f"  extra factors loaded: {len(cols)} cols from {path}")
        except Exception as e:
            print(f"  extra factors skipped: {e}")

    def _merge_chip(self, feats, code):
        c = None
        for k, v in self.chip.items():
            if _bare(k) == code:
                c = v
                break
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

    def _chip_factors(self, df):
        df = df.copy()
        if "chip_concentration" in df.columns:
            conc = df["chip_concentration"].astype(float)
            df["z_chip_concentration"] = (conc / 20.0).fillna(0.0)
        else:
            df["z_chip_concentration"] = 0.0
        df["chip_penetration_3d"] = (
            df["chip_penetration"].astype(float).rolling(3, min_periods=1).mean().fillna(0)
            if "chip_penetration" in df.columns
            else 0.0
        )
        df["avg_cost_shift_10d"] = (
            df["avg_cost_shift_5d"].astype(float).rolling(2, min_periods=1).sum().fillna(0)
            if "avg_cost_shift_5d" in df.columns
            else 0.0
        )
        df["chip_profit_trend"] = (
            df["chip_profit_rate"].astype(float).diff(3).fillna(0)
            if "chip_profit_rate" in df.columns
            else 0.0
        )
        df["chip_distribution_width"] = (
            df["chip_concentration"].astype(float).fillna(0)
            if "chip_concentration" in df.columns
            else 0.0
        )
        if "chip_concentration" in df.columns and "chip_concentration_70" in df.columns:
            df["chip_distribution_shape"] = (
                df["chip_concentration"].astype(float)
                / (df["chip_concentration_70"].astype(float) + 1e-8)
            ).fillna(1.0)
        else:
            df["chip_distribution_shape"] = 1.0
        return df

    def _opt_tech(self, df):
        if not any(str(c).startswith("opt_") for c in self.feature_names):
            return df
        df = df.sort_values("date").copy() if "date" in df.columns else df.copy()
        close = df["close"]
        p = self.best
        if p.get("use_ma", True):
            ms, ml, mv = p.get("ma_s", 5), p.get("ma_l", 30), p.get("ma_vl", 60)
            ma_s = close.rolling(ms, min_periods=ms).mean()
            ma_l = close.rolling(ml, min_periods=ml).mean()
            ma_vl = close.rolling(mv, min_periods=mv).mean()
            df["opt_ma_price_above_long"] = (close > ma_l).astype(float)
            df["opt_ma_short_above_long"] = (ma_s > ma_l).astype(float)
            df["opt_ma_mid_above_vlong"] = (ma_l > ma_vl).astype(float)
            df["opt_ma_long_slope"] = ma_l.pct_change(5)
            df["opt_ma_dist_long"] = (close - ma_l) / ma_l
        if p.get("use_macd", True):
            f, s, sig = p.get("macd_f", 6), p.get("macd_s", 13), p.get("macd_sig", 5)
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
        return df

    def build_features(self, kline_df, symbol):
        code = _bare(symbol)
        kl = kline_df.copy()
        if "date" in kl.columns:
            kl["date"] = kl["date"].astype(str)
        feats = ft.build_full_features_v2(
            kl,
            fundamentals=self.fundamentals.get(code),
            fund_hist=self.fund_flow.get(code),
            margin_data=self.margin.get(code),
            event_data=self.event.get(code),
            has_forecast=bool(self.event.get(code) and self.event.get(code).get("has_forecast")),
            yjyg_max_change=float((self.event.get(code) or {}).get("yjyg_max_change", 0) or 0),
        )
        if feats is None or len(feats) < 30:
            return None
        # 龙虎榜按日对齐
        lhb_rec = self.lhb_hist.get(code)
        if lhb_rec and "date" in feats.columns:
            dates_map = lhb_rec.get("dates") or {}
            if dates_map:
                dser = feats["date"].astype(str).str[:10]
                feats = feats.copy()
                feats["has_lhb"] = dser.map(lambda d: 1.0 if d in dates_map else 0.0).astype(float)
                feats["buy_inst_count"] = dser.map(
                    lambda d: float(dates_map.get(d, 0) or 0)
                ).astype(float)
        feats = self._merge_chip(feats, code)
        feats = self._opt_tech(feats)
        derived = derive_factors(feats)
        full = pd.concat([feats, derived], axis=1)
        full = full.loc[:, ~full.columns.duplicated()]
        full = self._chip_factors(full)
        if self.extra_factor_cols:
            from rd_workshop.normalize_factors import merge_extra_factors

            full = merge_extra_factors(full, code, self.extra_factors, self.extra_factor_cols)
        return full.replace([np.inf, -np.inf], np.nan).fillna(0)

    def get_factor_vector(self, kline_df, symbol):
        """Build features and return the latest row as a {feature_name: value} dict.
        Used by ICIR scorer for cross-sectional z-scoring (no XGBoost inference)."""
        full = self.build_features(kline_df, symbol)
        if full is None or len(full) < 1:
            return None
        row = full.iloc[-1]
        return {c: float(row.get(c, 0.0) or 0.0) for c in self.feature_names}

    def score(self, kline_df, symbol, sector_heat=0.0):
        if not self.models and not self.load():
            return {"error": "model_not_loaded"}
        full = self.build_features(kline_df, symbol)
        if full is None:
            return {"error": "insufficient_data"}
        row = full.iloc[-1]
        vec = np.array([[float(row.get(c, 0.0)) for c in self.feature_names]], dtype=float)
        dm = xgb.DMatrix(vec, feature_names=self.feature_names)
        proba = float(np.mean([m.predict(dm)[0] for m in self.models]))
        close = float(kline_df.iloc[-1]["close"])
        final = proba * 0.8 + float(sector_heat) * 0.2
        # ATR 目标/止损相对同一 close，保证 止损 < 买入 < 目标
        try:
            atr = float((kline_df["high"] - kline_df["low"]).rolling(14).mean().iloc[-1])
        except Exception:
            atr = 0.0
        if close > 0 and atr > 0:
            t_pct = max(0.03, min(0.12, 1.5 * atr / close))
            s_pct = min(max(1.5 * atr / close, 0.02), 0.07)
        else:
            t_pct, s_pct = 0.04, 0.03
        target_price = round(close * (1.0 + t_pct), 2)
        stop_price = round(close * (1.0 - s_pct), 2)
        if target_price <= close:
            target_price = round(close * 1.04, 2)
        if stop_price >= close:
            stop_price = round(close * 0.97, 2)
        return {
            "score": round(final, 4),
            "lgb_score": round(proba, 4),
            "ml_score": round(proba, 4),
            "sector_heat": round(float(sector_heat), 4),
            "buy_price": close,
            "target_price": target_price,
            "stop_price": stop_price,
            "model": "vm25",
            "n_features": len(self.feature_names),
        }

scorer = VM25Scorer(prefer="opt")