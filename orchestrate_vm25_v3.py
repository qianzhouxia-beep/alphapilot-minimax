#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""等资金流拉完 -> 体检 -> 重训 VM2.5 -> 切 recommend 到 v25 -> V3 管线回测。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/home/ubuntu/alphapilot")
os.chdir(ROOT)
LOG = ROOT / "orchestrate_vm25_v3.log"


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(cmd, timeout=None):
    log(f"$ {cmd}")
    r = subprocess.run(cmd, shell=True, cwd=str(ROOT))
    log(f"exit={r.returncode}")
    return r.returncode


def wait_fundflow(max_wait_s=7200):
    prog = ROOT / "data" / "fund_flow_sina_progress.json"
    t0 = time.time()
    while time.time() - t0 < max_wait_s:
        alive = subprocess.run("pgrep -f pull_fundflow_sina_backup.py", shell=True).returncode == 0
        if prog.exists():
            d = json.loads(prog.read_text(encoding="utf-8"))
            log(f"fundflow progress done={d.get('done')}/{d.get('total')} ok={d.get('ok')} mean_depth={d.get('mean_depth')} alive={alive}")
            if not alive and d.get("done", 0) >= d.get("total", 1) * 0.95:
                return True
            if d.get("mean_depth", 0) >= 100 and d.get("done", 0) >= d.get("total", 1) * 0.98:
                return True
        elif not alive:
            # 可能已完成但 progress 丢了
            log("pull process not alive and no progress file; continue")
            return True
        time.sleep(60)
    log("TIMEOUT waiting fundflow")
    return False


def patch_recommend_to_v25():
    path = ROOT / "recommend.py"
    src = path.read_text(encoding="utf-8")
    bak = ROOT / "recommend.py.bak_before_v25"
    if not bak.exists():
        bak.write_text(src, encoding="utf-8")
    # load_model version
    src2 = src.replace('load_model(version="v20")', 'load_model(version="v25")')
    src2 = src2.replace("load_model(version='v20')", "load_model(version='v25')")
    if src2 != src:
        path.write_text(src2, encoding="utf-8")
        log("recommend.py -> load_model(v25)")
    else:
        log("recommend.py already v25 or pattern not found")


def patch_ml_screener_v25():
    path = ROOT / "ml_screener.py"
    src = path.read_text(encoding="utf-8")
    bak = ROOT / "ml_screener.py.bak_before_v25"
    if not bak.exists():
        bak.write_text(src, encoding="utf-8")
    if "_load_v25" in src and '== "v25"' in src:
        log("ml_screener already has v25")
        return
    # insert branch in load_model
    needle = 'elif self.model_version == "v20":'
    insert = '''elif self.model_version in ("v25", "vm25", "vm2.5"):
            return self._load_v25()
        ''' + needle
    if needle in src and '== "v25"' not in src:
        src = src.replace(needle, insert, 1)
    # insert _load_v25 / _score_v25 before _load_v20
    method = '''
    def _load_v25(self) -> bool:
        """Load VM2.5 via shared scorer (features_v2 + V3 side data)."""
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
    # score_stock branch
    sn = 'elif self.model_version == "v20":'
    si = '''elif self.model_version in ("v25", "vm25", "vm2.5"):
            return self._score_v25(kline_df, symbol, sector_heat)
        ''' + sn
    # only in score_stock — replace second occurrence carefully
    if 'return self._score_v25' not in src and sn in src:
        # replace in score_stock area: find after insufficient_data
        parts = src.split("if feats.empty or len(feats) < 30:")
        if len(parts) >= 2:
            head, rest = parts[0], parts[1]
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
    # syntax check
    r = subprocess.run([sys.executable, "-m", "py_compile", str(path)])
    log(f"ml_screener v25 patch compile={r.returncode}")
    if r.returncode != 0:
        # restore
        path.write_text(bak.read_text(encoding="utf-8"), encoding="utf-8")
        log("RESTORE ml_screener from backup due to compile fail")


def main():
    log("=== orchestrate VM2.5 retrain + V3 pipeline backtest ===")
    if not wait_fundflow():
        log("fundflow wait failed; still try coverage check")
    # coverage (non-fail)
    run("python3 check_v25_data_coverage.py")
    # retrain
    rc = run("python3 -u train_v25.py")
    meta_p = ROOT / "models" / "v25_meta.json"
    n_samples = 0
    if meta_p.exists():
        try:
            n_samples = int(json.loads(meta_p.read_text(encoding="utf-8")).get("training", {}).get("n_samples", 0) or 0)
        except Exception:
            n_samples = 0
    log(f"train n_samples={n_samples}")
    if rc != 0 or n_samples < 1000:
        log("train failed; abort backtest")
        sys.exit(rc)
    patch_ml_screener_v25()
    patch_recommend_to_v25()
    # V3 pipeline backtest — full market may be long; start with reasonable window
    rc = run("python3 -u backtest_v3_pipeline.py --start 2026-06-01 --end 2026-07-15 --hold 5 --top-k 20 --stride 1")
    log(f"done backtest rc={rc}")
    if Path("output/v3_pipeline_backtest.json").exists():
        kpi = json.loads(Path("output/v3_pipeline_backtest.json").read_text(encoding="utf-8")).get("kpi", {})
        log("KPI: " + json.dumps(kpi, ensure_ascii=False))
    sys.exit(rc)


if __name__ == "__main__":
    main()