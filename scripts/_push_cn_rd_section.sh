#!/bin/bash
set -euo pipefail
cd /home/ubuntu/alphapilot-repo
python3 /home/ubuntu/alphapilot/scripts/_patch_cn_rd_section.py
git add frontend/app/cn/page.tsx
git commit -m "feat(cn): market R&D dual-loop workshop as product differentiator

Track A weekly uplift, Track B RD-Agent self-dev, human promotion gate; schedule on page."
git push origin HEAD
git log -1 --oneline
