from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

_is_sqlite = "sqlite" in settings.database_url

engine_kwargs: dict = {
    "echo": False,
    "future": True,
    "pool_pre_ping": True,
}
if not _is_sqlite:
    engine_kwargs.update(
        pool_size=20,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
    )

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
    # CRIT-005 修复：添加自动 commit/rollback，确保事务正确性
    # 成功时自动 commit（对无 pending changes 的 session 是 no-op，安全）
    # 异常时自动 rollback，避免脏数据残留
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
