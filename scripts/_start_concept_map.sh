#!/bin/bash
cd /home/ubuntu/alphapilot
mkdir -p data scripts
# sample first
python3 scripts/build_stock_concept_map_tdx.py --codes 300750,600900,688981,601988,600519
echo SAMPLE_DONE
nohup python3 -u scripts/build_stock_concept_map_tdx.py --concurrency 20 > data/stock_concept_map_tdx.log 2>&1 &
echo PID:$!
sleep 8
head -25 data/stock_concept_map_tdx.log
