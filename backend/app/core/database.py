from collections.abc import AsyncGenerator

from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings, settings


def _build_engine_kwargs(is_sqlite: bool, settings_obj: Settings) -> dict:
    """构造 ``create_async_engine`` 的 kwargs.

    STAB-P0-002: PostgreSQL 模式下通过 ``server_settings`` 透传 ``statement_timeout``,
    防止慢查询持续占用连接. SQLite 不支持此参数, 自动跳过.

    抽取为独立函数以便单元测试覆盖不同配置组合, 无需 reload 模块.
    """
    kwargs: dict = {
        "echo": False,
        "future": True,
        "pool_pre_ping": True,
    }
    if not is_sqlite:
        # M-L 修复：连接池参数从 settings 读取，支持通过环境变量调整
        kwargs.update(
            pool_size=settings_obj.db_pool_size,
            max_overflow=settings_obj.db_max_overflow,
            pool_timeout=settings_obj.db_pool_timeout,
            pool_recycle=settings_obj.db_pool_recycle,
        )
        # STAB-P0-002 修复: PostgreSQL 语句级超时, 防止慢查询持续占用连接
        # asyncpg 通过 server_settings 透传 PostgreSQL GUC, statement_timeout 单位为毫秒
        # 仅在显式配置 (>0) 时生效, 0 表示禁用
        if settings_obj.db_statement_timeout > 0:
            kwargs["connect_args"] = {
                "server_settings": {
                    "statement_timeout": str(settings_obj.db_statement_timeout * 1000),
                },
            }
    return kwargs


_is_sqlite = settings.database_url.startswith("sqlite")
engine_kwargs: dict = _build_engine_kwargs(_is_sqlite, settings)

engine: AsyncEngine = create_async_engine(settings.database_url, **engine_kwargs)
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
    autoflush=False,
)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(lambda _: None)


async def close_db() -> None:
    await engine.dispose()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """STAB-P0-001 修复：集成熔断器的 DB 依赖。

    - 熔断器 OPEN 时抛 HTTPException(503), 快速拒绝, 避免连接池耗尽
    - 连接级异常 (OperationalError/TimeoutError/OSError) 触发失败计数
    - 业务异常 (IntegrityError/DataError) 不触发熔断器
    - 成功完成后重置失败计数

    测试环境可通过 ``DB_CIRCUIT_BREAKER_ENABLED=false`` 禁用。
    """
    # STAB-P0-001: 熔断器检查 (仅在启用时)
    if settings.db_circuit_breaker_enabled:
        from app.core.db_breaker import db_breaker

        await db_breaker.before_request()  # OPEN 时抛 CircuitBreakerOpenError(503)

    # H-Core-1 修复：移除自动 commit，避免只读路由在 auto-flush 时提交非预期变更
    # 由路由/service 层显式 commit；异常时仍自动 rollback 避免脏数据残留
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as exc:
            await session.rollback()
            # STAB-P0-001: 连接级失败记录到熔断器 (业务异常不计入)
            if settings.db_circuit_breaker_enabled:
                from app.core.db_breaker import db_breaker

                # 业务异常不触发熔断器 (IntegrityError/ProgrammingError/DataError 等)
                if not isinstance(exc, (IntegrityError, ProgrammingError)):
                    await db_breaker.on_failure(exc)
            raise
        else:
            # STAB-P0-001: 请求成功, 重置失败计数
            if settings.db_circuit_breaker_enabled:
                from app.core.db_breaker import db_breaker

                await db_breaker.on_success()
        finally:
            await session.close()
