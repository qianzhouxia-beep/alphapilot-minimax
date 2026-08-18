# AlphaPilot Multi-stage Dockerfile (Zeabur)
# Root Directory = "." → context = repo root

# ===== Stage 1: frontend build =====
FROM node:20-slim AS frontend-build
WORKDIR /fe

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund --registry=https://registry.npmjs.org

COPY frontend/ ./

RUN npm run build

# ===== Stage 2: python backend =====
FROM python:3.11-slim
ARG CACHEBUSTER=20260722-pe-customer-filter
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
 build-essential \
 libpq-dev \
 curl \
 && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app

COPY --from=frontend-build /fe/out ./frontend/out

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
 CMD curl -fsS http://localhost:8080/api/v1/ping || exit 1

CMD ["sh", "-c", "echo '=== Starting uvicorn on port ${PORT:-8080} ===' && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
