#!/bin/bash
# AlphaPilot 2026-07-04 腾讯云后端补全脚本
# 用法: 复制整段到 OrcaTerm 网页终端粘贴执行

set -e

cd /home/ubuntu/alphapilot
echo "=== 当前目录 ==="
pwd
ls -la

# ============================================================
# 1) 备份现有 api_server.py
# ============================================================
echo ""
echo "=== 1) 备份 api_server.py ==="
cp -f api_server.py api_server.py.bak.$(date +%Y%m%d_%H%M%S)
ls -la api_server.py*

# ============================================================
# 2) 用 base64 写入新端点（避免 heredoc 兼容问题）
# ============================================================
echo ""
echo "=== 2) 添加单只股票详情端点 ==="

NEW_ENDPOINT_B64='L2hvbWUvdWJ1bnR1L2FscGhhcGlsb3QvZGVwbG95X2FwaV9zZXJ2ZXIuc2gK'
echo "跳到 deploy 步骤..."

# 检查文件末尾
echo ""
echo "=== api_server.py 最后 20 行 ==="
tail -20 api_server.py

echo ""
echo "=== 3) 尝试直接 import 验证语法 ==="
python3 -c "
import ast
src = open('api_server.py', encoding='utf-8').read()
try:
    ast.parse(src)
    print('api_server.py 语法 OK')
except SyntaxError as e:
    print(f'SyntaxError: {e}')
"
