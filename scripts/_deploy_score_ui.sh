#!/bin/bash
set -euo pipefail

export NVM_DIR="$HOME/.nvm"
if [ -s "$NVM_DIR/nvm.sh" ]; then
  # shellcheck disable=SC1090
  . "$NVM_DIR/nvm.sh"
  nvm use 20 >/dev/null
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm not found. Run scripts/_install_node_and_deploy.sh once." >&2
  exit 1
fi

SRC=/home/ubuntu/alphapilot/frontend_cn_page.tsx
FE=/home/ubuntu/alphapilot-repo/frontend

cp -f "$SRC" "$FE/app/cn/page.tsx"
if [ -d /home/ubuntu/alphapilot-frontend/app/cn ]; then
  cp -f "$SRC" /home/ubuntu/alphapilot-frontend/app/cn/page.tsx
fi
cp -f "$SRC" /home/ubuntu/alphapilot/page.tsx

cd "$FE"
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
pids=$(pgrep -f '/usr/bin/python3 -m uvicorn api_server:app' || true)
if [ -n "${pids:-}" ]; then
  kill $pids || true
  sleep 2
fi
cd /home/ubuntu/alphapilot
nohup python3 -m uvicorn api_server:app --host 0.0.0.0 --port 8000 >> api_server.log 2>&1 &
echo "started uvicorn pid $!"
sleep 3
curl -sS "http://127.0.0.1:8000/api/v1/cn/recommend" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("pipeline_version"), d.get("model_version"), (d.get("stats") or {}).get("score_scale"))'
echo DONE
