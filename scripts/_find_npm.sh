#!/bin/bash
set -e
echo "=== which ==="
command -v npm || true
command -v node || true
echo "=== nvm ==="
ls -d "$HOME"/.nvm/versions/node/*/bin/npm 2>/dev/null || true
echo "=== common paths ==="
ls /usr/local/bin/npm /usr/bin/npm 2>/dev/null || true
echo "=== find ==="
find /home/ubuntu -name 'npm' -type f 2>/dev/null | head -20
find /usr -name 'npm' -type f 2>/dev/null | head -10
echo "=== package.json locations ==="
ls -la /home/ubuntu/alphapilot-repo/frontend/package.json 2>/dev/null || true
ls -la /home/ubuntu/alphapilot-frontend/package.json 2>/dev/null || true
