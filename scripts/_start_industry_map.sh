#!/bin/bash
set -e
cd /home/ubuntu/alphapilot
python3 scripts/build_stock_industry_map_tdx.py --codes 600519,300750,688981,601988,000001
echo SAMPLE_OK
nohup python3 -u scripts/build_stock_industry_map_tdx.py --concurrency 16 > data/stock_industry_map_tdx.log 2>&1 &
echo PID:$!
sleep 8
head -25 data/stock_industry_map_tdx.log
