#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wait for train_v25 to finish, then wire VM2.5 and run V3 pipeline backtest."""
from __future__ import annotations
import json, os, subprocess, sys, time
from pathlib import Path

ROOT = Path("/home/ubuntu/alphapilot")
os.chdir(ROOT)
LOG = ROOT / "post_train_v3.log"

def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def run(cmd):
    log(f"$ {cmd}")
    r = subprocess.run(cmd, shell=True, cwd=str(ROOT))
    log(f"exit={r.returncode}")
    return r.returncode

def train_alive():
    return subprocess.run("pgrep -f 'python3 -u train_v25.py'", shell=True).returncode == 0

def meta_ok():
    p = ROOT / "models" / "v25_meta.json"
    if not p.exists():
        return False, 0, ""
    try:
        m = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return False, 0, ""
    n = int(m.get("training", {}).get("n_samples", 0) or 0)
    at = str(m.get("trained_at", ""))
    wired = bool(m.get("features", {}).get("v3_wired")) or "V3 wiring" in str(m.get("note", ""))
    # accept new train if n_samples large and trained today-ish / v3 wired
    ok = n >= 100000 and (wired or at >= "2026-07-18")
    return ok, n, at

def patch_ml_screener_v25():
    path = ROOT / "ml_screener.py"
    src = path.read_text(encoding="utf-8")
    bak = ROOT / "ml_screener.py.bak_before_v25"
    if not bak.exists():
        bak.write_text(src, encoding="utf-8")
    if "_load_v25" in src and '("v25"' in src:
        log("ml_screener already has v25")
        return True
    needle = 'elif self.model_version == "v20":'
    insert = 'elif self.model_version in ("v25", "vm25", "vm2.5"):\n            return self._load_v25()\n        ' + needle
    if needle in src and "_load_v25" not in src:
        src = src.replace(needle, insert, 1)
    method = '''
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
            print(f" V25 loaded via vm25_scorer feats={len(vm25.feature_names)}")
            return True
        except Exception as e:
            print(f" V25 load error: {e}; fallback v20")
            return self._load_v20()

'''
    if "_load_v25" not in src:
        src = src.replace("    def _load_v20(self)", method + "    def _load_v20(self)", 1)
    if "return self._score_v25" not in src:
        parts = src.split("if feats.empty or len(feats) < 30:")
        if len(parts) >= 2:
            head, rest = parts[0], parts[1]
            sn = 'elif self.model_version == "v20":'
            si = 'elif self.model_version in ("v25", "vm25", "vm2.5"):\n            return self._score_v25(kline_df, symbol, sector_heat)\n        ' + sn
            rest = rest.replace(sn, si, 1)
            src = head + "if feats.empty or len(feats) < 30:" + rest
    score_m = '''
    def _score_v25(self, kline_df, symbol, sector_heat):
        vm = getattr(self, "_vm25", None)
        if vm is None:
            from vm25_scorer import scorer as vm
            vm.load()
            self._vm25 = vm
        return vm.score(kline_df, symbol, sector_heat=sector_heat)

'''
    if "_score_v25" not in src:
        src = src.replace("    def _score_v14(self", score_m + "    def _score_v14(self", 1)
    path.write_text(src, encoding="utf-8")
    r = subprocess.run([sys.executable, "-m", "py_compile", str(path)])
    log(f"ml_screener patch compile={r.returncode}")
    if r.returncode != 0:
        path.write_text(bak.read_text(encoding="utf-8"), encoding="utf-8")
        log("RESTORE ml_screener")
        return False
    return True

def patch_recommend():
    path = ROOT / "recommend.py"
    src = path.read_text(encoding="utf-8")
    bak = ROOT / "recommend.py.bak_before_v25"
    if not bak.exists():
        bak.write_text(src, encoding="utf-8")
    src2 = src.replace('load_model(version="v20")', 'load_model(version="v25")')
    src2 = src2.replace("load_model(version='v20')", "load_model(version='v25')")
    if src2 != src:
        path.write_text(src2, encoding="utf-8")
        log("recommend -> v25")
    else:
        log("recommend already v25 or pattern missing")

def main():
    log("=== post_train_v3 watcher start ===")
    # wait train
    while train_alive():
        ok, n, at = meta_ok()
        log(f"train alive; meta_ok={ok} n_samples={n} trained_at={at}")
        time.sleep(60)
    log("train process ended")
    ok, n, at = meta_ok()
    log(f"final meta_ok={ok} n_samples={n} trained_at={at}")
    if not ok:
        # maybe meta not updated yet; read log tail
        log("train meta not OK — abort backtest")
        sys.exit(2)
    if not Path("vm25_scorer.py").exists() or not Path("backtest_v3_pipeline.py").exists():
        log("missing scorer/backtest scripts")
        sys.exit(3)
    if not patch_ml_screener_v25():
        sys.exit(4)
    patch_recommend()
    rc = run("python3 -u backtest_v3_pipeline.py --start 2026-06-01 --end 2026-07-15 --hold 5 --top-k 20 --stride 1")
    if Path("output/v3_pipeline_backtest.json").exists():
        kpi = json.loads(Path("output/v3_pipeline_backtest.json").read_text(encoding="utf-8")).get("kpi", {})
        log("KPI " + json.dumps(kpi, ensure_ascii=False))
    sys.exit(rc)

if __name__ == "__main__":
    main()