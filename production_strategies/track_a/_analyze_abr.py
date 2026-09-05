# -*- coding: utf-8 -*-
"""Analyze ABR discrimination power from the fullchain backtest output."""
import json

import numpy as np

d = json.load(open(
    r"C:\Users\elvisq\Projects\alphapilot\output\bt_abr_gate_fullchain.json",
    encoding="utf-8"))
trades = d["trades"]["P2_base"]
trig = [t for t in trades if t["trigger"]]
nont = [t for t in trades if not t["trigger"]]
print("base triggered:", len(trig), "not:", len(nont))

abrs = [t["abr"] for t in trig if t["abr"] is not None]
print("n with abr:", len(abrs),
      "mean:", round(sum(abrs) / len(abrs), 3),
      "median:", round(float(np.median(abrs)), 3))

arr_a = np.array([t["abr"] for t in trig
                  if t["abr"] is not None and t["ret_next_open"] is not None])
arr_r = np.array([t["ret_next_open"] for t in trig
                  if t["abr"] is not None and t["ret_next_open"] is not None])
pairs = [(t["abr"], t["ret_next_open"], t["ret_day_close"]) for t in trig
         if t["abr"] is not None and t["ret_next_open"] is not None
         and t["ret_day_close"] is not None]
if len(pairs) > 2:
    A = np.array([p[0] for p in pairs])
    Rn = np.array([p[1] for p in pairs])
    Rd = np.array([p[2] for p in pairs])
    print("corr(abr, ret_next_open):", round(float(np.corrcoef(A, Rn)[0, 1]), 3))
    print("corr(abr, ret_day_close):", round(float(np.corrcoef(A, Rd)[0, 1]), 3))

hi = [t for t in trig if t["abr"] is not None and t["abr"] >= 0.50
      and t["ret_next_open"] is not None]
lo = [t for t in trig if t["abr"] is not None and t["abr"] < 0.50
      and t["ret_next_open"] is not None]
print()
if hi:
    print(f"ABR>=0.50: n={len(hi)} T1_open_mean="
          f"{sum(t['ret_next_open'] for t in hi) / len(hi):.3f}% win="
          f"{100 * sum(1 for t in hi if t['ret_next_open'] > 0) / len(hi):.1f}%")
if lo:
    print(f"ABR<0.50:  n={len(lo)} T1_open_mean="
          f"{sum(t['ret_next_open'] for t in lo) / len(lo):.3f}% win="
          f"{100 * sum(1 for t in lo if t['ret_next_open'] > 0) / len(lo):.1f}%")

# quantile buckets
arr_a2 = np.array([t["abr"] for t in trig if t["abr"] is not None])
arr_r2 = np.array([t["ret_next_open"] for t in trig
                   if t["abr"] is not None and t["ret_next_open"] is not None])
q = np.quantile(arr_a2, [0, 0.25, 0.5, 0.75, 1.0])
print("\nabr quartiles:", np.round(q, 3))
for i in range(4):
    lo_q, hi_q = q[i], q[i + 1]
    sel = [(t["ret_next_open"], t["ret_day_close"]) for t in trig
           if t["abr"] is not None and lo_q <= t["abr"] < hi_q
           and t["ret_next_open"] is not None]
    sel_d = [t["ret_day_close"] for t in trig
             if t["abr"] is not None and lo_q <= t["abr"] < hi_q
             and t["ret_day_close"] is not None]
    if sel:
        rn = np.array([s[0] for s in sel])
        rd = np.array(sel_d)
        print(f"  Q{i+1} abr[{lo_q:.2f},{hi_q:.2f}): n={len(rn)} "
              f"T1_open={rn.mean():.3f}% win={100*(rn > 0).mean():.1f}% "
              f"T_day={rd.mean():.3f}% win={100*(rd > 0).mean():.1f}%")
