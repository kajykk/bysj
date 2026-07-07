from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.celery_app import celery_app

# P1-E 修复：添加 logger 记录健康检查失败原因，便于运维定位问题
logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from fastapi import FastAPI

# P0-1.1: 健康检查分层 - 后台健康监控任务刷新间隔 (秒)
# 该任务周期性调用 get_health_snapshot 刷新缓存，确保 /health/ready 永不阻塞
HEALTH_MONITOR_INTERVAL_SECONDS: float = 10.0


def _is_test_environment() -> bool:
    """检测当前是否在 pytest 测试环境中运行.

    P0-1.1: 测试环境跳过后台健康监控任务, 避免 Redis/Celery 超时阻塞测试.
    """
    return "PYTEST_CURRENT_TEST" in os.environ


@dataclass(slots=True)
class HealthSnapshot:
    database: bool | None = None
    redis: bool | None = None
    celery_worker: bool | None = None
    # STAB-P1-007 修复：增加 ML 模型可用性字段
    # 检查 3 个核心模型文件存在性 (structured_logistic_regression_quick + text_depression_model + text_depression_tfidf)
    # None 表示未检查, True 表示全部就绪, False 表示至少一个缺失
    models: bool | None = None
    collected_at: float = 0.0
    # M-Core-16 修复：标记健康状态是否经过实际检查，
    # basic_health_snapshot 返回未经验证的静态值时为 False。
    verified: bool = True


async def check_database(engine: AsyncEngine) -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        # P1-E 修复：记录数据库健康检查失败原因
        logger.warning("Database health check failed", exc_info=True)
        return False


async def check_redis(redis_url: str) -> bool:
    """P1-2: 复用共享 Redis 客户端, 避免每次健康检查创建/关闭新连接.

    历史问题: 健康监控任务每 10s 调用一次 check_redis, 旧实现每次
    from_url() + aclose(), 导致连接池无法复用, TCP 连接频繁建立/断开.

    现在使用 app.core.cache.get_redis_client() 共享单例:
    - 客户端仅初始化一次, 后续 ping 复用同一连接池.
    - 不再 aclose() 客户端, 保留单例供下次健康检查复用.
    - 应用关闭时由 main.py lifespan 调用 close_redis_client() 统一释放.
    """
    # 延迟导入避免循环依赖 (cache 模块在初始化阶段可能触发 health 检查)
    from app.core.cache import get_redis_client

    try:
        client = await get_redis_client()
        if client is None:
            # 共享客户端初始化失败 (无 redis_url 或连接异常)
            return False
        # H-03 修复: 保留整体超时保护, 防止 Redis 网络黑洞导致 /health 挂起
        pong = await asyncio.wait_for(client.ping(), timeout=3.0)
        return bool(pong)
    except asyncio.TimeoutError:
        # H-03 修复：Redis 健康检查超时，记录日志便于运维定位网络问题
        logger.warning("Redis health check timed out after 3.0s")
        return False
    except Exception:
        # P1-E 修复：记录 Redis 健康检查失败原因
        logger.warning("Redis health check failed", exc_info=True)
        return False


async def check_celery_worker(redis_url: str, timeout_seconds: float = 1.5) -> bool:
    """STAB-P1-005: 在 Celery broker 熔断器保护下检查 worker 可用性.

    改造点:
    - ``inspect.stats()`` 调用用 ``call_with_celery_breaker`` 包装,
      broker 连续 5 次失败后熔断器 OPEN, 后续健康检查快速返回 False
      (不再每次阻塞 1.5s+0.5s).
    - 熔断器 OPEN 时捕获 ``CircuitBreakerOpenError`` 返回 False.
    - 顺带激活 ``celery_worker_heartbeat`` 指标 (成功=1, 失败=0),
      使 AR-205 告警规则生效.
    """
    from app.core.celery_breaker import (
        CircuitBreakerOpenError,
        call_with_celery_breaker,
    )
    from app.core.metrics import celery_worker_heartbeat

    try:
        inspect = celery_app.control.inspect(timeout=timeout_seconds)
        # 添加 asyncio.wait_for 超时保护，防止 broker 网络挂起导致 /health 无限阻塞
        # STAB-P1-005: 用熔断器包装 inspect.stats() 调用
        stats = await asyncio.wait_for(
            call_with_celery_breaker(asyncio.to_thread(inspect.stats)),
            timeout=timeout_seconds + 0.5,
        )
        celery_worker_heartbeat.set(1.0)
        return bool(stats)
    except CircuitBreakerOpenError:
        # 熔断器打开: broker 持续不可用, 快速返回 False
        celery_worker_heartbeat.set(0.0)
        return False
    except asyncio.TimeoutError:
        logger.warning(
            "Celery worker health check timed out after %.1fs", timeout_seconds + 0.5
        )
        celery_worker_heartbeat.set(0.0)
        return False
    except Exception:
        # P1-E 修复：记录 Celery worker 健康检查失败原因
        logger.warning("Celery worker health check failed", exc_info=True)
        celery_worker_heartbeat.set(0.0)
        return False


