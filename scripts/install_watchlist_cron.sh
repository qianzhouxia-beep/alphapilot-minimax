#!/bin/bash
set -e
mkdir -p /home/ubuntu/alphapilot/output/logs
cat > /home/ubuntu/alphapilot/scripts/run_watchlist_update.sh <<'EOF'
#!/bin/bash
cd /home/ubuntu/alphapilot
python3 -u -c 'from watchlist import recompute_tracking; import json; print(json.dumps(recompute_tracking(force=True), ensure_ascii=False))'
EOF
chmod +x /home/ubuntu/alphapilot/scripts/run_watchlist_update.sh
# install cron line
TMP=$(mktemp)
crontab -l 2>/dev/null | grep -v 'run_watchlist_update' > "$TMP" || true
echo '40 15 * * 1-5 /home/ubuntu/alphapilot/scripts/run_watchlist_update.sh >> /home/ubuntu/alphapilot/output/logs/watchlist_update.log 2>&1' >> "$TMP"
crontab "$TMP"
rm -f "$TMP"
echo "=== crontab ==="
crontab -l | grep -E 'watchlist|pipeline_0500'
echo "=== sample rows ==="
python3 /tmp/dump_watchlist.py | head -12
