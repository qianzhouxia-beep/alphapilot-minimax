#!/bin/bash
# 补全数据到最近交易日（上周五等）
set -e
cd /home/ubuntu/alphapilot
mkdir -p /tmp/alphapilot_logs
LOG=/tmp/alphapilot_logs/backfill_$(date +%Y%m%d_%H%M%S).log
exec > >(tee -a "$LOG") 2>&1

echo "======== BACKFILL START $(date) ========"

echo "---- 1) patch + update kline ----"
python3 scripts/patch_and_update_kline.py
python3 cache_kline.py update

echo "---- 2) verify kline range ----"
python3 <<'PY'
import pandas as pd
from pathlib import Path
for p in [Path("data/kline_cache/kline_all.parquet"), Path("kline_all.parquet")]:
    df = pd.read_parquet(p)
    d = df["date"].astype(str)
    print(p, "max", d.max(), "min", d.min(), "rows", len(df), "syms", df["symbol"].nunique())
    # count per recent day
    for day in sorted(d.unique())[-8:]:
        n = int((d == day).sum())
        print(f"  {day}: {n} stocks")
PY

echo "---- 3) fundflow TDX overlay (recent) ----"
# 全市场 overlay 可能较久；用现有脚本增量写 progress，完成后 merge
if [ -f scripts/pull_fundflow_tdx.py ]; then
  # 不 replace-prod 全量重写，先拉 tdx 侧再 merge（若脚本支持）
  python3 scripts/pull_fundflow_tdx.py --concurrency 12 || echo "WARN fundflow pull exit $?"
  # 若产出 fund_flow_history.tdx.json，尝试轻量合并近端日期
  python3 <<'PY'
import json
from pathlib import Path
root = Path(".")
tdx = root / "data/fund_flow_history.tdx.json"
prod = root / "data/fund_flow_history.json"
if not tdx.exists():
    print("no tdx fundflow file, skip merge")
    raise SystemExit(0)
td = json.loads(tdx.read_text(encoding="utf-8"))
pr = json.loads(prod.read_text(encoding="utf-8")) if prod.exists() else {}
# merge: for each symbol, overlay tdx dates onto prod
n_sym = 0
n_day = 0
for sym, days in td.items():
    if not isinstance(days, dict):
        continue
    bucket = pr.setdefault(sym, {})
    for d, v in days.items():
        if d >= "2026-07-01":  # 只覆盖近端，避免打乱长历史
            bucket[d] = v
            n_day += 1
    n_sym += 1
prod.write_text(json.dumps(pr, ensure_ascii=False), encoding="utf-8")
print(f"merged fundflow near-end: symbols_touched~{n_sym} day_writes={n_day}")
# depth check
depths = [len(v) for v in pr.values() if isinstance(v, dict)]
print("prod symbols", len(pr), "mean_depth", round(sum(depths)/max(len(depths),1),1))
PY
else
  echo "WARN no pull_fundflow_tdx.py"
fi

echo "---- 4) sector/concept flow refresh if available ----"
python3 -c "from sector_rotation_gate import build_snapshot; s=build_snapshot(); print('sector snap ok', list(s.keys())[:8])" || echo "WARN sector snapshot"

echo "======== BACKFILL DONE $(date) ========"
echo "LOG=$LOG"