# STAB-P1-007: 核心模型 ID 集合 — 与 ModelPredictService.get_model_status 的 ready 字段逻辑一致
# 这 3 个模型是系统降级回退路径的最低保障, 任一缺失即视为 ML 不可用
_CORE_MODEL_IDS: tuple[str, ...] = (
    "structured_logistic_regression_quick",
    "text_depression_model",
    "text_depression_tfidf",
)


async def check_models() -> bool:
    """STAB-P1-007: 检查 ML 核心模型文件可用性.

    检查 3 个核心模型文件是否存在 (不加载模型, 仅 stat 文件):
    - structured_logistic_regression_quick: 结构化评估降级模型
    - text_depression_model: 文本评估降级模型
    - text_depression_tfidf: 文本评估 TF-IDF 向量器

    设计要点:
    - 仅检查文件存在性, 不加载模型 (避免阻塞, 延迟 < 100ms)
    - 复用 model_registry.resolve_model_path 解析路径
    - 任一核心模型缺失即返回 False
    - 异常时返回 False 并记录日志, 不抛出
    """
    try:
        from app.core.config import settings
        from app.core.model_registry import resolve_model_path

        model_dir = Path(settings.model_dir)
        for model_id in _CORE_MODEL_IDS:
            path = Path(resolve_model_path(model_id))
            # 路径解析逻辑与 ModelPredictService.get_model_status 一致
            if not path.is_absolute():
                if path.parts and path.parts[0] == "models":
                    abs_path = model_dir.parent / path
                else:
                    abs_path = model_dir / path
            else:
                abs_path = path
            if not abs_path.exists():
                logger.warning(
                    "Model health check failed: core model missing id=%s path=%s",
                    model_id,
                    abs_path,
                )
                return False
        return True
    except Exception:
        logger.warning("Model health check failed", exc_info=True)
        return False


# L-14 修复：移除无意义的 @lru_cache 装饰器，直接返回常量
def get_health_cache_ttl_seconds() -> float:
    return 5.0


_snapshot: HealthSnapshot = HealthSnapshot()
# L-修复：使用 asyncio.Lock 保护并发健康检查，避免多个协程同时执行重复检查
_health_lock = asyncio.Lock()


async def get_health_snapshot(engine: AsyncEngine, redis_url: str) -> HealthSnapshot:
    global _snapshot

    now = monotonic()
    if (
        _snapshot.collected_at
        and now - _snapshot.collected_at < get_health_cache_ttl_seconds()
    ):
        return _snapshot

    async with _health_lock:
        # 双重检查：获取锁后再次确认缓存是否已被其他协程填充
        now = monotonic()
        if (
            _snapshot.collected_at
            and now - _snapshot.collected_at < get_health_cache_ttl_seconds()
        ):
            return _snapshot

        # L-15 修复：三项健康检查（database/redis/celery）并行执行，避免 celery 检查串行等待 db/redis
        # STAB-P1-007: 新增 models 检查, 4 项并行执行
        database, redis_ok, celery_ok, models_ok = await asyncio.gather(
            check_database(engine),
            check_redis(redis_url),
            check_celery_worker(redis_url),
            check_models(),
        )
        snapshot = HealthSnapshot(
            database=database,
            redis=redis_ok,
            celery_worker=celery_ok,
            models=models_ok,
            collected_at=now,
            verified=True,
        )
        _snapshot = snapshot
        return snapshot


