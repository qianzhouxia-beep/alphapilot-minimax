"""PSR / DSR statistical guardrails — Bailey & López de Prado.

The walk-forward AUC floor alone cannot tell whether a *profitable* backtest
is real or luck: with ~20-40 trades, a Sharpe can look great by chance, and
the more strategies/factor-sets we try the more inflated the best one looks.

  PSR (Probabilistic Sharpe Ratio, 2012): P(true Sharpe > benchmark) given the
      observed per-trade return series, accounting for non-normality
      (skewness/kurtosis) and the number of trades n.
  DSR (Deflated Sharpe Ratio, 2014): PSR evaluated against a benchmark
      *inflated by the number of trials N* (expected max Sharpe of N random
      strategies), so multiple-testing luck is priced in.

Both are computed on the per-trade PnL% series of an OOS backtest. With n too
small the estimates are meaningless and the gate rejects (can't validate).
"""
from __future__ import annotations

import math
from datetime import datetime

import numpy as np
from scipy import stats

# Number of strategy/factor variants tried historically (factor groups P0/P1/P2,
# grid vs peel, ATR sizing, entry/exit rule iterations, short-model variants).
DEFAULT_N_TRIALS = 50

# Gate thresholds.
PSR_FLOOR = 0.90      # need >= 90% probability true Sharpe > 0
DSR_FLOOR = 0.85      # need >= 85% probability true Sharpe > max-of-N-trials
MIN_TRADES = 15       # fewer trades than this → statistical tests meaningless

# When True, sg_pipeline hard-gates on PSR/DSR in addition to the WFO AUC
# floor. Keep False until a few retrain cycles establish typical PSR/DSR
# magnitudes, otherwise a low-trade-frequency model would roll back constantly.
ENABLE_STAT_GATE = False

_EULER_MASCHERONI = 0.5772156649015329


def sharpe_stats(returns) -> dict:
    """Per-trade Sharpe, skewness, excess kurtosis from a return series."""
    r = np.asarray(returns, dtype=float)
    r = r[~np.isnan(r)]
    n = int(len(r))
    if n < 3:
        return {"n": n, "sharpe": 0.0, "skew": 0.0, "kurt": 0.0, "std": 0.0, "mean": 0.0}
    mu = float(r.mean())
    sd = float(r.std(ddof=1))
    if sd < 1e-12:
        sd = 1e-12
    sharpe = mu / sd  # per-trade, not annualized
    m2 = float(np.mean((r - mu) ** 2))
    m3 = float(np.mean((r - mu) ** 3))
    m4 = float(np.mean((r - mu) ** 4))
    skew = m3 / (m2 ** 1.5) if m2 > 1e-12 else 0.0
    kurt = m4 / (m2 ** 2) if m2 > 1e-12 else 0.0
    return {"n": n, "sharpe": sharpe, "skew": skew, "kurt": kurt - 3.0,  # excess
            "std": sd, "mean": mu}


def probabilistic_sharpe(sharpe: float, n: int, skew: float, kurt_ex: float,
                         benchmark: float = 0.0) -> float:
    """PSR — Bailey & López de Prado (2012) eq. (14)."""
    if n < 3:
        return 0.5
    denom = math.sqrt(max(1.0 - skew * sharpe + (kurt_ex / 4.0) * sharpe ** 2, 1e-8))
    z = (sharpe - benchmark) * math.sqrt(n - 1) / denom
    return float(stats.norm.cdf(z))


def deflated_sharpe_ratio(returns, n_trials: int = DEFAULT_N_TRIALS) -> dict:
    """DSR — Bailey & López de Prado (2014).

    Returns PSR, DSR, and the deflated benchmark Sharpe.
    """
    st = sharpe_stats(returns)
    n, sharpe, skew, kurt = st["n"], st["sharpe"], st["skew"], st["kurt"]
    if n < 3:
        return {**st, "psr": 0.5, "dsr": 0.5, "benchmark": 0.0, "n_trials": n_trials,
                "note": "insufficient data"}

    # variance of the estimated Sharpe (eq. 11 of the DSR paper)
    var_sr = (1.0 - skew * sharpe + (kurt / 4.0) * sharpe ** 2) / (n - 1)
    sd_sr = math.sqrt(max(var_sr, 1e-12))

    # expected max Sharpe of N_trials independent N(0,1) strategies (eq. 20)
    N = max(n_trials, 2)
    g = _EULER_MASCHERONI
    phi_n = stats.norm.ppf(1.0 - 1.0 / N)
    phi_ne = stats.norm.ppf(1.0 - 1.0 / (N * math.e))
    benchmark = sd_sr * ((1.0 - g) * phi_n + g * phi_ne)

    psr = probabilistic_sharpe(sharpe, n, skew, kurt, benchmark=0.0)
    dsr = probabilistic_sharpe(sharpe, n, skew, kurt, benchmark=benchmark)
    return {**st, "psr": psr, "dsr": dsr, "benchmark": benchmark, "n_trials": N}


def check_stat_guardrail(returns, n_trials: int = DEFAULT_N_TRIALS,
                         psr_floor: float = PSR_FLOOR, dsr_floor: float = DSR_FLOOR) -> dict:
    """Decision from PSR/DSR of a per-trade PnL% series."""
    res = deflated_sharpe_ratio(returns, n_trials)
    n = res["n"]
    if n < MIN_TRADES:
        return {
            "pass": False,
            "decision": "reject",
            "reason": f"too few trades ({n} < {MIN_TRADES})",
            "psr": None, "dsr": None, "psr_floor": psr_floor, "dsr_floor": dsr_floor,
            "n_trials": res["n_trials"], "n_trades": n,
            "sharpe": res["sharpe"], "skew": res["skew"], "kurt": res["kurt"],
            "asof": datetime.now().isoformat(),
        }
    passed = res["psr"] >= psr_floor and res["dsr"] >= dsr_floor
    return {
        "pass": passed,
        "decision": "accept" if passed else "reject",
        "reason": ("psr/dsr above floors" if passed
                   else f"psr={res['psr']:.3f}<{psr_floor} or dsr={res['dsr']:.3f}<{dsr_floor}"),
        "psr": round(res["psr"], 4), "dsr": round(res["dsr"], 4),
        "benchmark": round(res["benchmark"], 4),
        "psr_floor": psr_floor, "dsr_floor": dsr_floor,
        "n_trials": res["n_trials"], "n_trades": n,
        "sharpe": round(res["sharpe"], 4), "skew": round(res["skew"], 4),
        "kurt": round(res["kurt"], 4),
        "asof": datetime.now().isoformat(),
    }


def trades_to_returns(trades) -> np.ndarray:
    """Extract per-trade PnL% array from backtest Trade objects."""
    pnls = [t.pnl_pct for t in trades if t.pnl_pct is not None]
    return np.asarray(pnls, dtype=float)


def print_stat_report(res: dict, label: str = "") -> None:
    """Human-readable stat guardrail output."""
    prefix = f"[{label}] " if label else ""
    if res.get("psr") is None:
        print(f"{prefix}STAT: reject — {res.get('reason')}")
        return
    print(f"{prefix}STAT: sharpe={res['sharpe']:.3f} n={res['n_trades']} "
          f"skew={res['skew']:.2f} kurt={res['kurt']:.2f} | "
          f"PSR={res['psr']:.3f} (floor {res['psr_floor']}) "
          f"DSR={res['dsr']:.3f} (floor {res['dsr_floor']}, trials={res['n_trials']}, "
          f"benchmark={res['benchmark']:.4f}) -> {res['decision']}")
