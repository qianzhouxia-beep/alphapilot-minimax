#!/bin/bash
# Daily US overnight ingest + G1 signal (Shanghai, workdays 05:30 + 09:20 fallback)
# v1.1 (2026-09-16): stamp/mirror now run even if ingest exits non-zero, and the
# ingest exit code is propagated at the end (so a lagging upstream still refreshes
# the mirror with explicit stale rows instead of freezing it).
set -uo pipefail
ROOT=/home/ubuntu/alphapilot
cd "$ROOT"
mkdir -p "$ROOT/data/us_daily" "$ROOT/output/logs" "$ROOT/output/research_gates" "$ROOT/knowledge/ops"
/usr/bin/python3 -u "$ROOT/scripts/ingest_us_daily.py" \
  --out-dir "$ROOT/data/us_daily" \
  --symbols nvda,qqq \
  --emit-signal \
  >> "$ROOT/output/logs/ingest_us_daily.log" 2>&1
RC=$?
# pre-open G1 annotate (candidates may not exist yet)
/usr/bin/python3 -u "$ROOT/scripts/g1_shadow_stamp.py" --date "$(date +%F)" \
  >> "$ROOT/output/logs/g1_shadow_stamp.log" 2>&1 || true
# refresh static HTTP mirror for WB (same channel as 09:38; no new cron)
/usr/bin/python3 -u "$ROOT/scripts/mirror_research_to_qmt_scores.py" \
  >> "$ROOT/output/logs/mirror_research.log" 2>&1 || true
echo "DONE ingest $(date -Is) rc=$RC"
exit $RC
