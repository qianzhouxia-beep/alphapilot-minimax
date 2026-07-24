#!/bin/bash
# 盘后二次兜底：15:30 若源站延迟导致空更新，16:30 再拉 K 线+筹码
set -e
cd /home/ubuntu/alphapilot
/usr/bin/python3 -u cache_kline.py update
/usr/bin/python3 -u scripts/pull_chip_from_kline.py --workers 1
/usr/bin/python3 -u scripts/data_readiness_gate.py --repair
