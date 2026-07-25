#!/bin/bash
set -euo pipefail
export NVM_DIR=/home/ubuntu/.nvm
# shellcheck disable=SC1091
. /home/ubuntu/.nvm/nvm.sh
nvm use 20 >/dev/null

echo "== restart API =="
sudo systemctl restart alphapilot-api.service
sleep 2
systemctl is-active alphapilot-api.service
curl -sS -m 20 http://127.0.0.1:8000/api/v1/cn/trade-plan | python3 -c '
import sys,json
d=json.load(sys.stdin)
print("status", (d.get("status") or {}).get("code"), (d.get("status") or {}).get("label"))
print("expo", d.get("position_exposure"), "buys", len(d.get("buys") or []), "layers", len(d.get("exit_layers") or []))
print("asof", d.get("asof"))
'

echo "== build frontend =="
cd /home/ubuntu/alphapilot-repo/frontend
npm run build

echo "== deploy frontend_out =="
bash /home/ubuntu/alphapilot/_deploy_fe.sh

echo "== verify static contains TradePlan =="
if grep -R "今日交易指令" -l /home/ubuntu/alphapilot/frontend_out/cn/screener/ 2>/dev/null | head; then
  echo "OK: trade plan UI in screener build"
else
  echo "WARN: trade plan string not found"
  exit 1
fi
