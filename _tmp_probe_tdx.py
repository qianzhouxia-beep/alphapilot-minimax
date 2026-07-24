#!/usr/bin/env python3
"""Probe existing TDX fundflow helpers on Shanghai."""
import importlib.util
import json
import os
import sys
import time

os.chdir("/home/ubuntu/alphapilot")
sys.path.insert(0, "/home/ubuntu/alphapilot")

print("=== probe TDX fundflow ===")

# 1) build_fundflow_tdx_server helpers
try:
    import build_fundflow_tdx_server as tdx
    print("build_fundflow_tdx_server attrs:", [a for a in dir(tdx) if not a.startswith("_")][:40])
except Exception as e:
    print("import build_fundflow_tdx_server fail:", e)

# 2) try common fetch functions
for mod_name in [
    "build_fundflow_tdx_server",
    "batch_tdx_fundflow_auto",
    "fund_flow_fetcher",
    "fundflow_fetcher_v4",
    "fundflow_fetcher_v5",
    "fund_flow_fetcher_v2",
]:
    try:
        m = __import__(mod_name)
    except Exception as e:
        print(f"skip {mod_name}: {e}")
        continue
    funcs = [a for a in dir(m) if "fund" in a.lower() or "tdx" in a.lower() or a.startswith("get_") or a.startswith("fetch")]
    print(mod_name, "funcs", funcs[:30])

# 3) direct call patterns from build script
try:
    from build_fundflow_tdx_server import fetch_one, get_fund_flow, pull_symbol
except Exception:
    fetch_one = get_fund_flow = pull_symbol = None

for name, fn in [("fetch_one", fetch_one), ("get_fund_flow", get_fund_flow), ("pull_symbol", pull_symbol)]:
    if not callable(fn):
        continue
    t0 = time.time()
    try:
        r = fn("600519")
        print(name, "type", type(r).__name__, "elapsed", round(time.time() - t0, 2))
        if isinstance(r, dict):
            print("  keys", list(r.keys())[:10], "n", len(r))
            if r:
                k = sorted(r.keys())
                print("  range", k[0], k[-1], "sample", r[k[-1]])
        elif isinstance(r, list):
            print("  n", len(r), "first", r[0] if r else None, "last", r[-1] if r else None)
        else:
            print("  val", str(r)[:200])
    except TypeError:
        try:
            r = fn("sh600519")
            print(name, "sh600519 ok", type(r))
        except Exception as e:
            print(name, "fail", e)
    except Exception as e:
        print(name, "fail", e)