async def basic_health_snapshot() -> HealthSnapshot:
    """返回静态健康快照（不检查外部依赖，未经验证）。

    database=True 为硬编码值，redis/celery_worker 均为 None，
    verified=False 标记该值未经验证。

    适用于不需要真实健康状态的场景（如单元测试 mock、启动早期探针）。
    生产环境应使用 get_health_snapshot() 获取真实健康状态。
    """
    return HealthSnapshot(
        database=True,
        redis=None,
        celery_worker=None,
        models=None,
        collected_at=monotonic(),
        verified=False,
    )


# ── P0-1.1: 健康检查分层 ──────────────────────────────────────────────
# 后台健康监控任务: 周期性刷新 _snapshot 缓存, 确保 /health/ready 永不阻塞
_health_monitor_task: asyncio.Task[None] | None = None


async def get_health_snapshot_nonblocking(
    engine: AsyncEngine, redis_url: str
) -> HealthSnapshot:
    """非阻塞获取健康快照 (P0-1.1).

    优先返回缓存 (即使已过期), 避免阻塞请求线程.
    仅在首次调用 (缓存为空) 时同步执行检查.

    适用于 k8s readiness probe 等对延迟敏感的场景.
    生产环境应配合 start_health_monitor() 后台任务, 保持缓存常新.
    """
    now = monotonic()
    # 缓存有效: 直接返回
    if (
        _snapshot.collected_at
        and now - _snapshot.collected_at < get_health_cache_ttl_seconds()
    ):
        return _snapshot
    # 缓存过期但存在: 返回旧值 (后台任务会异步刷新), 避免阻塞
    if _snapshot.collected_at:
        return _snapshot
    # 首次调用 (缓存为空): 同步执行一次, 填充缓存
    return await get_health_snapshot(engine, redis_url)


async def _health_monitor_loop(engine: AsyncEngine, redis_url: str) -> None:
    """后台健康监控循环: 周期性刷新健康快照缓存.

    每 HEALTH_MONITOR_INTERVAL_SECONDS 秒调用一次 get_health_snapshot,
    确保 /health/ready 端点始终能命中缓存, 永不阻塞.
    """
    while True:
        try:
            await get_health_snapshot(engine, redis_url)
        except asyncio.CancelledError:
            # 应用关闭时正常退出
            raise
        except Exception:
            logger.warning("Health monitor refresh failed", exc_info=True)
        await asyncio.sleep(HEALTH_MONITOR_INTERVAL_SECONDS)


async def start_health_monitor(
    app: "FastAPI", engine: AsyncEngine, redis_url: str
) -> None:
    """启动后台健康监控任务 (P0-1.1).

    在 lifespan 启动阶段调用. 周期性刷新健康快照缓存,
    确保 /health/ready 端点延迟 < 5ms (仅读取内存缓存).

    任务句柄存储在 app.state.health_monitor_task, 在应用关闭时由
    stop_health_monitor() 取消.

    注意: 不在启动阶段同步调用 get_health_snapshot, 避免阻塞 lifespan
    (Redis/Celery 健康检查可能耗时 3-8s). 后台任务首次迭代会异步填充缓存.
    若 /health/ready 在缓存填充前被调用, get_health_snapshot_nonblocking
    会回退到同步检查 (仅首次).

    测试环境 (PYTEST_CURRENT_TEST 已设置) 跳过后台监控, 避免超时阻塞测试.
    """
    global _health_monitor_task
    if _is_test_environment():
        logger.info("Health monitor skipped in test environment")
        return
    if _health_monitor_task is not None and not _health_monitor_task.done():
        logger.warning("Health monitor already running, skip duplicate start")
        return
    _health_monitor_task = asyncio.create_task(_health_monitor_loop(engine, redis_url))
    app.state.health_monitor_task = _health_monitor_task
    logger.info(
        "Health monitor started (interval=%.1fs)", HEALTH_MONITOR_INTERVAL_SECONDS
    )


async def stop_health_monitor() -> None:
    """停止后台健康监控任务 (P0-1.1). 在 lifespan 关闭阶段调用."""
    global _health_monitor_task
    if _health_monitor_task is None:
        return
    _health_monitor_task.cancel()
    try:
        await _health_monitor_task
    except asyncio.CancelledError:
        pass
    _health_monitor_task = None
    logger.info("Health monitor stopped")
