import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from app.api.csp_report import router as csp_report_router
from app.api.v1 import api_router
from app.api.v1.uploads import router as uploads_router
from app.core.config import settings
from app.core.database import close_db, engine, init_db
from app.core.exceptions import install_exception_handlers
from app.core.health import (
    get_health_snapshot,
    get_health_snapshot_nonblocking,
    start_health_monitor,
    stop_health_monitor,
)
from app.core.logging_config import configure_logging
from app.core.middlewares import (
    metrics_middleware,
    request_id_middleware,
    security_headers_middleware,
)
from app.core.openapi_responses import COMMON_ERROR_RESPONSES
from app.core.pii_crypto import ensure_pii_key
from app.core.rate_limit import install_rate_limiter, limiter
from app.core.seed import seed_database
from app.core.sentry import init_sentry
from app.core.tenant_context import tenant_context_middleware
from app.core.ws import websocket_endpoint
from app.models.base import Base
from app.services import ObservabilityExporter

logger = logging.getLogger(__name__)


async def _async_noop(func):
    """将同步函数包装为协程，用于 record_step_async 调用同步函数."""
    func()
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # R-006 修复: 启动状态收集器 (进程级单例)，记录每个组件的启动结果
    from app.core.startup_status import (
        record_step_async,
        record_step_sync,
        startup_status,
    )

    # RES-P0-002 修复：在 lifespan 最开始配置日志轮转，确保后续所有启动日志均经过统一配置
    await record_step_async(
        "configure_logging", _async_noop(configure_logging), fatal=True
    )
    # STAB-P0-001 修复：根据 settings 初始化 DB 熔断器参数
    from app.core.db_breaker import init_db_breaker

    record_step_sync("init_db_breaker", init_db_breaker, fatal=True)
    # STAB-P1-002 修复：根据 settings 初始化 ML 推理熔断器参数
    from app.core.ml_breaker import init_ml_breaker

    record_step_sync("init_ml_breaker", init_ml_breaker, fatal=True)
    # STAB-P1-004 修复：根据 settings 初始化 SMTP 邮件熔断器参数
    from app.core.smtp_breaker import init_smtp_breaker

    record_step_sync("init_smtp_breaker", init_smtp_breaker, fatal=True)
    # STAB-P1-005 修复：根据 settings 初始化 Celery broker 熔断器参数
    from app.core.celery_breaker import init_celery_breaker

    record_step_sync("init_celery_breaker", init_celery_breaker, fatal=True)
    app.state.seed_ready = False
    # P0-1.1: startup 探针初始状态为 False, 启动完成后置 True
    app.state.started = False
    # H-01 修复：开发环境自动生成临时 PII 加密密钥，避免未配置时崩溃
    record_step_sync("ensure_pii_key", ensure_pii_key, fatal=True)
    await record_step_async("init_db", init_db(), fatal=True)
    # P1-INFRA-035 修复：生产环境使用 Alembic 迁移，不调用 create_all
    # 开发环境保留 create_all 以简化首次启动（自动建表）
    if settings.app_env.lower() != "production":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    else:
        logger.info(
            "Production mode: skipping create_all, ensure 'alembic upgrade head' is run before startup"
        )
    if settings.enable_seed:
        await record_step_async("seed_database", seed_database(), fatal=True)
        app.state.seed_ready = True
    else:
        startup_status.record("seed_database", "skipped")

    # STAB-P2-004: model preload 改为后台任务, 不阻塞启动
    # 原: await record_step_async("model_preload", _preload_models(), fatal=False) 阻塞启动
    # 新: asyncio.create_task 后台预加载, 模型未加载时按需加载 (model_engine._load_model 已有缓存+回退)
    async def _preload_models_background():
        import time as _time

        from app.core.startup_status import startup_status

        start = _time.monotonic()
        startup_status.record("model_preload", "pending")
        try:
            from app.core.model_engine import model_engine

            await asyncio.to_thread(model_engine.preload)
            model_engine.start_persist()
            # PERF-P3-007: 启动 BERT micro-batch collector (模型预加载完成后)
            try:
                await model_engine.start_bert_batch_collector()
            except Exception as batch_exc:
                logger.warning(
                    "BERT micro-batch collector start failed (non-fatal): %s",
                    batch_exc,
                )
            duration_ms = (_time.monotonic() - start) * 1000
            startup_status.record(
                "model_preload", "ok", duration_ms=duration_ms, fatal=False
            )
            logger.info("Model preload completed in background (%.0f ms)", duration_ms)
        except BaseException as exc:
            duration_ms = (_time.monotonic() - start) * 1000
            startup_status.record(
                "model_preload",
                "failed",
                error=exc,
                duration_ms=duration_ms,
                fatal=False,
            )
            logger.error(
                "Model preload failed in background: %s: %s",
                type(exc).__name__,
                exc,
                exc_info=True,
            )

    app.state._model_preload_task = asyncio.create_task(
        _preload_models_background()
    )

    # R-006: sentry 初始化失败不影响启动 (仅监控降级)
    def _init_sentry():
        init_sentry(
            dsn=settings.sentry_dsn,
            environment=settings.sentry_environment,
            release=app.version,
            traces_sample_rate=settings.sentry_traces_sample_rate,
        )

    record_step_sync("init_sentry", _init_sentry, fatal=False)
    # STAB-P2-009: 初始化 OpenTelemetry 分布式追踪 (OTLP 导出)
    # OTel 初始化失败不影响启动 (仅追踪降级, 与 Sentry 一致)
    def _init_otel():
        from app.core.otel import init_otel

        init_otel(
            service_name=settings.otel_service_name,
            service_version=settings.app_version,
            otlp_endpoint=settings.otlp_endpoint,
            otlp_protocol=settings.otlp_protocol,
            environment=settings.sentry_environment,
        )

    record_step_sync("init_otel", _init_otel, fatal=False)
    # v1.39: 启动 ObservabilityExporter (60s 周期发布 7 v1.36 metric 到 Prometheus)
    observability_exporter = ObservabilityExporter()
    await record_step_async(
        "observability_exporter", observability_exporter.start(), fatal=False
    )
    # P0-1.1: 启动后台健康监控任务, 周期性刷新健康快照缓存
    # 确保 /health/ready 端点延迟 < 5ms (仅读取内存缓存, 永不阻塞)
    await record_step_async(
        "health_monitor",
        start_health_monitor(app, engine, settings.redis_url),
        fatal=False,
    )
    # P2-1: 启动 WebSocket pubsub 订阅器,支持多 worker 部署与 Celery 跨进程通知
    # 订阅 ws:user:* pattern, 收到其他 worker/Celery 发布的消息后投递给本地连接
    from app.core.ws import ws_manager

    await record_step_async(
        "ws_pubsub", ws_manager.start_pubsub_subscriber(), fatal=False
    )
    # STAB-P1-009: 启动金丝雀回滚备用监控 (Celery 不可用时的 fallback)
    # 当 celery_breaker 状态 != closed 时, 后台任务接管 canary_auto_rollback_check
    from app.services.canary_fallback_monitor import start_canary_fallback_monitor

    await record_step_async(
        "canary_fallback", start_canary_fallback_monitor(app), fatal=False
    )
    # R-006: 标记启动序列完成 (供 /health/startup 端点使用)
    startup_status.mark_completed()
    # P0-1.1: 标记应用启动完成, /health/startup 探针返回 ok
    app.state.started = True
    try:
        yield
    finally:
        # STAB-P2-004: 取消后台模型预加载任务 (如果仍在运行)
        _preload_task = getattr(app.state, "_model_preload_task", None)
        if _preload_task is not None and not _preload_task.done():
            _preload_task.cancel()
            try:
                await _preload_task
            except asyncio.CancelledError:
                pass
        # P2-1: 停止 WebSocket pubsub 订阅器
        await ws_manager.stop_pubsub_subscriber()
        # STAB-P1-009: 停止金丝雀回滚备用监控
        from app.services.canary_fallback_monitor import stop_canary_fallback_monitor

        await stop_canary_fallback_monitor()
        # P0-1.1: 关闭后台健康监控任务
        await stop_health_monitor()
        # STAB-P2-009: 关闭 OpenTelemetry, 刷新待导出的 span
        from app.core.otel import shutdown_otel

        shutdown_otel()
        from app.core.model_engine import model_engine as _me

        # PERF-P3-007: 停止 BERT micro-batch collector (在 persist 之前停止)
        try:
            await _me.stop_bert_batch_collector()
        except Exception:
            logger.warning("Failed to stop BERT micro-batch collector")
        try:
            await _me.stop_persist()
        except Exception:
            logger.warning("Failed to stop monitoring persist")
        # v1.39: 停止 ObservabilityExporter
        await observability_exporter.stop()
        # H-Svc-9 修复：关闭 risk_service 的 PDF 生成线程池，避免应用关闭时线程泄漏
        from app.services.risk_service import shutdown_pdf_executor

        shutdown_pdf_executor()
        # P1-2: 关闭共享 Redis 客户端, 释放连接池资源
        from app.core.cache import close_redis_client

        await close_redis_client()
        await close_db()


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)

