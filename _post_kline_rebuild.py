#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path("/home/ubuntu/alphapilot")
LOG = ROOT / "output" / "logs" / "post_kline_rebuild.log"


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(cmd: str, timeout_min: int = 30) -> bool:
    log(f"START {cmd}")
    r = subprocess.run(cmd, shell=True, cwd=str(ROOT), timeout=timeout_min * 60)
    log(f"{'OK' if r.returncode == 0 else 'FAIL'} rc={r.returncode}")
    return r.returncode == 0


def main() -> int:
    log("=" * 50)
    ok = True
    ok &= run(f"{sys.executable} -u scripts/pull_chip_from_kline.py --workers 1", 20)
    ok &= run(f"{sys.executable} -u scripts/data_readiness_gate.py --repair", 20)

    # sector rotation snapshot (writes SNAP)
    ok &= run(f"{sys.executable} -u -c \"from sector_rotation_gate import build_snapshot; print(build_snapshot())\"", 10)

    # dashboard-style snapshot refresh via sector_dashboard
    try:
        from sector_dashboard import build_dashboard

        d = build_dashboard(force_refresh=True)
        path = ROOT / "output" / "sector_dashboard_today.json"
        path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"OK sector_dashboard_today {d.get('generated_at')} summary={d.get('summary')}")
    except Exception as e:
        log(f"FAIL sector_dashboard: {e}")
        ok = False

    ok &= run(f"{sys.executable} -u run_pipeline_standalone.py", 40)
    ok &= run(f"{sys.executable} -u sector_research_report.py --session afternoon", 20)

    # final verify snippet
    import pandas as pd
    from collections import Counter

    TODAY = "2026-07-21"
    df = pd.read_parquet(ROOT / "data/kline_cache/kline_all.parquet")
    last = df.assign(_d=pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")).groupby("symbol")["_d"].max()
    log(f"kline asof_today={int((last==TODAY).sum())}/{len(last)}")

    ff = json.loads((ROOT / "data/fund_flow_history.json").read_text(encoding="utf-8"))
    fl = [max(v) for v in ff.values() if isinstance(v, dict) and v]
    log(f"fund latest={Counter(fl).most_common(3)}")

    chip = json.loads((ROOT / "chip_data_all.json").read_text(encoding="utf-8"))
    items = chip.get("data") if isinstance(chip, dict) and isinstance(chip.get("data"), dict) else chip
    dates = []
    if isinstance(items, dict):
        for v in items.values():
            if isinstance(v, dict):
                d = v.get("asof") or v.get("date") or v.get("trade_date")
                if d:
                    dates.append(str(d)[:10])
    log(f"chip date dist={Counter(dates).most_common(3)}")

    rd = json.loads((ROOT / "output/data_readiness.json").read_text(encoding="utf-8"))
    log(f"ready_for_trade={rd.get('ready_for_trade')} fails={rd.get('fails')}")

    rec = json.loads((ROOT / "output/daily_recommend.json").read_text(encoding="utf-8"))
    r = rec.get("recommendations") or []
    log(f"recommend n={len(r)} at={rec.get('generated_at')} top={[x.get('name') for x in r[:3]]}")

    for rel in [
        "data/sector_flow_today.json",
        "data/concept_flow_today.json",
        "data/sector_flow_3day.json",
    ]:
        p = ROOT / rel
        d = json.loads(p.read_text(encoding="utf-8"))
        log(f"{rel} total={d.get('total')} asof={d.get('asof')} top={(d.get('data') or [{}])[0].get('name')}")

    log(f"DONE ok={ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
