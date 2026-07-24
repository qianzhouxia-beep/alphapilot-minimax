#!/bin/bash
# Install / refresh Workshop crontab entries (idempotent)
set -euo pipefail
ROOT=/home/ubuntu/alphapilot
chmod +x "$ROOT/rd_workshop/cron_track_a.sh" "$ROOT/rd_workshop/cron_track_b_doctor.sh"
mkdir -p "$ROOT/output/logs"

TMP=$(mktemp)
crontab -l 2>/dev/null | grep -v 'rd_workshop/cron_track_' >"$TMP" || true
cat >>"$TMP" <<'EOF'
# AlphaPilot Model R&D Workshop (no production model writes)
0 2 * * 6 /home/ubuntu/alphapilot/rd_workshop/cron_track_a.sh
0 3 1 * * /home/ubuntu/alphapilot/rd_workshop/cron_track_b_doctor.sh
EOF
crontab "$TMP"
rm -f "$TMP"
echo "Workshop crontab installed:"
crontab -l | grep rd_workshop || true
