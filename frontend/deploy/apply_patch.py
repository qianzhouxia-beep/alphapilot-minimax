#!/usr/bin/env python3
"""apply_patch.py - 2026-07-04
向 api_server.py 末尾插入单只股票详情端点 /api/v1/cn/stock/{symbol}
"""
import re, shutil, sys
from datetime import datetime

SRC = "api_server.py"
BAK = f"api_server.py.bak.{datetime.now().strftime('%H%M%S')}"

# 备份
shutil.copy2(SRC, BAK)
print(f"[1/4] 备份 -> {BAK}")

# 读源文件
with open(SRC, encoding="utf-8") as f:
    src = f.read()

# patch: 在最后一个 @app.get/post 路由后面插入新端点
PATCH = '''
@app.get("/api/v1/cn/stock/{symbol}")
async def get_cn_stock_detail(symbol: str):
    """单只股票详情: 从 recommend cache 查表"""
    try:
        from pathlib import Path as _P
        import json as _j
        import re as _re
        cp = _P("/home/ubuntu/alphapilot/recommend_cache.json")
        if not cp.exists():
            return {"error": "cache not found, please run pipeline first", "status": 503}
        cache = _j.loads(cp.read_text(encoding="utf-8"))
        items = cache.get("items", [])
        # symbol 归一化: 去掉 SH/SZ 前缀和 .SH/.SZ 后缀
        sym = _re.sub(r"^SH|^SZ|\\.SH$|\\.SZ$", "", symbol.upper())
        item = next(
            (x for x in items
             if _re.sub(r"^SH|^SZ|\\.SH$|\\.SZ$", "", str(x.get("symbol", "")).upper()) == sym),
            None
        )
        if not item:
            return {"error": f"symbol {symbol} not in recommend list", "status": 404}
        return {
            "symbol": item.get("symbol"),
            "name": item.get("name", ""),
            "score": item.get("score", 0),
            "up_probability": item.get("up_probability", 0),
            "risk": item.get("risk", "medium"),
            "main_force": item.get("main_force", ""),
            "sector": item.get("sector", ""),
            "buy_price": item.get("buy_price"),
            "target_price": item.get("target_price"),
            "stop_price": item.get("stop_price"),
            "sector_heat": item.get("sector_heat"),
            "price": item.get("price"),
            "change_pct": item.get("change_pct"),
            "open": item.get("open"),
            "high": item.get("high"),
            "low": item.get("low"),
            "prev_close": item.get("prev_close"),
            "volume": item.get("volume"),
            "turnover": item.get("turnover"),
            "pe": item.get("pe"),
            "market_cap": item.get("market_cap"),
            "source": cache.get("source", "live"),
        }
    except Exception as e:
        return {"error": str(e), "status": 500}
'''

# 找最后一个 @app.get 或 @app.post 块
matches = list(re.finditer(r"@app\.(get|post)\([^)]+\)", src, re.DOTALL))
if not matches:
    print("[ERR] 没找到任何 @app 路由, 请检查 api_server.py")
    sys.exit(1)

last = matches[-1]
print(f"[2/4] 找到 {len(matches)} 个路由, 将在第 {last.end()} 字符位置插入新端点")

new_src = src[:last.end()] + "\n" + PATCH + src[last.end():]
with open(SRC, "w", encoding="utf-8") as f:
    f.write(new_src)
print(f"[3/4] 已写入, 新文件行数: {new_src.count(chr(10))}")

# 语法检查
import ast
try:
    ast.parse(new_src)
    print("[4/4] ✅ 语法检查通过")
except SyntaxError as e:
    print(f"[ERR] 语法错误: {e}")
    print(f"     正在回滚...")
    shutil.copy2(BAK, SRC)
    sys.exit(1)

print()
print("=" * 50)
print("Patch 完成! 下一步:")
print("  sudo systemctl restart alphapilot-api")
print("  sleep 2 && curl -s http://localhost:8000/health")
print("=" * 50)