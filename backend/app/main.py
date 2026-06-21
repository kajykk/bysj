from contextlib import asynccontextmanager
import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1 import api_router
from app.api.csp_report import router as csp_report_router
from app.core.config import settings
from app.core.database import close_db, engine, init_db
from app.core.exceptions import install_exception_handlers
from app.core.health import get_health_snapshot, lightweight_health_snapshot
from app.core.middlewares import (
    metrics_middleware,
    request_id_middleware,
    security_headers_middleware,
)
from app.core.openapi_responses import COMMON_ERROR_RESPONSES
from app.core.rate_limit import limiter, install_rate_limiter
from app.core.seed import seed_database
from app.core.sentry import init_sentry
from app.core.ws import websocket_endpoint
from app.models.base import Base
from app.services import ObservabilityExporter

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.seed_ready = False
    await init_db()
    # P1-INFRA-035 修复：生产环境使用 Alembic 迁移，不调用 create_all
    # 开发环境保留 create_all 以简化首次启动（自动建表）
    if settings.app_env.lower() != "production":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    else:
        logger.info("Production mode: skipping create_all, ensure 'alembic upgrade head' is run before startup")
    if settings.enable_seed:
        await seed_database()
        app.state.seed_ready = True
    try:
        from app.core.model_engine import model_engine
        await asyncio.to_thread(model_engine.preload)
        model_engine.start_persist()
    except Exception:
        logger.exception("model.preload.failed")
    init_sentry(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        release=app.version,
        traces_sample_rate=settings.sentry_traces_sample_rate,
    )
    # v1.39: 启动 ObservabilityExporter (60s 周期发布 7 v1.36 metric 到 Prometheus)
    observability_exporter = ObservabilityExporter()
    await observability_exporter.start()
    try:
        yield
    finally:
        from app.core.model_engine import model_engine as _me
        try:
            await _me.stop_persist()
        except Exception:
            logger.warning("Failed to stop monitoring persist")
        # v1.39: 停止 ObservabilityExporter
        await observability_exporter.stop()
        await close_db()


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

upload_dir = Path(__file__).resolve().parent.parent / "uploads"
try:
    upload_dir.mkdir(parents=True, exist_ok=True)
except OSError:
    logger.warning("upload_dir.creation.failed path=%s", upload_dir)
app.mount("/uploads", StaticFiles(directory=str(upload_dir)), name="uploads")

app.middleware("http")(request_id_middleware)
app.middleware("http")(security_headers_middleware)
app.middleware("http")(metrics_middleware)
install_rate_limiter(app)
app.include_router(api_router)
app.include_router(csp_report_router)
install_exception_handlers(app)


@app.websocket("/ws/{user_id}")
async def ws_endpoint(ws: WebSocket, user_id: int):
    await websocket_endpoint(ws, user_id)


@app.get("/health", responses=COMMON_ERROR_RESPONSES)
@limiter.exempt
async def health_check() -> dict:
    snapshot = await get_health_snapshot(engine, settings.redis_url)
    return {
        "status": "ok" if snapshot.database else "degraded",
        "checks": {
            "database": "ok" if snapshot.database else "failed",
            "redis": "ok" if snapshot.redis else "failed (optional)",
            "celery_worker": "ok" if snapshot.celery_worker else "failed (optional)",
        },
    }


@app.get("/health/ready", responses=COMMON_ERROR_RESPONSES)
@limiter.exempt
async def readiness_check() -> dict:
    snapshot = await get_health_snapshot(engine, settings.redis_url)
    status = "ok" if snapshot.database else "degraded"
    return {
        "status": status,
        "checks": {
            "database": "ok" if snapshot.database else "failed",
            "redis": "ok" if snapshot.redis else "failed (optional)",
            "celery_worker": "ok" if snapshot.celery_worker else "failed (optional)",
        },
    }


@app.get("/health/seed", responses=COMMON_ERROR_RESPONSES)
@limiter.exempt
async def seed_health_check() -> dict:
    return {
        "status": "ok",
        "seed_ready": bool(getattr(app.state, "seed_ready", False)),
    }
