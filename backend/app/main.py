"""
AlphaPilot Zeabur Gateway
- Serve Next.js static build output from /app/frontend/out
- Proxy /api/* requests to Tencent Cloud backend via nginx (port 80, firewall blocks :8000)
"""
import os
import httpx
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path

app = FastAPI(title="AlphaPilot Gateway", version="1.0.0")

# Backend URL on Tencent Cloud (nginx proxying port 80 -> localhost:8000)
BACKEND_URL = os.environ.get("BACKEND_URL", "http://150.158.100.236")
FRONTEND_DIR = Path("/app/frontend/out")

# Proxy /api/* to Tencent Cloud backend
@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy_api(path: str, request: Request):
    url = f"{BACKEND_URL}/api/{path}"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            body = await request.body() if request.method in ("POST", "PUT", "PATCH") else None
            resp = await client.request(
                method=request.method,
                url=url,
                params=request.query_params,
                content=body,
                headers={k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")},
            )
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers={k: v for k, v in resp.headers.items() if k.lower() not in ("content-encoding", "transfer-encoding", "content-length")},
            )
    except httpx.RequestError as e:
        return JSONResponse(
            status_code=502,
            content={"error": "Backend unreachable", "detail": str(e), "backend": BACKEND_URL},
        )

# Dockerfile health check endpoint
@app.get("/api/v1/ping")
async def ping():
    return {"status": "ok"}
@app.get("/_zeabur_health")
async def health():
    return {"status": "ok", "backend": BACKEND_URL, "frontend_dir": str(FRONTEND_DIR), "frontend_exists": FRONTEND_DIR.exists()}

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
