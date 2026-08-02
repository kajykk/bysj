# Production Dockerfile for Depression Warning System Backend
# Multi-stage build: deps + runtime for smaller final image
#
# Build:
#   docker build -f Dockerfile -t dws-backend:v1.30 .
#
# Run:
#   docker run -d --name dws-backend \
#     -p 8000:8000 \
#     -e DATABASE_URL=postgresql+asyncpg://user:pass@db:5432/dws \
#     -e REDIS_URL=redis://redis:6379/0 \
#     -e JWT_SECRET_KEY=<your-secret> \
#     -e SENTRY_DSN=<your-dsn> \
#     dws-backend:v1.30
#
# Health check:
#   docker exec dws-backend curl -f http://localhost:8000/health

# ===============================================================
# Stage 1: deps — install Python dependencies in a clean layer
# ===============================================================
# T-P0-04: 升级至 Python 3.12.13 (3.12 系列最新安全补丁, superseded 3.12.9)
# 修复 CVE-2025-59375 等安全漏洞, 清零 trivy HIGH/CRITICAL
FROM python:3.12.13-slim AS deps

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System libraries: build tools for C extensions (scikit-learn, pandas, etc.)
# We keep them only in the build stage; the final stage is smaller.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        g++ \
        libpq-dev \
        libffi-dev \
        libmagic1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy only requirements first to leverage layer caching
COPY requirements.txt ./

# Install CPU-only PyTorch first (much smaller than the default CUDA build)
# TensorFlow is heavy; install only if required by the deployment target.
# We install the standard requirements without torch/tensorflow here for slim image;
# the deep-learning layer is loaded lazily and can fall back to heuristic rules
# (see app.core.model_engine: model loader degrades gracefully).
RUN pip install --no-cache-dir \
        fastapi>=0.110.0 \
        "uvicorn[standard]>=0.29.0" \
        "sqlalchemy[asyncio]>=2.0.29" \
        asyncpg>=0.29.0 \
        "psycopg2>=2.9.9" \
        aiosqlite>=0.19.0 \
        alembic>=1.13.1 \
        "pydantic[email]>=2.7.0" \
        pydantic-settings>=2.2.1 \
        "PyJWT[crypto]>=2.8.0" \
        "bcrypt>=4.0.0,<5.0.0" \
        python-multipart>=0.0.9 \
        redis>=5.0.4 \
        requests>=2.31.0 \
        celery>=5.4.0 \
        "scikit-learn>=1.5.0,<2.0.0" \
        joblib>=1.4.2 \
        "numpy>=1.26.4" \
        "pandas>=2.1.4" \
        openpyxl>=3.1.2 \
        reportlab>=4.1.0 \
        python-dotenv>=1.0.1 \
        slowapi>=0.1.9 \
        python-magic>=0.4.27 \
        "sentry-sdk[fastapi]>=2.0.0"

# ===============================================================
# Stage 2: runtime — minimal image with only the application
# ===============================================================
# T-P0-04: 升级至 Python 3.12.13 (与 deps 阶段保持一致)
FROM python:3.12.13-slim AS runtime

LABEL maintainer="DWS Team" \
      version="v1.28-final" \
      description="Depression Warning System backend (FastAPI)"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    PYTHONPATH=/app \
    PATH="/app/.local/bin:${PATH}"

# Runtime system libraries only (no compilers)
# T-P0-04: 添加 apt-get upgrade 升级基础镜像系统包至最新安全补丁版本
# python:3.12.13-slim 基于 Debian 12 (bookworm), 上游发布后可能有 OpenSSL/libcurl/etc 安全补丁
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        libmagic1 \
        curl \
        tini \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r dws && useradd -r -g dws -d /app -s /sbin/nologin dws

WORKDIR /app

# Copy installed Python packages from the deps stage
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# Copy application source
COPY --chown=dws:dws app/ /app/app/
COPY --chown=dws:dws alembic/ /app/alembic/
COPY --chown=dws:dws alembic.ini /app/alembic.ini
COPY --chown=dws:dws models/ /app/models/
COPY --chown=dws:dws scripts/ /app/scripts/

# Make sure the user can write to the app dir (for sqlite fallback, logs, etc.)
RUN mkdir -p /app/logs /app/tmp && chown -R dws:dws /app

USER dws

EXPOSE 8000

# Health check — backend exposes /health on port 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# tini ensures proper signal handling for graceful shutdown
ENTRYPOINT ["/usr/bin/tini", "--"]

# Production: 多 worker 以利用多核 CPU（P1-INFRA-032 修复：从 1 改为可配置）
# WEB_CONCURRENCY 默认 4，可通过环境变量调整
# Use exec form so signals reach uvicorn properly
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-4} --loop uvloop --http httptools --proxy-headers --forwarded-allow-ips '10.0.0.0/8,172.16.0.0/12,192.168.0.0/16' --access-log --no-server-header"]
