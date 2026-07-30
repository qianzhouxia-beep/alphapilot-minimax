"""Crypto quant configuration — Binance perpetual paper trading."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ─── Trading pairs & timeframes ───
SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "XRP/USDT:USDT", "BNB/USDT:USDT"]
TIMEFRAMES = ["2h", "4h", "1d"]
PRIMARY_TF = "2h"

# ─── Feature & label params ───
LABEL_FORWARD = 2       # 2h × 2 = predict 4h ahead
LABEL_THRESHOLD = 0.01

TECH_LOOKBACK = 60

# ─── Model ───
TRAIN_TEST_SPLIT = 0.2
N_BOOST = 300
EARLY_STOP = 50
SCALE_POS_WEIGHT = 4.0
USE_SHORT_MODEL = False  # short AUC < 0.52 → pure noise

# Best hyperparams from sweep: d=4, lr=0.08, 60 ICIR factors
MODEL_PARAMS = {"max_depth": 4, "learning_rate": 0.08, "subsample": 0.6, "colsample_bytree": 0.6}
ICIR_TOP_K = 60

# ─── Paths ───
DATA_DIR = ROOT / "data" / "crypto"
DATA_DIR.mkdir(parents=True, exist_ok=True)
MODEL_DIR = ROOT / "output" / "crypto"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

HISTORY_PATH = DATA_DIR / "history.parquet"
ICIR_PATH = DATA_DIR / "icir_weights.json"
MODEL_PATH = MODEL_DIR / "model.ubj"
SIGNAL_PATH = MODEL_DIR / "signal.json"

# ─── Exit policy (crypto-tuned) ───
@dataclass
class ExitConfig:
    trail_arm: float = 0.02       # activate trailing at 2% profit (was 3%)
    peel_pullback: float = 0.01    # cut half on 1% peak pullback (was 1.5%)
    hard_stop: float = -0.03       # -3% hard stop (was -8% — crypto is more volatile)
    take_profit: float = 0.03      # full close at 3% TP (was 6%)
    max_hold_bars: int = 24        # max 24 bars on 2h = 48h

EXIT = ExitConfig()

# ─── Paper trading ───
@dataclass
class PaperConfig:
    initial_capital: float = 1000.0  # USDT
    max_positions: int = 2
    per_trade_risk: float = 0.10    # 10% of capital per signal (fallback when ATR sizing off)
    min_signal_score: float = 0.50  # lower threshold for more signals
    # ATR-based dynamic sizing (Turtle-inspired)
    use_atr_sizing: bool = True     # enable ATR-adaptive position sizing
    atr_risk_pct: float = 0.002     # risk 0.2% of capital per ATR unit (normalizes vol)
    atr_max_batch_pct: float = 0.25 # cap single batch at 25% of capital

PAPER = PaperConfig()
