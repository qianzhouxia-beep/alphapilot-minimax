#!/bin/bash
set -euo pipefail
export PATH="/home/ubuntu/.nvm/versions/node/v20.20.2/bin:/usr/bin:/bin:$PATH"
ROOT=/home/ubuntu/alphapilot
SRC="$ROOT/frontend_cn_page.tsx"
FE=/home/ubuntu/alphapilot-repo/frontend

cp -f "$SRC" "$FE/app/cn/page.tsx"
if [ -d /home/ubuntu/alphapilot-frontend/app/cn ]; then
  cp -f "$SRC" /home/ubuntu/alphapilot-frontend/app/cn/page.tsx
fi
cp -f "$SRC" "$ROOT/page.tsx"

cd "$FE"
echo "Building with $(command -v node) $(node -v)"
npm run build

if [ -d out ]; then
  mkdir -p "$ROOT/frontend_out"
  rsync -a --delete out/ "$ROOT/frontend_out/"
  echo "Synced frontend_out"
  grep -R "模型研发双循环" "$ROOT/frontend_out" -l | head -5 || true
else
  echo "ERROR: no out/" >&2
  exit 1
fi
