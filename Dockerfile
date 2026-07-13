# AlphaPilot 项目统一 Dockerfile
# Stage 1: 构建 Next.js 前端
FROM node:20-alpine AS frontend-builder
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN mkdir -p /app/public
RUN npm run build

# Stage 2: 准备后端运行环境
FROM python:3.11-slim AS backend
WORKDIR /app
# 系统依赖 (pandas/numpy 需要)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# 复制后端 Python 代码
COPY api_server.py features.py ml_screener.py recommend.py light_categorize.py eod_sniper_signals.py paper_trading_signals.py enriched_data.py data_fetcher.py fund_flow_fetcher.py train_v19.py money_flow_gate.py overnight_sentiment.py multisource_fetcher.py fundflow_fetcher_v4.py fundflow_fetcher_v5.py ./
COPY models/ ./models/
COPY chip_data_all.json fundflow_individual.json daily_recommend.json watchlist.db ./

# 安装 Python 依赖
RUN pip install --no-cache-dir \
    fastapi==0.115.0 \
    uvicorn[standard]==0.32.0 \
    pydantic==2.9.0 \
    xgboost==2.1.0 \
    pandas==2.2.3 \
    numpy==1.26.4 \
    scipy==1.13.1 \
    scikit-learn==1.5.0 \
    requests==2.32.3 \
    httpx==0.27.0 \
    akshare==1.16.0 \
    tushare==1.4.0 \
    python-dotenv==1.0.1 \
    pytdx==1.72

# Stage 3: 复制前端静态构建产物到后端的 frontend/out 目录
COPY --from=frontend-builder /app/out ./frontend/out

# 暴露后端端口
EXPOSE 8000

# 启动 FastAPI (后端会自己 serve 前端静态文件)
CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8000"]
