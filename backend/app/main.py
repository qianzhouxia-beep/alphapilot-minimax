"""
AlphaPilot Zeabur Gateway
- Serve Next.js static build output from /app/frontend/out
- Proxy /api/* requests to Tencent Cloud backend via nginx (port 80, firewall blocks :8000)
- Proxy /cn/sectors/research/* pretty URLs to Shanghai research HTML API
"""
import os
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="AlphaPilot Gateway", version="1.1.0")

# Backend URL on Tencent Cloud (nginx proxying port 80 -> localhost:8000)
BACKEND_URL = os.environ.get("BACKEND_URL", "http://150.158.100.236")
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
