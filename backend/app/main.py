"""
AlphaPilot Zeabur Gateway
- Serve Next.js static build output from /app/frontend/out
- Proxy /api/* requests to Tencent Cloud backend via nginx (port 80, firewall blocks :8000)
- Proxy /cn/sectors/research/* pretty URLs to Shanghai research HTML API
"""
import os
from pathlib import Path

import asyncio

import httpx
import websockets
from fastapi import FastAPI, Request, Response, WebSocket
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="AlphaPilot Gateway", version="1.1.0")

# Backend URL on Tencent Cloud (nginx proxying port 80 -> localhost:8000)
BACKEND_URL = os.environ.get("BACKEND_URL", "http://150.158.100.236")
WS_BACKEND_URL = os.environ.get("WS_BACKEND_URL", "ws://150.158.100.236")
FRONTEND_DIR = Path("/app/frontend/out")

HOP_BY_HOP = {
    "host",
    "content-length",
    "content-encoding",
    "transfer-encoding",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "upgrade",
}


async def _proxy_to_backend(backend_path: str, request: Request) -> Response:
    """Proxy a path to Shanghai backend, preserving query string and useful headers."""
    url = f"{BACKEND_URL}{backend_path}"
    try:
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            body = await request.body() if request.method in ("POST", "PUT", "PATCH") else None
            resp = await client.request(
                method=request.method,
                url=url,
                params=request.query_params,
                content=body,
                headers={
                    k: v
                    for k, v in request.headers.items()
                    if k.lower() not in HOP_BY_HOP
                },
            )
            headers = {
                k: v
                for k, v in resp.headers.items()
                if k.lower() not in HOP_BY_HOP
            }
            if not any(k.lower() == "content-type" for k in headers):
                headers["content-type"] = resp.headers.get(
                    "content-type", "application/octet-stream"
                )
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers=headers,
            )
    except httpx.RequestError as e:
        return JSONResponse(
            status_code=502,
            content={
                "error": "Backend unreachable",
                "detail": str(e),
                "backend": BACKEND_URL,
                "path": backend_path,
            },
        )


# Crypto dashboard backend (Singapore node)
CRYPTO_URL = os.environ.get("CRYPTO_URL", "http://43.156.119.47:8899")


async def _proxy_to_url(base_url: str, backend_path: str, request: Request) -> Response:
    """Proxy a path to an arbitrary HTTP backend, preserving query string and headers."""
    url = f"{base_url}{backend_path}"
    try:
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            body = await request.body() if request.method in ("POST", "PUT", "PATCH") else None
            resp = await client.request(
                method=request.method,
                url=url,
                params=request.query_params,
                content=body,
                headers={k: v for k, v in request.headers.items() if k.lower() not in HOP_BY_HOP},
            )
            headers = {k: v for k, v in resp.headers.items() if k.lower() not in HOP_BY_HOP}
            if not any(k.lower() == "content-type" for k in headers):
                headers["content-type"] = resp.headers.get("content-type", "application/octet-stream")
            return Response(content=resp.content, status_code=resp.status_code, headers=headers)
    except httpx.RequestError as e:
        return JSONResponse(
            status_code=502,
            content={"error": "Backend unreachable", "detail": str(e), "backend": base_url, "path": backend_path},
        )


# Local health endpoints must be registered BEFORE the /api proxy catch-all.
@app.get("/api/v1/ping")
async def ping():
    return {"status": "ok"}


@app.get("/_zeabur_health")
async def health():
    return {
        "status": "ok",
        "backend": BACKEND_URL,
        "frontend_dir": str(FRONTEND_DIR),
        "frontend_exists": FRONTEND_DIR.exists(),
    }




# CapitalPulse WebSocket 转发（/ws/sector-flow, /ws/stock-flow）-> 腾讯云 nginx -> uvicorn 8000
@app.websocket("/ws/{ws_path:path}")
async def proxy_ws(websocket: WebSocket, ws_path: str):
    await websocket.accept()
    upstream = f"{WS_BACKEND_URL}/ws/{ws_path}"
    if websocket.query_params:
        upstream += "?" + websocket.query_params
    try:
        async with websockets.connect(upstream) as client:
            async def pump_up():
                try:
                    async for msg in client:
                        if isinstance(msg, bytes):
                            await websocket.send_bytes(msg)
                        else:
                            await websocket.send_text(msg)
                except Exception:
                    pass
            task = asyncio.create_task(pump_up())
            try:
                while True:
                    msg = await websocket.receive()
                    if msg["type"] == "websocket.disconnect":
                        break
                    data = msg.get("text") or msg.get("bytes")
                    if data is None:
                        continue
                    await client.send(data)
            except Exception:
                pass
            finally:
                task.cancel()
    except Exception as exc:
        await websocket.close(code=1011, reason=str(exc)[:120])



# Proxy /api/* to Tencent Cloud backend
@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy_api(path: str, request: Request):
    return await _proxy_to_backend(f"/api/{path}", request)


# Pretty URL for sector research HTML (full page, not iframe).
# Index + date/session pages are proxied from Shanghai as standalone HTML.
@app.api_route("/cn/sectors/research", methods=["GET", "HEAD"], include_in_schema=False)
@app.api_route("/cn/sectors/research/", methods=["GET", "HEAD"], include_in_schema=False)
@app.api_route(
    "/cn/sectors/research/{path:path}",
    methods=["GET", "HEAD"],
    include_in_schema=False,
)
async def proxy_sector_research(request: Request, path: str = ""):
    suffix = (path or "").strip("/")
    backend_path = (
        "/api/v1/cn/sectors/research/"
        if not suffix
        else f"/api/v1/cn/sectors/research/{suffix}/"
    )
    return await _proxy_to_backend(backend_path, request)


# Crypto dashboard reverse proxy (SG 8899) -> https://alphapilot.api-tokenmaster.com/crypto/
@app.api_route("/crypto", methods=["GET", "HEAD", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"], include_in_schema=False)
@app.api_route("/crypto/", methods=["GET", "HEAD", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"], include_in_schema=False)
@app.api_route("/crypto/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"], include_in_schema=False)
async def proxy_crypto_dashboard(request: Request, path: str = ""):
    suffix = (path or "").strip("/")
    backend_path = "/" if not suffix else f"/{suffix}"
    return await _proxy_to_url(CRYPTO_URL, backend_path, request)


# Serve static frontend files
if FRONTEND_DIR.exists():
    next_dir = FRONTEND_DIR / "_next"
    if next_dir.exists():
        app.mount("/_next", StaticFiles(directory=str(next_dir)), name="next_static")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        file_path = FRONTEND_DIR / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        if not full_path.endswith("/"):
            file_path_html = FRONTEND_DIR / (full_path + ".html")
            if file_path_html.is_file():
                return FileResponse(str(file_path_html))
        file_path_dir = FRONTEND_DIR / full_path / "index.html"
        if file_path_dir.is_file():
            return FileResponse(str(file_path_dir))
        nf = FRONTEND_DIR / "404.html"
        if nf.is_file():
            return FileResponse(str(nf), status_code=404)
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
else:
    @app.get("/{full_path:path}")
    async def fallback(full_path: str):
        return JSONResponse(
            status_code=503,
            content={"error": "Frontend not built", "frontend_dir": str(FRONTEND_DIR)},
        )