# STAB-P2-009: 对 FastAPI 应用启用 OTel 自动 instrumentation (HTTP 请求追踪)
# 在 app 创建后调用, init_otel 在 lifespan 中已初始化 TracerProvider
from app.core.otel import instrument_app as _otel_instrument_app

_otel_instrument_app(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

upload_dir = Path(__file__).resolve().parent.parent / "uploads"
# SEC-P0-001 修复：移除 StaticFiles 直接挂载，改为鉴权路由 + 归属校验
# 原 app.mount("/uploads", StaticFiles(...)) 任何未登录用户均可访问 /uploads/*，
# 泄露用户头像/音频/PDF 报告等敏感数据。
# 现使用 app.api.v1.uploads 提供的两条鉴权路由：
#   GET /uploads/{user_id}/{filename}   - 用户私有文件 (JWT + 归属校验)
#   GET /uploads/public/{subpath:path}  - 公共资源 (白名单 audio/content 目录)
try:
    upload_dir.mkdir(parents=True, exist_ok=True)
except OSError:
    logger.warning(
        "upload_dir.creation.failed path=%s - /uploads route may fail", upload_dir
    )

app.middleware("http")(request_id_middleware)
app.middleware("http")(tenant_context_middleware)
app.middleware("http")(security_headers_middleware)
app.middleware("http")(metrics_middleware)
install_rate_limiter(app)
app.include_router(api_router)
app.include_router(csp_report_router)
app.include_router(uploads_router)
install_exception_handlers(app)


@app.websocket("/ws/{user_id}")
async def ws_endpoint(ws: WebSocket, user_id: int):
    await websocket_endpoint(ws, user_id)


@app.get("/health", responses=COMMON_ERROR_RESPONSES, deprecated=True)
@limiter.exempt
async def health_check() -> dict:
    """[DEPRECATED] 完整健康检查 (DB + Redis + Celery + Models 同步执行).

    PERF-P3-005: 该端点在缓存未命中时会同步执行 4 项 I/O 检查,
    高负载下可能阻塞 3-8s, 不适合作为 k8s 探针使用.

    建议使用以下替代端点:
    - /health/live: 轻量存活探针 (无 I/O, 延迟 < 5ms)
    - /health/ready: 就绪探针 (读取缓存, 延迟 < 5ms, 后台任务刷新)
    - /health/startup: 启动探针 (检查启动流程是否完成)

    该端点暂保留用于人工调试, 后续版本将移除.
    """
    snapshot = await get_health_snapshot(engine, settings.redis_url)
    # R-006 修复: 暴露启动失败组件摘要，便于运维定位降级原因
    from app.core.startup_status import startup_status

    return {
        "status": "ok" if snapshot.database else "degraded",
        "checks": {
            "database": "ok" if snapshot.database else "failed",
            "redis": "ok" if snapshot.redis else "failed (optional)",
            "celery_worker": "ok" if snapshot.celery_worker else "failed (optional)",
            # STAB-P1-007: 暴露 ML 核心模型可用性 (3 个降级回退模型文件存在性)
            "models": "ok" if snapshot.models else "failed (optional)",
        },
        **startup_status.to_summary_dict(),
    }


@app.get("/health/live", responses=COMMON_ERROR_RESPONSES)
@limiter.exempt
async def liveness_check() -> dict:
    """P0-1.1: 轻量存活探针.

    仅检查进程存活与事件循环响应能力, 不执行任何 I/O.
    延迟目标: < 5ms. 适用于 k8s liveness probe.
    """
    return {"status": "ok"}


@app.get("/health/ready", responses=COMMON_ERROR_RESPONSES)
@limiter.exempt
async def readiness_check() -> dict:
    """P0-1.1: 就绪探针 (非阻塞).

    返回缓存中的健康快照, 永不阻塞. 后台健康监控任务
    (start_health_monitor) 周期性刷新缓存, 确保数据常新.
    延迟目标: < 5ms (仅读取内存缓存).
    """
    snapshot = await get_health_snapshot_nonblocking(engine, settings.redis_url)
    # R-006 修复: 暴露启动失败组件摘要
    from app.core.startup_status import startup_status

    status = "ok" if snapshot.database else "degraded"
    # 若有启动失败组件，整体状态降级为 degraded
    if startup_status.failed_components:
        status = "degraded"
    return {
        "status": status,
        "checks": {
            "database": "ok" if snapshot.database else "failed",
            "redis": "ok" if snapshot.redis else "failed (optional)",
            "celery_worker": "ok" if snapshot.celery_worker else "failed (optional)",
            # STAB-P1-007: 暴露 ML 核心模型可用性
            "models": "ok" if snapshot.models else "failed (optional)",
        },
        **startup_status.to_summary_dict(),
    }


@app.get("/health/startup", responses=COMMON_ERROR_RESPONSES)
@limiter.exempt
async def startup_check() -> dict:
    """P0-1.1: 启动探针.

    检查应用是否完成启动流程 (DB 初始化/模型预加载/健康监控启动).
    适用于 k8s startup probe, 启动完成前返回 503, 完成后返回 200.

    R-006 修复: 返回结构化启动状态，包含每个组件的成功/失败/跳过状态、
    错误类型与摘要、耗时。便于运维通过 /health/startup 定位启动失败原因。
    """
    started = bool(getattr(app.state, "started", False))
    # R-006: 暴露完整启动状态 (组件级详情 + 致命错误)
    from app.core.startup_status import startup_status

    return {
        "status": "ok" if started else "starting",
        "started": started,
        **startup_status.to_dict(),
    }


@app.get("/health/seed", responses=COMMON_ERROR_RESPONSES)
@limiter.exempt
async def seed_health_check() -> dict:
    return {
        "status": "ok",
        "seed_ready": bool(getattr(app.state, "seed_ready", False)),
    }
