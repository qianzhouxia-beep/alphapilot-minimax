# ============ 探查全量管线入口(在 OrcaTerm 终端逐条粘) ============

# 重要: 先确保回到 alphapilot 目录
cd ~/alphapilot

# ---- 第1条: 列所有端点 ----
curl -s http://localhost:8000/openapi.json | python3 -c "import sys,json; d=json.load(sys.stdin); [print(f'  {m.upper():6s} {p}') for p,ops in d['paths'].items() for m in ops]"
