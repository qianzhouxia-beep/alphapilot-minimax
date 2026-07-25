#!/bin/bash
# -*- coding: utf-8 -*-
# 集合竞价因子部署脚本 — 在远程服务器上运行
set -euo pipefail

ROOT="/home/ubuntu/alphapilot"

echo "=================================================="
echo "集合竞价因子深度集成 — 部署脚本"
echo "=================================================="

# 1. 确认代码已同步
echo ""
echo "[1/5] 确认代码文件..."
for f in \
    "$ROOT/call_auction_factors.py" \
    "$ROOT/features_v2.py" \
    "$ROOT/train_v25.py" \
    "$ROOT/vm25_scorer.py" \
    "$ROOT/scripts/run_auction_training.py"; do
    if [ -f "$f" ]; then
        echo "  ✅ $(basename $f)"
    else
        echo "  ❌ MISSING: $f"
        echo "  请先同步代码 (rsync / scp / git push)"
        exit 1
    fi
done

# 2. 快速验证集成
echo ""
echo "[2/5] 集成验证..."
python3 -c "
from call_auction_factors import ALL_FACTORS, compute_auction_factors
from features_v2 import V11_FEATURE_COLUMNS
au_cols = [c for c in V11_FEATURE_COLUMNS if c.startswith('rd_auction')]
print(f'  Call Auction Factors: {len(ALL_FACTORS)} factors active')
print(f'  V11_FEATURE_COLUMNS: {len(V11_FEATURE_COLUMNS)} total, {len(au_cols)} auction')
assert len(au_cols) >= 19, 'auction columns missing'
print('  ✅ Integration verified')
"

# 3. ICIR 分析
echo ""
echo "[3/5] 运行集合竞价因子 IC/IR 分析..."
python3 scripts/run_auction_training.py --icir-only --sample 800

# 4. 全量重训
echo ""
echo "[4/5] 全量重训 XGBoost 模型..."
# 先备份旧模型
BACKUP="$ROOT/models/backup_before_auction"
mkdir -p "$BACKUP"
cp "$ROOT/models"/v25_*.ubj "$BACKUP/" 2>/dev/null || true
cp "$ROOT/models/v25_meta.json" "$BACKUP/" 2>/dev/null || true
echo "  ✅ 旧模型已备份至 $BACKUP"

# 训练（生产 models/ 目录直接写入）
python3 -u train_v25.py --opt-only

echo "  ✅ 新模型训练完成"

# 5. 回测对比
echo ""
echo "[5/5] 回测对比..."
python3 scripts/run_auction_training.py --backtest-only

echo ""
echo "=================================================="
echo "集合竞价因子部署完成！"
echo "=================================================="
echo "结果文件:"
echo "  - output/auction_eval/auction_icir_analysis.json"
echo "  - output/auction_eval/training_meta.json"
echo "  - output/auction_eval/training_report.json"
echo "旧模型备份:"
echo "  - models/backup_before_auction/"
echo ""
echo "回滚命令（如需）:"
echo "  cp models/backup_before_auction/*.ubj models/"
echo "  cp models/backup_before_auction/v25_meta.json models/"
echo "=================================================="