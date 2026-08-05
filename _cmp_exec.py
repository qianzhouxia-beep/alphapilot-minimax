#!/usr/bin/env python3
"""Compare taker-only vs mixed maker/taker execution on server."""
import paramiko, warnings
warnings.filterwarnings("ignore")

conn = paramiko.SSHClient()
conn.set_missing_host_key_policy(paramiko.AutoAddPolicy())
conn.connect("43.156.119.47", username="ubuntu", password="Sef-9i7k]1zjicK6Nv", timeout=30)

script = r"""
import sys, json, warnings
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/ubuntu/alphapilot")

from crypto import config as C
from crypto.features import compute_features, list_factors
from crypto.grid_backtest import grid_backtest

df = pd.read_parquet('/home/ubuntu/alphapilot/data/crypto/history.parquet')
df = compute_features(df, forward=2, threshold=0.01)
all_factors = list_factors()

iw = json.load(open('/home/ubuntu/alphapilot/data/crypto/icir_weights.json'))
ranked = sorted(iw.get('summary', {}).items(), key=lambda x: -x[1]['abs_icir'])
factors = [f[0] for f in ranked if f[0] in df.columns][:C.ICIR_TOP_K]
df = df.dropna(subset=factors)
print(f"df rows: {len(df)}, factors: {len(factors)}")

# Save original fees, then simulate taker by overriding
import crypto.grid_backtest as gb
orig_maker = C.MAKER_FEE
orig_taker = C.TAKER_FEE

print("\n=== MIXED maker/taker (entry+TP maker, SL taker) ===")
r1 = grid_backtest(df, factors=factors, min_score=0.45, min_score_short=0.50,
                   per_signal_risk=0.10, entry_timeframe="2h",
                   use_atr_sizing=True, atr_risk_pct=0.003, atr_max_batch_pct=0.25,
                   max_positions_per_sym=3, cooldown_bars=4)
print(f"ret={r1.total_return:+.2f}%  win={r1.win_rate:.1f}%  maxDD={r1.max_drawdown:.2f}%  fees=${r1.total_fees:.2f}  trades={r1.n_trades}")

print("\n=== TAKER-ONLY (old behavior) ===")
C.MAKER_FEE = C.TAKER_FEE  # force both to taker fee
C.TAKER_FEE = 0.0005
# entry slippage reapplied: use slippage dict
r2 = grid_backtest(df, factors=factors, min_score=0.45, min_score_short=0.50,
                   per_signal_risk=0.10, entry_timeframe="2h",
                   use_atr_sizing=True, atr_risk_pct=0.003, atr_max_batch_pct=0.25,
                   max_positions_per_sym=3, cooldown_bars=4)
print(f"ret={r2.total_return:+.2f}%  win={r2.win_rate:.1f}%  maxDD={r2.max_drawdown:.2f}%  fees=${r2.total_fees:.2f}  trades={r2.n_trades}")

# restore
C.MAKER_FEE = orig_maker
C.TAKER_FEE = orig_taker
"""

sftp = conn.open_sftp()
with sftp.open('/tmp/_cmp_exec.py', 'w') as f:
    f.write(script)
sftp.close()
_, out, err = conn.exec_command("cd /home/ubuntu/alphapilot && python3 /tmp/_cmp_exec.py", timeout=900)
print(out.read().decode("utf-8", errors="replace").strip())
e = err.read().decode("utf-8", errors="replace").strip()
if e:
    print("STDERR:", e[-800:])
conn.close()
