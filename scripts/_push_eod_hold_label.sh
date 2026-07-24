#!/bin/bash
set -euo pipefail
cd /home/ubuntu/alphapilot-repo
git add frontend/app/cn/page.tsx
git commit -m "fix(cn): eod sniper holds until stop/peel (drop overnight-only label)"
git push origin HEAD
git log -1 --oneline
