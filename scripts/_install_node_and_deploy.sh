#!/bin/bash
set -euo pipefail

export NVM_DIR="$HOME/.nvm"
if [ ! -s "$NVM_DIR/nvm.sh" ]; then
  echo "Installing nvm..."
  curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
fi
# shellcheck disable=SC1090
. "$NVM_DIR/nvm.sh"

if ! command -v node >/dev/null 2>&1; then
  echo "Installing Node 20 LTS..."
  nvm install 20
fi
nvm use 20
node -v
npm -v

SRC=/home/ubuntu/alphapilot/frontend_cn_page.tsx
FE=/home/ubuntu/alphapilot-repo/frontend

cp -f "$SRC" "$FE/app/cn/page.tsx"
if [ -d /home/ubuntu/alphapilot-frontend/app/cn ]; then
  cp -f "$SRC" /home/ubuntu/alphapilot-frontend/app/cn/page.tsx
fi
cp -f "$SRC" /home/ubuntu/alphapilot/page.tsx

cd "$FE"
if [ ! -d node_modules ]; then
  echo "npm ci..."
  npm ci
fi

echo "Building Next.js export..."
npm run build

if [ -d out ]; then
  mkdir -p /home/ubuntu/alphapilot/frontend_out
  rsync -a --delete out/ /home/ubuntu/alphapilot/frontend_out/
  echo "Synced to alphapilot/frontend_out"
else
  echo "ERROR: no out/ after build" >&2
  exit 1
fi

# restart API (manual uvicorn)
API_PID=$(pgrep -f 'uvicorn api_server:app' | head -1 || true)
if [ -n "${API_PID:-}" ]; then
  echo "Restarting uvicorn pid $API_PID"
  kill "$API_PID" || true
  sleep 2
fi
cd /home/ubuntu/alphapilot
nohup python3 -m uvicorn api_server:app --host 0.0.0.0 --port 8000 >> api_server.log 2>&1 &
echo "started uvicorn pid $!"
sleep 2
curl -sS "http://127.0.0.1:8000/api/recommend?limit=1" | python3 -c 'import sys,json; d=json.load(sys.stdin); print("keys", list(d.keys())[:20]); s=(d.get("stocks") or d.get("recommendations") or [{}])[0]; print({k:s.get(k) for k in ("confidence_score","model_proba","score_pct","score","name","symbol")})'
echo DONE
