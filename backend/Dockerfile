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

# Copy requirement manifests first to leverage layer caching
# ── 依赖版本单一事实源（SEC-P2-005 延伸）───────────────────────────────────
# 三处版本声明的权威顺序：
#   ① backend/requirements.lock — uv pip-compile 全量传递锁定，最高权威
#                                 （文件存在且完整时，构建一律以它为准）
#   ② backend/requirements.txt  — 顶层依赖声明，是 lock 的生成输入与升级入口
#   ③ 本 Dockerfile 内联清单    — 仅当 lock 缺失/不完整时的应急兜底，
#                                 平时不作为版本来源
# 说明：lock 为全量传递锁定且包含 tensorflow/torch 等重型 ML 依赖；本镜像按设计
# 排除重型 ML 依赖（体积考虑，模型层懒加载可回退），因此不整体安装 lock，而是按
# 下方顶层运行时子集从 lock 提取精确锁定版本；任一顶层包未命中 lock 即视为
# “lock 不完整”，整体回退到内联清单（与历史行为一致，保证构建确定性）。
COPY requirements.txt requirements.lock ./

RUN set -eux; \
    : > /tmp/pins.txt; \
    lock_incomplete=0; \
    for spec in \
        fastapi: uvicorn:[standard] sqlalchemy:[asyncio] asyncpg: \
        psycopg2-binary: aiosqlite: alembic: pydantic:[email] \
        pydantic-settings: pyjwt:[crypto] bcrypt: python-multipart: \
        redis: requests: celery: scikit-learn: scipy: joblib: \
        numpy: pandas: openpyxl: reportlab: python-dotenv: \
        slowapi: python-magic: sentry-sdk:[fastapi] \
        email-validator: httptools: websockets:; do \
        pkg="${spec%%:*}"; extra="${spec#*:}"; \
        pin="$(grep -im1 "^${pkg}==" requirements.lock || true)"; \
        if [ -n "${pin}" ]; then \
            echo "${pkg}${extra}==${pin##*==}" >> /tmp/pins.txt; \
        else \
            echo "WARN: '${pkg}' not found in requirements.lock" >&2; \
            lock_incomplete=1; \
        fi; \
    done; \
    if [ "${lock_incomplete}" -eq 0 ]; then \
        echo ">>> [deps] installing from requirements.lock (authoritative)"; \
        pip install --no-cache-dir -r /tmp/pins.txt; \
    else \
        echo ">>> [deps] requirements.lock missing/incomplete -> inline fallback"; \
        pip install --no-cache-dir \
            fastapi==0.136.1 \
            "uvicorn[standard]==0.46.0" \
            "sqlalchemy[asyncio]==2.0.49" \
            asyncpg==0.31.0 \
            "psycopg2-binary==2.9.11" \
            aiosqlite==0.19.0 \
            alembic==1.18.4 \
            "pydantic[email]==2.13.3" \
            pydantic-settings==2.14.0 \
            "PyJWT[crypto]==2.13.0" \
            "bcrypt==4.0.1" \
            python-multipart==0.0.26 \
            redis==7.4.0 \
            requests==2.32.5 \
            celery==5.6.3 \
            "scikit-learn==1.8.0" \
            scipy==1.16.2 \
            joblib==1.5.3 \
            "numpy==1.26.4" \
            "pandas==2.1.4" \
            openpyxl==3.1.5 \
            reportlab==4.4.10 \
            python-dotenv==1.2.2 \
            slowapi==0.1.9 \
            python-magic==0.4.27 \
            "sentry-sdk[fastapi]==2.58.0"; \
    fi

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
