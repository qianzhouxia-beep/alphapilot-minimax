#!/usr/bin/env python3
"""AlphaPilot API server wrapper — 在此文件添加额外路由，不会被 api_server.py 更新覆盖。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.chdir(Path(__file__).parent)

# ── 导入主 app ──
from api_server import app

# ── CapitalPulse 资金流看板集成（REST + WebSocket + 采集服务生命周期）──
from capitalpulse import bridge as _capitalpulse_bridge

_capitalpulse_bridge.setup(app)

# ── 静态页面路由 ──
from fastapi.responses import FileResponse
from fastapi import HTTPException

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
    primary = _frontend_dir / "cn" / "framework" / "index.html"
    fallback = Path(__file__).parent / "AlphaPilot_Framework_CN.html"
    if primary.is_file():
        return _serve_html(primary)
    return _serve_html(fallback)


@app.get("/api/v1/cn/quant", include_in_schema=False)
async def quant_marketing_page():
    """量化营销推广页 — 在线自进化量化交易系统"""
    primary = _frontend_dir / "cn" / "quant" / "index.html"
    fallback = Path(__file__).parent / "cn_quant_page.html"
    if primary.is_file():
        return _serve_html(primary)
    return _serve_html(fallback)

# ── 每日复盘报告（API路由，不被Next.js前端拦截）──
_REVIEW_DIR = Path(__file__).parent / "frontend_out" / "cn" / "daily-review"

@app.get("/api/v1/cn/daily-review/latest", include_in_schema=False)
async def daily_review_latest():
    latest = _REVIEW_DIR / "latest.html"
    if latest.is_file():
        return _serve_html(latest)
    raise HTTPException(status_code=404, detail="no report yet")



# ── 每日复盘报告归档列表（前端「每日复盘报告归档」依赖）──
@app.get("/api/v1/cn/daily-review/list", include_in_schema=False)
async def daily_review_list():
    """扫描 daily-review 目录，返回按日期倒序的复盘报告列表（自动随新报告更新）。"""
    from datetime import datetime as _dt
    entries = []
    if _REVIEW_DIR.is_dir():
        for p in _REVIEW_DIR.iterdir():
            if p.suffix == ".html" and p.stem.isdigit() and len(p.stem) == 8:
                if p.name in ("latest.html", "index.html"):
                    continue
                stem = p.stem
                entries.append({
                    "date": f"{stem[0:4]}-{stem[4:6]}-{stem[6:8]}",
                    "file": p.name,
                })
    entries.sort(key=lambda x: x["file"], reverse=True)
    return {
        "generated_at": _dt.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "reports": entries,
    }


@app.get("/api/v1/cn/daily-review/{filename:path}", include_in_schema=False)
async def daily_review_api(filename: str):
    path = _REVIEW_DIR / filename
    if path.is_file() and path.suffix == ".html":
        return _serve_html(path)
    raise HTTPException(status_code=404, detail="not found")


# ── QMT 交易信号端点（供本地 qmt_bridge.py 轮询）──
@app.get("/api/v1/cn/trade-signals", include_in_schema=False)
async def trade_signals():
    import json as _json, os as _os, time as _time
    rec_path = Path(__file__).parent / "output" / "daily_recommend.json"
    morning_path = Path(__file__).parent / "output" / "morning_live_picks.json"
    if not rec_path.exists():
        return {"generated_at": "", "signals": [], "exit_signals": [], "message": "no data"}
    try:
        rec = _json.loads(rec_path.read_text(encoding="utf-8"))
        items = rec.get("recommendations", rec.get("items", []))
        # 优先用 morning_live_picks（当天且不超过2小时旧；否则降级到 daily_recommend）
        if morning_path.exists():
            morning_age_h = (_time.time() - _os.path.getmtime(str(morning_path))) / 3600.0
            if morning_age_h < 2:
                mp = _json.loads(morning_path.read_text(encoding="utf-8"))
                picks = mp.get("picks", [])
                if picks:
                    items = picks
        # 标准化信号
        signals = []
        for it in items[:2]:  # Top 2
            sym = str(it.get("symbol", ""))[-6:]
            score = float(it.get("score", 0) or 0)
            ref_price = it.get("buy_price") or it.get("close") or it.get("price") or 0
            signals.append({
                "symbol": sym,
                "name": it.get("name", ""),
                "score": round(score, 4),
                "action": "buy",
                "price": round(float(ref_price), 2) if ref_price else None,
                "position_pct": 25.0,
                "stop_loss": round(float(ref_price or 0) * 0.90, 2) if ref_price else None,
                "take_profit": round(float(ref_price or 0) * 1.15, 2) if ref_price else None,
                "signal_id": f"{sym}-{rec.get('generated_at', rec.get('run_at', ''))[:19]}",
            })
        return {
            "generated_at": rec.get("generated_at", rec.get("run_at", "")),
            "pipeline_version": rec.get("pipeline_version", "v3"),
            "position_exposure": rec.get("position_exposure", 0.5),
            "signals": signals,
            "exit_signals": [],
            "market_env": rec.get("env", {}),
        }
    except Exception as e:
        return {"generated_at": "", "signals": [], "exit_signals": [], "error": str(e)}

# 暴露 app 供 uvicorn 使用
__all__ = ["app"]


# ── 研报归档（不覆盖已有 nginx 前端）──
_RESEARCH_ROOT = Path(__file__).parent / "output" / "sector_research"

@app.get("/api/v1/cn/sectors/research/", include_in_schema=False)
async def sector_research_index():
    """返回研报归档索引 HTML（由 sector_research_report 生成）。"""
    return _serve_html(_RESEARCH_ROOT / "index.html")


@app.get("/api/v1/cn/sectors/research/{date}/{session}/", include_in_schema=False)
async def sector_research_page(date: str, session: str):
    """返回某日某时段的研报 HTML。"""
    return _serve_html(_RESEARCH_ROOT / date / session / "index.html")
