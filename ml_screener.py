import os

import json
import warnings
from pathlib import Path

import xgboost as xgb
import numpy as np
import pandas as pd

from config import MODEL_PATH, MODELS_DIR
from features import V11_FEATURE_COLUMNS, build_full_features
from auto_factor_engine import derive_factors

warnings.filterwarnings("ignore")

# V18 Fusion 浣跨敤鐨?30 缁寸壒寰侊紙22 鍩虹 + 10 鍥犲瓙锛屽幓閲嶅悗锛?
ALL_FEATURES = list(dict.fromkeys(list(V11_FEATURE_COLUMNS) + [
    "active_buy_ratio", "amt_ma_ratio_ma3", "amt_ma_ratio_std5", "atr_pct",
    "atr_pct_std5", "atr_pct_zscore", "bull_confirmation", "chip_reverse",
    "chip_vol", "conv_div"
]))

class MLScreener:
    

    def __init__(self, model_version="v20"):
        self.models = []
        self.model_loaded = False
        self.model_version = model_version
        self.meta = None

    def load_model(self, version=None) -> bool:
        
        if self.model_loaded:
            return True

        if version:
            self.model_version = version

        if self.model_version == "v14":
            return self._load_v14()
        elif self.model_version == "v19_fusion":
            return self._load_v19_fusion()
        elif self.model_version in ("v25", "vm25", "vm2.5"):
            return self._load_v25()
        elif self.model_version == "v20":
            return self._load_v20()
        else:
            return self._load_v18_fusion()

    def _load_v14(self) -> bool:
        meta_path = MODELS_DIR / "v14_slim_meta.json"
        if not meta_path.exists():
            return self._load_fallback()
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            return self._load_from_meta(meta, "V14")
        except Exception as e:
            print("...")
            return self._load_fallback()

    def _load_v18_fusion(self) -> bool:
        meta_path = MODELS_DIR / "v18_fusion_v2_meta.json"
        if not meta_path.exists():
            print("...")
            return self._load_v14()
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            return self._load_from_meta(meta, "V18_fusion_v2")
        except Exception as e:
            print("...")
            return self._load_v14()

    def _load_from_meta(self, meta, label) -> bool:
        model_paths = [m["path"] for m in meta["models"]]
        for p in model_paths:
            pf = Path(p)
            if pf.exists():
                m = xgb.XGBClassifier()
                m.load_model(str(pf))
                self.models.append(m)
            else:
                print("...")
        if len(self.models) == 0:
            return self._load_fallback()
        self.model_loaded = True
        self.meta = meta
        print("...")
        return True

    def _load_v19_fusion(self) -> bool:
        meta_path = MODELS_DIR / "v1.9_meta.json"
        if not meta_path.exists():
            print(" V19 meta not found, fallback to v18")
            return self._load_v18_fusion()
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            model_prefix = str(MODELS_DIR / "v1.9_fusion_ensemble")
            self.models = []
            for i in range(5):
                p = f"{model_prefix}_{i+1}.ubj"
                if os.path.exists(p):
                    m = xgb.XGBClassifier()
                    m.load_model(str(p))
                    self.models.append(m)
            if len(self.models) >= 3:
                self.model_loaded = True
                auc = meta.get("v19_fusion", {}).get("ensemble_auc", "?")
                print(f" V19 Fusion loaded: {len(self.models)} models (AUC={auc})")
                return True
            print(" V19 models insufficient, fallback v18")
            return self._load_v18_fusion()
        except Exception as e:
            print(f" V19 load failed: {e}, fallback v18")
            return self._load_v18_fusion()


    def _load_v25(self) -> bool:
        try:
            from vm25_scorer import scorer as vm25
            ok = vm25.load()
            if not ok:
                print(" V25 load failed, fallback v20")
                return self._load_v20()
            self.models = vm25.models
            self.model_loaded = True
            self.model_version = "v25"
            self._vm25 = vm25
            self.meta = getattr(vm25, "meta", None)
            print(f" V25 loaded via vm25_scorer feats={len(vm25.feature_names)}")
            return True
        except Exception as e:
            print(f" V25 load error: {e}; fallback v20")
            return self._load_v20()

    def _score_v25(self, kline_df, symbol, sector_heat):
        vm = getattr(self, "_vm25", None)
        if vm is None:
            from vm25_scorer import scorer as vm
            vm.load()
            self._vm25 = vm
        return vm.score(kline_df, symbol, sector_heat=sector_heat)

    def _load_v20(self) -> bool:
        if not self.model_loaded and not self.load_model():
            return {"error": "model_not_loaded"}

        feats = build_full_features(
            kline_df, symbol=symbol, fundamentals=fundamentals,
            has_forecast=has_forecast, yjyg_max_change=yjyg_max_change,
            buy_inst_count=buy_inst_count, has_lhb=has_lhb,
            margin_balance=margin_balance, margin_buy=margin_buy,
        )

        if feats.empty or len(feats) < 30:
            return {"error": "insufficient_data"}

        if self.model_version in ("v25", "vm25", "vm2.5"):
            return self._score_v25(kline_df, symbol, sector_heat)
        if self.model_version.startswith("v18") or self.model_version.startswith("v19"):
            # V18 Fusion: 22缁?+ 琛嶇敓鍥犲瓙, 鍘婚噸鍚?30 缁?            # V19 and V18 use same scoring logic (30-dim, 5 models)
            return self._score_v18(feats, kline_df, sector_heat)
        elif self.model_version == "v20":
            return self._score_v20(feats, kline_df, sector_heat)
        else:
            return self._score_v14(feats, kline_df, sector_heat)

    def _score_v14(self, feats, kline_df, sector_heat):
        latest = feats.iloc[-1:][V11_FEATURE_COLUMNS].copy()
        latest = latest.fillna(0)

        probas = [m.predict_proba(latest)[0, 1] for m in self.models]
        proba = float(np.mean(probas))
        score = proba

        latest_close = float(kline_df.iloc[-1]["close"])
        ret_2d = feats["ret_5d"].dropna()
        target_pct = float(ret_2d.quantile(0.7)) if len(ret_2d) > 20 else 0.04
        target_price = round(latest_close * (1 + abs(max(target_pct, 0.04))), 2)
        atr = (kline_df["high"] - kline_df["low"]).rolling(14).mean().iloc[-1]
        stop_loss_pct = min(max(float(atr) / latest_close * 2, 0.02), 0.07)
        stop_price = round(latest_close * (1 - stop_loss_pct), 2)
        final_score = score * 0.8 + sector_heat * 0.2

        return {
            "score": round(float(final_score), 4),
            "lgb_score": round(float(score), 4),
            "sector_heat": round(float(sector_heat), 4),
            "buy_price": latest_close,
            "target_price": target_price,
            "stop_price": stop_price,
            "features": {k: round(float(latest[k].iloc[0]), 4) for k in V11_FEATURE_COLUMNS[:10]},
        }

    def _score_v18(self, feats, kline_df, sector_heat):
        # 1. 璁＄畻琛嶇敓鍥犲瓙锛堢敤鍏ㄩ儴琛岋紝纭繚 rolling 鏈夋剰涔夛級
        base = feats[V11_FEATURE_COLUMNS].copy()
        base.columns = [c.strip() for c in base.columns]
        derived = derive_factors(base)
        combined = pd.concat([base, derived], axis=1)
        # 2. 鍘婚噸鍒楀悕
        combined = combined.loc[:, ~combined.columns.duplicated()]
        latest = combined.iloc[-1:].copy()
        # 4. 閫夋嫨
        avail = [c for c in ALL_FEATURES if c in latest.columns]
        if len(avail) < len(
ALL_FEATURES):
            # 閮ㄥ垎鍒楃己澶辨椂鐢ㄦ墍鏈夊彲鐢ㄥ垪
            X = latest[avail].fillna(0).values
        else:
            X = latest[avail].fillna(0).values

        # 5. 闆嗘垚鎶曠エ
        probas = [m.predict_proba(X)[0, 1] for m in self.models]
        proba = float(np.mean(probas))
        score = proba

        latest_close = float(kline_df.iloc[-1]["close"])
        ret_2d = feats["ret_5d"].dropna()
        target_pct = float(ret_2d.quantile(0.7)) if len(ret_2d) > 20 else 0.04
        target_price = round(latest_close * (1 + abs(max(target_pct, 0.04))), 2)
        atr = (kline_df["high"] - kline_df["low"]).rolling(14).mean().iloc[-1]
        stop_loss_pct = min(max(float(atr) / latest_close * 2, 0.02), 0.07)
        stop_price = round(latest_close * (1 - stop_loss_pct), 2)
        final_score = score * 0.8 + sector_heat * 0.2

        return {
            "score": round(float(final_score), 4),
            "lgb_score": round(float(score), 4),
            "sector_heat": round(float(sector_heat), 4),
            "buy_price": latest_close,
            "target_price": target_price,
            "stop_price": stop_price,
            "features": {k: round(float(latest[k].iloc[0]), 4) for k in list(latest.columns)[:10]},
        }

    def _score_v20(self, feats, kline_df, sector_heat):
        base = feats[V11_FEATURE_COLUMNS].copy()
        base.columns = [c.strip() for c in base.columns]
        from auto_factor_engine import derive_factors
        derived = derive_factors(base)
        combined = pd.concat([base, derived], axis=1)
        combined = combined.loc[:, ~combined.columns.duplicated()]
        latest = combined.iloc[-1:].copy()
        avail = [c for c in ALL_FEATURES if c in latest.columns]
        X = latest[avail].fillna(0).values

        probas = [m.predict_proba(X)[0, 1] for m in self.models]
        proba = float(np.mean(probas))
        score = proba

        latest_close = float(kline_df.iloc[-1]["close"])
        ret_2d = feats["ret_5d"].dropna()
        target_pct = float(ret_2d.quantile(0.7)) if len(ret_2d) > 20 else 0.04
        target_price = round(latest_close * (1 + abs(max(target_pct, 0.04))), 2)
        atr = (kline_df["high"] - kline_df["low"]).rolling(14).mean().iloc[-1]
        stop_loss_pct = min(max(float(atr) / latest_close * 2, 0.02), 0.07)
        stop_price = round(latest_close * (1 - stop_loss_pct), 2)
        final_score = score * 0.8 + sector_heat * 0.2

        return {
            "score": round(float(final_score), 4),
            "lgb_score": round(float(score), 4),
            "sector_heat": round(float(sector_heat), 4),
            "buy_price": latest_close,
            "target_price": target_price,
            "stop_price": stop_price,
            "features": {k: round(float(latest[k].iloc[0]), 4) for k in V11_FEATURE_COLUMNS[:10]},
        }


# Global instance used by recommend.py
screener = MLScreener(model_version="v25")

if __name__ == "__main__":
    print(f"loading {screener.model_version}...")
    ok = screener.load_model()
    print("ok" if ok else "fail", "models", len(screener.models))
