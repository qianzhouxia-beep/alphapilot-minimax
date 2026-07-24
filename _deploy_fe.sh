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
echo "deployed frontend_out"
ls -la /home/ubuntu/alphapilot/frontend_out/cn/paper-trading/ | head
cd /home/ubuntu/alphapilot
python3 _seed_p0_tickets.py
