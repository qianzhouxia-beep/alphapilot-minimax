#!/bin/bash
set -euo pipefail
cd /home/ubuntu/alphapilot-repo
git add frontend/app/cn/page.tsx
git commit -m "feat(cn): surface R&D dual-loop as product selling point

Document Track A/B workshop + human promotion gate and weekly schedule on the CN dashboard."
git push origin HEAD
git status -sb
grep -n "模型研发双循环" frontend/app/cn/page.tsx | head -2
