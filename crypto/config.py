"""Crypto quant configuration — Binance perpetual paper trading."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ─── Trading pairs & timeframes ───
SYMBOLS = [
    # Majors
    "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "XRP/USDT:USDT", "BNB/USDT:USDT",
    # High-frequency alt picks
    "DOGE/USDT:USDT", "LINK/USDT:USDT", "ADA/USDT:USDT", "AVAX/USDT:USDT", "LTC/USDT:USDT",
    # Diversification picks (deep liquidity, low correlation)
    "SUI/USDT:USDT", "1000PEPE/USDT:USDT", "TON/USDT:USDT", "DOT/USDT:USDT", "NEAR/USDT:USDT",
    # Wave-2 additions (2026-08-10): liquid majors with strong perp volume
    "UNI/USDT:USDT", "XLM/USDT:USDT", "ATOM/USDT:USDT", "TRX/USDT:USDT", "ETC/USDT:USDT",
    "APT/USDT:USDT", "ARB/USDT:USDT", "INJ/USDT:USDT", "FIL/USDT:USDT", "WLD/USDT:USDT",
]
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
USE_SHORT_MODEL = True  # short AUC 0.58 → viable; dual-direction validated

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
    max_hold_bars: int = 24        # max 24 bars on 2h = 48h (win-rate study: 18 bars cut winners early, 24 balances hold&turnover)

EXIT = ExitConfig()

# ─── Paper trading ───
@dataclass
class PaperConfig:
    initial_capital: float = 1000.0  # USDT
    max_positions: int = 3           # 3 batches per symbol (more data for analysis)
    per_trade_risk: float = 0.10    # 10% of capital per signal (fallback when ATR sizing off)
    min_signal_score: float = 0.45  # long entry threshold
    min_signal_score_short: float = 0.50  # short entry threshold (higher — short AUC is noisier)
    # ATR-based dynamic sizing (Turtle-inspired)
    use_atr_sizing: bool = True     # enable ATR-adaptive position sizing
    atr_risk_pct: float = 0.008     # risk 0.8% of capital per ATR unit (sizing study: ret +6214%, DD -28%, Sharpe 2.07 — sweet spot)
    atr_max_batch_pct: float = 0.40 # cap single batch at 40% of capital (was 30%)
    global_max_position_pct: float = 0.80  # hard cap on total open exposure (sum of batch_size) — never over-leverage

PAPER = PaperConfig()

# ─── Signal frequency (higher = more data) ───
SIGNAL_COOLDOWN_BARS = 4   # min bars between entries per symbol (2h × 4 = 8h)

# ─── SMC Layer ① selective trend gate (dynamic, no static symbol labels) ───
# Backtest-validated (bt_smc_gate.py, full history, 4 arms):
#   nogate     9462 trades  70.9% win  +8874%
#   smc_dynamic 5929 trades 73.2% win  +2768%  (blanket with-trend only)
#   selective  7744 trades  73.8% win  +7296%  ← BEST (with-trend normal
#              threshold; counter-trend needs sig>=0.65; chop blocks all)
#   static     8709 trades  69.5% win  +3784%  (static per-symbol bans)
# Selective keeps the high-signal reversal trades while cutting weak
# counter-trend leaks (NEAR-long & ADA-short band 50-60 win~33%).
SMC_ENABLED = True
SMC_COUNTER_TREND_MIN_SIGNAL = 0.65

# ─── Slippage (per-side fractional cost) ───
# Liquidity tiers: BTC/ETH deepest, small alts thinner.
# Stress test: 0.1% costs erase ~77% of gross return; 0.5% kills the strategy.
SLIPPAGE_DEFAULT = 0.001  # 0.1% per side (fallback)
SLIPPAGE_BY_SYMBOL = {
    "BTC/USDT:USDT": 0.0005, "ETH/USDT:USDT": 0.0005,   # deepest books
    "BNB/USDT:USDT": 0.001, "SOL/USDT:USDT": 0.001, "XRP/USDT:USDT": 0.001,
    "LTC/USDT:USDT": 0.0015, "DOGE/USDT:USDT": 0.0015, "ADA/USDT:USDT": 0.0015,
    "LINK/USDT:USDT": 0.002, "AVAX/USDT:USDT": 0.002,    # thinnest books
    "SUI/USDT:USDT": 0.0015, "TON/USDT:USDT": 0.0015, "DOT/USDT:USDT": 0.0015,
    "NEAR/USDT:USDT": 0.002, "1000PEPE/USDT:USDT": 0.002,   # meme / thinner books
    # Wave-2 additions: same liquidity tiers
    "UNI/USDT:USDT": 0.0015, "XLM/USDT:USDT": 0.0015, "ATOM/USDT:USDT": 0.0015,
    "TRX/USDT:USDT": 0.0015, "ETC/USDT:USDT": 0.002, "APT/USDT:USDT": 0.002,
    "ARB/USDT:USDT": 0.002, "INJ/USDT:USDT": 0.002, "FIL/USDT:USDT": 0.002,
    "WLD/USDT:USDT": 0.002,
}

# ─── Execution model ───
# Mixed maker/taker: entries & take-profit use post-only limit orders (maker),
# stop-loss uses market orders (taker). Binance USDT-M perp: maker 0.02%, taker 0.05%.
MAKER_FEE = 0.0002   # 0.02% post-only limit
TAKER_FEE = 0.0005   # 0.05% market order
