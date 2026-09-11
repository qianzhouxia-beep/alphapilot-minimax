import os
"""
AlphaPilot V18 Fusion 推理引擎
加载 5 个 XGBoost 模型, 推理时投票平均
支持 V14 和 V18 两种模型版本
"""
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

# V18 Fusion 使用的 30 维特征（22 基础 + 10 因子，去重后）
ALL_FEATURES = list(dict.fromkeys(list(V11_FEATURE_COLUMNS) + [
    "active_buy_ratio", "amt_ma_ratio_ma3", "amt_ma_ratio_std5", "atr_pct",
    "atr_pct_std5", "atr_pct_zscore", "bull_confirmation", "chip_reverse",
    "chip_vol", "conv_div"
]))


class MLScreener:
    """AlphaPilot 短线集成推理引擎"""

    def __init__(self, model_version="v18_fusion_v2"):
        self.models = []
        self.model_loaded = False
        self.model_version = model_version
        self.meta = None

    def load_model(self, version=None) -> bool:
        """加载集成模型
        version: "v14" | "v18_fusion_v2" | "v19_fusion"
        """
        if self.model_loaded:
            return True

        if version:
            self.model_version = version

        if self.model_version == "v14":
            return self._load_v14()
        elif self.model_version in ("v25", "vm25", "vm2.5"):
            return self._load_v25()
        elif self.model_version == "v19_fusion":
            return self._load_v19_fusion()
        else:
            return self._load_v18_fusion()

    def _load_v25(self) -> bool:
        """VM2.5: 经 vm25_scorer 加载 v25_opt (93维 features_v2)"""
        try:
            from vm25_scorer import scorer as vm25
            ok = vm25.load()
            if not ok:
                print(" V25 load failed, fallback v18")
                return self._load_v18_fusion()
            self.models = vm25.models
            self.model_loaded = True
            self.model_version = "v25"
            self._vm25 = vm25
            print(f" V25 loaded via vm25_scorer feats={len(vm25.feature_names)}")
            return True
        except Exception as e:
            print(f" V25 load error: {e}; fallback v18")
            return self._load_v18_fusion()

    def _load_v14(self) -> bool:
        meta_path = MODELS_DIR / "v14_slim_meta.json"
        if not meta_path.exists():
            return self._load_fallback()
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            return self._load_from_meta(meta, "V14")
        except Exception as e:
            print(f" V14 加载失败: {e}")
            return self._load_fallback()

    def _load_v18_fusion(self) -> bool:
        meta_path = MODELS_DIR / "v18_fusion_v2_meta.json"
        if not meta_path.exists():
            print(" 18_fusion_v2 元数据不存在, 回退 V14")
            return self._load_v14()
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            return self._load_from_meta(meta, "V18_fusion_v2")
        except Exception as e:
            print(f" V18_fusion_v2 加载失败: {e}")
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
                print(f"  模型文件不存在: {p}")
        if len(self.models) == 0:
            return self._load_fallback()
        self.model_loaded = True
        self.meta = meta
        print(f"  {label} 加载成功: {len(self.models)} 个模型 (AUC={meta['ensemble_auc']:.4f})")
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

    def _load_fallback(self) -> bool:
        print("  回退到单模型 v11_prod.ubj")
        model_file = MODELS_DIR / "v11_prod.ubj"
        if not model_file.exists():
            print("  无可用模型")
            return False
        try:
            m = xgb.XGBClassifier()
            m.load_model(str(model_file))
            self.models = [m]
            self.model_loaded = True
            print(f"  V11 单模型加载成功")
            return True
        except Exception as e:
            print(f"  模型加载失败: {e}")
            return False

    def score_stock(self, kline_df: pd.DataFrame, symbol: str = "", fundamentals: dict = None,
                    has_forecast: bool = False, yjyg_max_change: float = 0.0,
                    buy_inst_count: int = 0, has_lhb: bool = False,
                    margin_balance: float = 0.0, margin_buy: float = 0.0,
                    sector_heat: float = 0.0) -> dict:
        """对单只股票进行评分"""
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
            # V18 Fusion: 22维 + 衍生因子, 去重后 30 维
            # V19 and V18 use same scoring logic (30-dim, 5 models)
            return self._score_v18(feats, kline_df, sector_heat)
        else:
            # V14: 仅 22 维
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

    def _score_v25(self, kline_df, symbol, sector_heat=0.0):
        """VM2.5 评分: vm25_scorer (93维 features_v2)"""
        try:
            vm25 = getattr(self, "_vm25", None)
            if vm25 is None:
                from vm25_scorer import scorer as vm25
                vm25.load()
            res = vm25.score(kline_df, symbol, sector_heat=sector_heat)
            if isinstance(res, dict) and "score" in res:
                return res
            return {"error": "v25_score_invalid"}
        except Exception as e:
            return {"error": "v25_score_err: " + str(e)}

    def _score_v18(self, feats, kline_df, sector_heat):
        # 1. 计算衍生因子（用全部行，确保 rolling 有意义）
        base = feats[V11_FEATURE_COLUMNS].copy()
        base.columns = [c.strip() for c in base.columns]
        derived = derive_factors(base)
        combined = pd.concat([base, derived], axis=1)
        # 2. 去重列名
        combined = combined.loc[:, ~combined.columns.duplicated()]
        # 3. 取最新一行
        latest = combined.iloc[-1:].copy()
        # 4. 选择 ALL_FEATURES 中存在的列（30 维）
        avail = [c for c in ALL_FEATURES if c in latest.columns]
        if len(avail) < len(ALL_FEATURES):
            # 部分列缺失时用所有可用列
            X = latest[avail].fillna(0).values
        else:
            X = latest[avail].fillna(0).values

        # 5. 集成投票
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

    def search_stocks(self, keyword: str, stock_list: pd.DataFrame) -> pd.DataFrame:
        if stock_list.empty:
            return pd.DataFrame()
        keyword = keyword.strip()
        mask = (
            stock_list["symbol"].str.contains(keyword, na=False) |
            stock_list["name"].str.contains(keyword, na=False)
        )
        return stock_list[mask].head(20)


# 全局实例（默认 V18 Fusion）
screener = MLScreener(model_version="v19_fusion")


if __name__ == "__main__":
    print(f"加载 {screener.model_version} 模型...")
    ok = screener.load_model()
    print(f"加载结果: {'✅' if ok else '❌'}")
    print(f"模型数: {len(screener.models)}")

    def _score_v19(self, feats, kline_df, sector_heat):
        """V19 score: 30 features + derived factors, deduplicated"""
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
