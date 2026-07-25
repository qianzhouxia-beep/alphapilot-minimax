#!/usr/bin/env python3
"""AlphaPilot API server wrapper — 在此文件添加额外路由，不会被 api_server.py 更新覆盖。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.chdir(Path(__file__).parent)

# ── 导入主 app ──
from api_server import app

# ── 静态页面路由 ──
from fastapi.responses import FileResponse

_frontend_dir = Path(__file__).parent / "frontend_out"


def _serve_html(path: Path):
    if path.is_file():
        return FileResponse(
            str(path),
            media_type="text/html; charset=utf-8",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
    from fastapi import HTTPException

    raise HTTPException(status_code=404, detail="page not found")


@app.get("/api/v1/cn/framework", include_in_schema=False)
async def framework_page():
    return _serve_html(_frontend_dir / "cn" / "framework" / "index.html")


@app.get("/api/v1/cn/quant", include_in_schema=False)
async def quant_marketing_page():
    """量化营销推广页 — 在线自进化量化交易系统"""
    return _serve_html(_frontend_dir / "cn" / "quant" / "index.html")

# 暴露 app 供 uvicorn 使用
__all__ = ["app"]
