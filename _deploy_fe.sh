#!/bin/bash
set -e
export NVM_DIR=/home/ubuntu/.nvm
. /home/ubuntu/.nvm/nvm.sh
nvm use 20 >/dev/null
cd /home/ubuntu/alphapilot-repo/frontend
if grep -R "今日待确认" -l out/cn/paper-trading/ >/tmp/fe_hit.txt 2>/dev/null; then
  echo "build contains gate UI:"
  cat /tmp/fe_hit.txt | head
else
  echo "WARN: gate UI string not found in build"
fi
rsync -a --delete out/ /home/ubuntu/alphapilot/frontend_out/
# 部署量化营销页
QUANT_SRC="/home/ubuntu/alphapilot/cn_quant_page.html"
if [ -f "$QUANT_SRC" ]; then
  mkdir -p /home/ubuntu/alphapilot/frontend_out/cn/quant
  cp -f "$QUANT_SRC" /home/ubuntu/alphapilot/frontend_out/cn/quant/index.html
  echo "deployed quant marketing page"
else
  echo "WARN: $QUANT_SRC not found, skip quant page"
fi
echo "deployed frontend_out"
ls -la /home/ubuntu/alphapilot/frontend_out/cn/paper-trading/ | head
cd /home/ubuntu/alphapilot
python3 _seed_p0_tickets.py
